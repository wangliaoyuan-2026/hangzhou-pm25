"""把 data/ 里的原始数据汇总成看板直接使用的 site/data/dashboard.json。"""
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from common import mean, read_wide_csv, read_yearly
from config import CN_CITIES, CN_GRADES, DATA, HOME_CITY, INTL_CITIES, LIMITS, SITE_DATA, YRD

ANNUAL_MIN_DAYS = 324  # GB 3095：年均值至少需要 324 个有效日均值


def load_json(name):
    p = DATA / name
    return json.loads(p.read_text()) if p.exists() else None


def series(table, city):
    return {d: row[city] for d, row in table.items() if row.get(city) is not None}


def yearly_stats(s, this_year):
    by_year = defaultdict(list)
    for d, v in s.items():
        by_year[int(d[:4])].append(v)
    out = []
    for y in sorted(by_year):
        vals = by_year[y]
        out.append({
            "year": y,
            "mean": round(mean(vals), 1),
            "days": len(vals),
            "partial": y == this_year or len(vals) < ANNUAL_MIN_DAYS,
            "cn_ok": sum(v <= LIMITS["cn_24h"] for v in vals),
            "who_ok": sum(v <= LIMITS["who_24h"] for v in vals),
        })
    return out


def window_mean(s, end, days):
    start = (end - timedelta(days=days - 1)).isoformat()
    vals = [v for d, v in s.items() if start <= d <= end.isoformat()]
    return (round(mean(vals), 1), len(vals)) if vals else (None, 0)


def compare_block(table, cities, today, source):
    if not table:
        return None
    last = max(table)
    end = date.fromisoformat(last)
    out = {"source": source, "last_date": last, "cities": []}
    for c in cities:
        s = series(table, c)
        if not s:
            continue
        m30, n30 = window_mean(s, end, 30)
        m365, n365 = window_mean(s, end, 365)
        start365 = (end - timedelta(days=364)).isoformat()
        recent = [v for d, v in s.items() if d >= start365]
        out["cities"].append({
            "name": c, "last30": m30, "last365": m365, "days365": n365,
            "cn_ok365": sum(v <= LIMITS["cn_24h"] for v in recent),
            "who_ok365": sum(v <= LIMITS["who_24h"] for v in recent),
            "yearly": yearly_stats(s, today.year),
        })
    return out


