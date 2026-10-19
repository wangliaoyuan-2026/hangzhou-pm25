"""从 Open-Meteo（CAMS 模型）拉取所有对比城市的 PM2.5，更新 data/om_daily.csv 和 data/om_forecast.json。

模型数据用于国际对比（所有城市同一口径）和未来 5 天预报，不作为国内官方数据。

用法：
  python scripts/update_model.py            # 日常更新：最近 10 天 + 未来 5 天
  python scripts/update_model.py --full     # 首次回填：从 2022-08-01 起
"""
import argparse
import json
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from common import get_json, read_wide_csv, write_wide_csv
from config import CN_CITIES, DATA, INTL_CITIES, MIN_HOURS_PER_DAY, OPEN_METEO_START, OPEN_METEO_URL

DAILY_CSV = DATA / "om_daily.csv"
FORECAST_JSON = DATA / "om_forecast.json"


def all_cities():
    out = {name: (lat, lon) for name, (lat, lon) in CN_CITIES.items()}
    out.update({name: (lat, lon) for name, (lat, lon, _) in INTL_CITIES.items()})
    return out


def fetch(cities, start, end):
    names = list(cities)
    q = {
        "latitude": ",".join(str(cities[n][0]) for n in names),
        "longitude": ",".join(str(cities[n][1]) for n in names),
        "hourly": "pm2_5",
        "timezone": "auto",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    res = get_json(f"{OPEN_METEO_URL}?{urllib.parse.urlencode(q)}", timeout=180)
    if isinstance(res, dict):
        res = [res]
    return dict(zip(names, res))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()

    today = datetime.now(timezone(timedelta(hours=8))).date()
    start = date.fromisoformat(OPEN_METEO_START) if a.full else today - timedelta(days=10)
    end = today + timedelta(days=4)
    cities = all_cities()

    # 一次请求的数据量有上限，按年分段
    data = defaultdict(lambda: {"time": [], "pm2_5": []})
    seg = start
    while seg <= end:
        seg_end = min(end, date(seg.year, 12, 31))
        for name, res in fetch(cities, seg, seg_end).items():
            data[name]["time"] += res["hourly"]["time"]
            data[name]["pm2_5"] += res["hourly"]["pm2_5"]
        seg = seg_end + timedelta(1)

    table, cols = read_wide_csv(DAILY_CSV)
    cols = list(dict.fromkeys([*cols, *cities]))
    forecast = {"generated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "cities": {}}
    for name, series in data.items():
        by_day = defaultdict(list)
        for t, v in zip(series["time"], series["pm2_5"]):
            if v is not None:
                by_day[t[:10]].append(v)
        fc_days = []
        for d, vals in by_day.items():
            avg = round(sum(vals) / len(vals), 1) if len(vals) >= MIN_HOURS_PER_DAY else None
            if d < today.isoformat():
                if avg is not None:
                    table.setdefault(d, {})[name] = avg
            else:
                fc_days.append({"date": d, "pm25": avg if avg is not None else round(sum(vals) / len(vals), 1)})
        # 预报：今天起的逐日均值；杭州额外保留逐小时
        entry = {"daily": sorted(fc_days, key=lambda x: x["date"])}
        if name == "杭州":
            entry["hourly"] = [
                {"time": t, "pm25": v} for t, v in zip(series["time"], series["pm2_5"])
                if t[:10] >= today.isoformat() and v is not None
            ]
        forecast["cities"][name] = entry

    write_wide_csv(DAILY_CSV, table, cols)
    FORECAST_JSON.write_text(json.dumps(forecast, ensure_ascii=False, indent=1))
    print(f"Open-Meteo：{start} ~ {end}，{len(cities)} 个城市；om_daily 共 {len(table)} 天")


if __name__ == "__main__":
    main()
