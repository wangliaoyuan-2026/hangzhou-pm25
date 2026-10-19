"""看板用到的城市、数据源地址和标准限值。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / ".cache"
SITE_DATA = ROOT / "site" / "data"

HOME_CITY = "杭州"

# 国内对比城市（名称需与国控站城市数据 CSV 的列名一致）
CN_CITIES = {
    "杭州": (30.27, 120.15),
    "北京": (39.90, 116.40),
    "上海": (31.23, 121.47),
    "广州": (23.13, 113.26),
    "深圳": (22.54, 114.06),
    "成都": (30.66, 104.07),
    "西安": (34.26, 108.94),
    "武汉": (30.59, 114.31),
    "南京": (32.06, 118.80),
    "苏州": (31.30, 120.59),
    "宁波": (29.87, 121.54),
}
YRD = ["杭州", "上海", "南京", "苏州", "宁波"]  # 长三角分组

# 国际对比城市：(纬度, 经度, 英文名，用于 WAQI/OpenAQ 查询)
INTL_CITIES = {
    "东京": (35.68, 139.69, "tokyo"),
    "首尔": (37.57, 126.98, "seoul"),
    "新加坡": (1.35, 103.82, "singapore"),
    "曼谷": (13.76, 100.50, "bangkok"),
    "新德里": (28.61, 77.21, "delhi"),
    "伦敦": (51.51, -0.13, "london"),
    "巴黎": (48.86, 2.35, "paris"),
    "纽约": (40.71, -74.01, "new-york"),
    "洛杉矶": (34.05, -118.24, "los-angeles"),
    "悉尼": (-33.87, 151.21, "sydney"),
}

# 国控站数据镜像（王晓磊整理，源自中国环境监测总站）
CNEMC_CITY_URL = "https://quotsoft.net/air/data/china_cities_{ymd}.csv"
CNEMC_START = "2016-01-01"

OPEN_METEO_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
OPEN_METEO_START = "2022-08-01"  # CAMS 全球数据在 Open-Meteo 上的起始日
WAQI_URL = "https://api.waqi.info"
OPENAQ_URL = "https://api.openaq.org/v3"

# PM2.5 限值（µg/m³）
LIMITS = {
    "who_annual": 5, "who_24h": 15,
    "cn_annual": 35, "cn_24h": 75,
    "us_annual": 9,
}

# 中国 PM2.5 24 小时浓度分级（HJ 633）
CN_GRADES = [
    (35, "优"), (75, "良"), (115, "轻度污染"),
    (150, "中度污染"), (250, "重度污染"), (float("inf"), "严重污染"),
]

# GB 3095：日均值至少需要 20 个有效小时
MIN_HOURS_PER_DAY = 20

USER_AGENT = "hangzhou-pm25-dashboard/1.0 (+https://github.com)"