def main():
    today = datetime.now(timezone(timedelta(hours=8))).date()
    cn, _ = read_yearly(DATA / "cn_daily")
    intl, _ = read_wide_csv(DATA / "intl_daily.csv")
    om, _ = read_wide_csv(DATA / "om_daily.csv")
    live = load_json("live.json") or {"cities": {}, "stations": [], "sources": {}}
    fc = load_json("om_forecast.json") or {"cities": {}}
    cn_latest = load_json("cn_latest.json") or {}

    # 实时读数只展示实测：国内用国控站最新小时值，国外用 OpenAQ/WAQI；模型值不进实时表
    live_cities = {}
    for name in [*CN_CITIES, *INTL_CITIES]:
        v = (live.get("cities") or {}).get(name)
        if name in CN_CITIES and name in cn_latest:
            v = {**cn_latest[name], "source": "国控站", "note": "城市均值"}
        live_cities[name] = v if v and "模型" not in v.get("source", "") else None

    hourly = []
    for hp in sorted((DATA / "hz_hourly").glob("*.csv")):
        with open(hp, encoding="utf-8") as f:
            hourly += [(r[0], float(r[1])) for r in list(csv.reader(f))[1:] if r[1]]

    # 当天数据还不完整，日均只用到昨天
    hz = {d: v for d, v in series(cn, HOME_CITY).items() if d < today.isoformat()}
    last_day = max(hz) if hz else None

    # 杭州：最近 7 天逐小时
    cutoff = (date.fromisoformat(last_day) - timedelta(days=6)).isoformat() if last_day else ""
    hourly_7d = [[t, v] for t, v in hourly if t[:10] >= cutoff]

    # 月份 × 小时热力图（全部历史平均）
    cells = defaultdict(list)
    for t, v in hourly:
        cells[(int(t[5:7]), int(t[11:13]))].append(v)
    heatmap = [[m - 1, h, round(mean(cells[(m, h)]), 1)] for m in range(1, 13) for h in range(24) if cells[(m, h)]]

    # 变化：最近一天 vs 前一天、去年同日；近 30 天 vs 去年同期
    changes = {}
    if last_day:
        ld = date.fromisoformat(last_day)
        prev = hz.get((ld - timedelta(1)).isoformat())
        ly = hz.get(ld.replace(year=ld.year - 1).isoformat()) if not (ld.month == 2 and ld.day == 29) else None
        m30, _ = window_mean(hz, ld, 30)
        m30_ly, _ = window_mean(hz, ld - timedelta(365), 30)
        changes = {"last": hz[last_day], "prev": prev, "last_year": ly, "m30": m30, "m30_last_year": m30_ly}

    # 杭州在全国城市中的排名（近 365 天均值，越小越好）
    rank = None
    if last_day:
        ld = date.fromisoformat(last_day)
        scores = []
        for c in {c for row in cn.values() for c in row}:
            m, n = window_mean(series(cn, c), ld, 365)
            if m is not None and n >= 300:
                scores.append((m, c))
        scores.sort()
        names = [c for _, c in scores]
        if HOME_CITY in names:
            rank = {"rank": names.index(HOME_CITY) + 1, "total": len(names),
                    "best": [{"name": c, "mean": m} for m, c in scores[:5]],
                    "worst": [{"name": c, "mean": m} for m, c in scores[-5:]]}

    # 预报：用近 30 天“实测/模型”比值校正 CAMS 模型偏差
    hz_fc = fc["cities"].get(HOME_CITY, {})
    ratio = None
    if hz and om:
        pairs = [(hz[d], om[d][HOME_CITY]) for d in sorted(hz)[-30:] if om.get(d, {}).get(HOME_CITY)]
        if len(pairs) >= 14:
            ratio = round(sum(a for a, _ in pairs) / sum(b for _, b in pairs), 2)
    forecast = {
        "ratio": ratio,
        "daily": [{"date": x["date"], "raw": x["pm25"],
                   "corrected": round(x["pm25"] * ratio, 1) if ratio else None} for x in hz_fc.get("daily", [])],
        "hourly": [[x["time"], round(x["pm25"] * ratio, 1) if ratio else x["pm25"]] for x in hz_fc.get("hourly", [])],
    }

    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "home": HOME_CITY,
        "limits": LIMITS,
        "grades": [[g if g != float("inf") else None, n] for g, n in CN_GRADES],
        "sources": live.get("sources", {}),
        "hz": {
            "last_day": last_day,
            "last_hour": hourly[-1] if hourly else None,
            "changes": changes,
            "hourly_7d": hourly_7d,
            "daily": [[d, hz[d]] for d in sorted(hz)],
            "yearly": yearly_stats(hz, today.year),
            "heatmap": heatmap,
            "rank": rank,
        },
        "cn": compare_block(cn, list(CN_CITIES), today, "中国环境监测总站国控站（经 quotsoft.net 镜像）"),
        "yrd": YRD,
        "intl": compare_block(intl, [HOME_CITY, *INTL_CITIES], today, "OpenAQ 官方实测") if intl else None,
        "live": live_cities,
        "live_generated": live.get("generated"),
        "stations": live.get("stations", []),
        "forecast": forecast,
    }
    # 国际对比里的杭州使用国控站数据，和国外实测放在一起
    if out["intl"] is not None:
        hz_cn = next((c for c in out["cn"]["cities"] if c["name"] == HOME_CITY), None)
        out["intl"]["cities"] = [c for c in out["intl"]["cities"] if c["name"] != HOME_CITY]
        if hz_cn:
            out["intl"]["cities"].insert(0, hz_cn)

    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "dashboard.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"dashboard.json 已生成：杭州 {len(hz)} 天，最新 {last_day}；国际实测 {'有' if intl else '无'}")


if __name__ == "__main__":
    main()
