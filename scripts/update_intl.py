"""从 OpenAQ 拉取国外对比城市的 PM2.5 实测日均，更新 data/intl_daily.csv。需要环境变量 OPENAQ_API_KEY。

每个城市取市中心 25 km 内、最近仍在上报的 PM2.5 传感器（最多 8 个），城市日均 = 各传感器日均的平均。

用法：
  python scripts/update_intl.py --days 10          # 日常更新
  python scripts/update_intl.py --start 2016-01-01 # 首次回填
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from common import get_json, read_wide_csv, write_wide_csv
from config import DATA, INTL_CITIES, OPENAQ_URL

DAILY_CSV = DATA / "intl_daily.csv"
SENSORS_JSON = DATA / "openaq_sensors.json"
KEY = os.environ.get("OPENAQ_API_KEY", "").strip()
MAX_SENSORS = 8
MIN_COVERAGE = 75  # 当天有效小时占比（%）不足则丢弃


def api(path, **params):
    time.sleep(1.1)  # 免费额度 60 次/分钟
    url = f"{OPENAQ_URL}{path}?{urllib.parse.urlencode(params)}"
    return get_json(url, headers={"X-API-Key": KEY}, timeout=60) or {}


def find_sensors(lat, lon):
    res = api("/locations", coordinates=f"{lat},{lon}", radius=25000, parameters_id=2, limit=100)
    recent = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    picked = []
    for loc in res.get("results", []):
        last = (loc.get("datetimeLast") or {}).get("utc") or ""
        if last < recent:
            continue
        for s in loc.get("sensors", []):
            if s["parameter"]["id"] == 2:
                picked.append({"id": s["id"], "location": loc["name"], "distance": loc.get("distance") or 0})
    picked.sort(key=lambda s: s["distance"])
    return picked[:MAX_SENSORS]


def sensor_days(sid, start, end):
    out, page = {}, 1
    while True:
        res = api(f"/sensors/{sid}/days", datetime_from=start.isoformat(), datetime_to=(end + timedelta(1)).isoformat(),
                  limit=1000, page=page)
        rows = res.get("results", [])
        for r in rows:
            cov = (r.get("coverage") or {}).get("percentComplete", 100)
            d = r["period"]["datetimeFrom"]["local"][:10]
            if cov >= MIN_COVERAGE and r["value"] is not None and 0 <= r["value"] < 1000:
                out[d] = r["value"]
        if len(rows) < 1000:
            return out
        page += 1


def main():
    if not KEY:
        print("未设置 OPENAQ_API_KEY，跳过国外城市实测数据")
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--start")
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--refresh-sensors", action="store_true")
    a = ap.parse_args()

    today = datetime.now(timezone.utc).date()
    start = date.fromisoformat(a.start) if a.start else today - timedelta(days=a.days)

    sensors = json.loads(SENSORS_JSON.read_text()) if SENSORS_JSON.exists() else {}
    for name, (lat, lon, _) in INTL_CITIES.items():
        if a.refresh_sensors or not sensors.get(name):
            sensors[name] = find_sensors(lat, lon)
    SENSORS_JSON.write_text(json.dumps(sensors, ensure_ascii=False, indent=1))

    table, cols = read_wide_csv(DAILY_CSV)
    cols = list(dict.fromkeys([*cols, *INTL_CITIES]))
    for name, lst in sensors.items():
        per_day = defaultdict(list)
        for s in lst:
            try:
                for d, v in sensor_days(s["id"], start, today).items():
                    per_day[d].append(v)
            except Exception as e:
                print(f"  {name} 传感器 {s['id']} 失败：{e}")
        for d, vals in per_day.items():
            table.setdefault(d, {})[name] = round(sum(vals) / len(vals), 1)
        print(f"  {name}：{len(lst)} 个传感器，{len(per_day)} 天")
    write_wide_csv(DAILY_CSV, table, cols)
    print(f"OpenAQ：{start} ~ {today}，intl_daily 共 {len(table)} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
