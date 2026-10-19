"""下载国控站城市数据，更新 data/cn_daily.csv（全国城市 PM2.5 日均）和 data/hz_hourly.csv（杭州逐小时）。

用法：
  python scripts/update_cn.py --days 5            # 日常更新：补最近 5 天
  python scripts/update_cn.py --start 2016-01-01  # 首次回填历史
"""
import argparse
import csv
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from common import http_get, read_yearly, write_yearly
from config import CACHE, CNEMC_CITY_URL, CNEMC_START, DATA, HOME_CITY, MIN_HOURS_PER_DAY

DAILY_DIR = DATA / "cn_daily"      # 全国城市日均，按年拆分
HOURLY_DIR = DATA / "hz_hourly"    # 杭州逐小时，按年拆分
LATEST_JSON = DATA / "cn_latest.json"
CACHE_DIR = CACHE / "cn"


def parse_day(raw):
    """返回 ({城市: 日均}, [杭州 0-23 点浓度])。"""
    rows = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
    header = next(rows)
    cities = header[3:]
    hourly = {c: [None] * 24 for c in cities}
    for r in rows:
        if len(r) < 3 or r[2] != "PM2.5":
            continue
        h = int(r[1])
        for c, v in zip(cities, r[3:]):
            if v:
                hourly[c][h] = float(v)
    daily = {}
    for c, vals in hourly.items():
        ok = [v for v in vals if v is not None]
        if len(ok) >= MIN_HOURS_PER_DAY:
            daily[c] = round(sum(ok) / len(ok), 1)
    latest = {}
    for c, vals in hourly.items():
        for h in range(23, -1, -1):
            if vals[h] is not None:
                latest[c] = [h, vals[h]]
                break
    return daily, hourly.get(HOME_CITY, [None] * 24), latest


def fetch_day(d, use_cache):
    ymd = d.strftime("%Y%m%d")
    cache = CACHE_DIR / f"{ymd}.json"
    if use_cache and cache.exists():
        return d, json.loads(cache.read_text())
    raw = http_get(CNEMC_CITY_URL.format(ymd=ymd))
    if raw is None:
        return d, None
    daily, hz, latest = parse_day(raw)
    result = {"daily": daily, "hz": hz, "latest": latest}
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result, ensure_ascii=False))
    return d, result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--days", type=int)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    today = datetime.now(timezone(timedelta(hours=8))).date()
    end = date.fromisoformat(a.end) if a.end else today
    if a.days:
        start = end - timedelta(days=a.days)
    else:
        start = date.fromisoformat(a.start or CNEMC_START)
    # 从最近的日期往前下载，中途中断也能先用上近期数据
    days = [end - timedelta(n) for n in range((end - start).days + 1)]
    # 当天和昨天的数据可能还不完整，不使用缓存
    fresh = {today, today - timedelta(1)}

    table, cols = read_yearly(DAILY_DIR, legacy=DATA / "cn_daily.csv")
    hourly = {}
    legacy_hourly = DATA / "hz_hourly.csv"
    for p in ([legacy_hourly] if legacy_hourly.exists() else []) + sorted(HOURLY_DIR.glob("*.csv")):
        with open(p, encoding="utf-8") as f:
            for r in list(csv.reader(f))[1:]:
                hourly[r[0]] = float(r[1]) if r[1] else None
    touched = set()

    def save():
        # 只重写有变化的年份，避免每次提交都改动全部历史文件
        years = touched | ({k[:4] for k in table} if migrate else set())
        write_yearly(DAILY_DIR, table, cols, years)
        HOURLY_DIR.mkdir(parents=True, exist_ok=True)
        for y in years:
            with open(HOURLY_DIR / f"{y}.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["time", "pm25"])
                for k in sorted(k for k in hourly if k.startswith(y)):
                    w.writerow([k, "" if hourly[k] is None else f"{hourly[k]:g}"])

    migrate = (DATA / "cn_daily.csv").exists() or legacy_hourly.exists()

    newest = None
    missing = 0
    with ThreadPoolExecutor(a.workers) as ex:
        jobs = [ex.submit(fetch_day, d, not a.no_cache and d not in fresh) for d in days]
        for i, job in enumerate(jobs, 1):
            d, res = job.result()
            if res is None:
                missing += 1
                continue
            iso = d.isoformat()
            touched.add(iso[:4])
            if res.get("latest") and (newest is None or d > newest[0]):
                newest = (d, res["latest"])
            for c in res["daily"]:
                if c not in cols:
                    cols.append(c)
            if res["daily"]:
                table[iso] = res["daily"]
            for h, v in enumerate(res["hz"]):
                if v is not None:
                    hourly[f"{iso} {h:02d}"] = v
            if i % 50 == 0:
                save()
                print(f"  {i}/{len(days)} 天（已到 {iso}）", flush=True)

    save()
    if migrate:
        (DATA / "cn_daily.csv").unlink(missing_ok=True)
        legacy_hourly.unlink(missing_ok=True)
    if newest and newest[0] >= today - timedelta(1):
        LATEST_JSON.write_text(json.dumps(
            {c: {"time": f"{newest[0].isoformat()}T{h:02d}:00+08:00", "pm25": v} for c, (h, v) in newest[1].items()},
            ensure_ascii=False))
    print(f"国控站数据：{start} ~ {end} 共 {len(days)} 天，缺失 {missing} 天；"
          f"cn_daily 共 {len(table)} 天 × {len(cols)} 城市")


if __name__ == "__main__":
    sys.exit(main())
