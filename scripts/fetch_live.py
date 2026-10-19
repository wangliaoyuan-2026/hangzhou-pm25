"""拉取各城市当前 PM2.5，写入 data/live.json。

来源优先级：
  国内城市：WAQI（转发国控站实测）→ Open-Meteo 模型
  国外城市：OpenAQ（官方实测）→ WAQI → Open-Meteo 模型
WAQI_TOKEN / OPENAQ_API_KEY 未设置时自动跳过对应来源。
"""
import json
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

from common import get_json, mean
from config import CN_CITIES, DATA, HOME_CITY, INTL_CITIES, OPEN_METEO_URL, OPENAQ_URL, WAQI_URL

LIVE_JSON = DATA / "live.json"
WAQI_TOKEN = os.environ.get("WAQI_TOKEN", "").strip()
OPENAQ_KEY = os.environ.get("OPENAQ_API_KEY", "").strip()

# WAQI 的 iaqi.pm25 是美国 AQI 分指数，不是浓度。
# 这里按 EPA 2012 年分段表反算（WAQI 长期沿用此表）；若 WAQI 改用 2024 新表，需同步修改。
US_AQI_PM25 = [
    (0, 50, 0.0, 12.0), (51, 100, 12.1, 35.4), (101, 150, 35.5, 55.4),
    (151, 200, 55.5, 150.4), (201, 300, 150.5, 250.4), (301, 500, 250.5, 500.4),
]
# 杭州主城区范围（纬度1, 经度1, 纬度2, 经度2），用于查找 WAQI 站点
HZ_BOUNDS = "30.05,119.90,30.50,120.45"
STALE_HOURS = 3


def aqi_to_ugm3(aqi):
    for ilo, ihi, clo, chi in US_AQI_PM25:
        if aqi <= ihi:
            return round(clo + (aqi - ilo) * (chi - clo) / (ihi - ilo), 1)
    return 500.4


def waqi_feed(path):
    res = get_json(f"{WAQI_URL}/feed/{path}/?token={WAQI_TOKEN}", timeout=30)
    if not res or res.get("status") != "ok":
        return None
    d = res["data"]
    aqi = d.get("iaqi", {}).get("pm25", {}).get("v")
    if aqi is None:
        return None
    return {"pm25": aqi_to_ugm3(aqi), "time": d["time"]["iso"], "name": d["city"]["name"]}


def waqi_city(lat, lon):
    r = waqi_feed(f"geo:{lat};{lon}")
    return r and {"pm25": r["pm25"], "time": r["time"], "source": "WAQI", "note": r["name"]}


def waqi_hz_stations():
    res = get_json(f"{WAQI_URL}/map/bounds/?latlng={HZ_BOUNDS}&networks=all&token={WAQI_TOKEN}", timeout=30)
    if not res or res.get("status") != "ok":
        return []
    out = []
    for st in res["data"]:
        r = waqi_feed(f"@{st['uid']}")
        if r:
            out.append({"name": st["station"]["name"], "lat": st["lat"], "lon": st["lon"],
                        "pm25": r["pm25"], "time": r["time"]})
    return out


def openaq_city(lat, lon):
    h = {"X-API-Key": OPENAQ_KEY}
    q = urllib.parse.urlencode({"coordinates": f"{lat},{lon}", "radius": 25000,
                                "parameters_id": 2, "limit": 50})
    locs = get_json(f"{OPENAQ_URL}/locations?{q}", headers=h, timeout=30)
    if not locs:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_HOURS)
    vals, latest = [], None
    for loc in locs.get("results", []):
        pm_sensors = {s["id"] for s in loc.get("sensors", []) if s["parameter"]["id"] == 2}
        if not pm_sensors:
            continue
        res = get_json(f"{OPENAQ_URL}/locations/{loc['id']}/latest", headers=h, timeout=30) or {}
        for m in res.get("results", []):
            t = datetime.fromisoformat(m["datetime"]["utc"].replace("Z", "+00:00"))
            if m["sensorsId"] in pm_sensors and t >= cutoff and 0 <= m["value"] < 1000:
                vals.append(m["value"])
                latest = max(latest or t, t)
    if not vals:
        return None
    return {"pm25": round(mean(vals), 1), "time": latest.isoformat(), "source": "OpenAQ",
            "note": f"{len(vals)} 个站点均值"}


def model_current(cities):
    names = list(cities)
    q = urllib.parse.urlencode({
        "latitude": ",".join(str(cities[n][0]) for n in names),
        "longitude": ",".join(str(cities[n][1]) for n in names),
        "current": "pm2_5", "timezone": "auto",
    })
    res = get_json(f"{OPEN_METEO_URL}?{q}", timeout=60)
    res = res if isinstance(res, list) else [res]
    return {n: {"pm25": r["current"]["pm2_5"], "time": r["current"]["time"] + r["timezone_abbreviation"].replace("GMT", ""),
                "source": "Open-Meteo 模型", "note": ""}
            for n, r in zip(names, res)}


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # 单个来源失败不影响整体
        print(f"  {fn.__name__}{args} 失败：{e}")
        return None


def main():
    coords = {n: (lat, lon) for n, (lat, lon) in CN_CITIES.items()}
    coords.update({n: (lat, lon) for n, (lat, lon, _) in INTL_CITIES.items()})
    model = safe(model_current, coords) or {}

    cities = {}
    for name, (lat, lon) in coords.items():
        domestic = name in CN_CITIES
        r = None
        if OPENAQ_KEY and not domestic:
            r = safe(openaq_city, lat, lon)
        if not r and WAQI_TOKEN:
            r = safe(waqi_city, lat, lon)
        cities[name] = r or model.get(name)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "sources": {"waqi": bool(WAQI_TOKEN), "openaq": bool(OPENAQ_KEY)},
        "cities": cities,
        "stations": (safe(waqi_hz_stations) or []) if WAQI_TOKEN else [],
    }
    LIVE_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    srcs = {}
    for v in cities.values():
        if v:
            srcs[v["source"]] = srcs.get(v["source"], 0) + 1
    print(f"实时数据：{srcs}；{HOME_CITY}站点 {len(out['stations'])} 个")


if __name__ == "__main__":
    main()
