# 杭州 PM2.5 看板

监测杭州 PM2.5 浓度，并与国内、国外主要城市对比。数据全部来自免费来源，由 GitHub Actions 每小时自动更新，发布在 GitHub Pages 上。

## 数据来源

| 内容 | 来源 | 更新频率 | 是否需要 Key |
|---|---|---|---|
| 杭州及全国城市逐小时、日均 | 中国环境监测总站国控站（[quotsoft.net](https://quotsoft.net/air/) 镜像），2016 年起 | 每小时 | 否 |
| 国外城市实测日均 | [OpenAQ](https://openaq.org) v3 | 每天 | `OPENAQ_API_KEY` |
| 国外城市实时、杭州各监测站 | [WAQI](https://aqicn.org/api/) | 每小时 | `WAQI_TOKEN` |
| 未来 5 天预报 | [Open-Meteo](https://open-meteo.com/en/docs/air-quality-api)（CAMS 模型） | 每小时 | 否 |

口径说明：
- 所有对比都用 PM2.5 浓度（µg/m³），不用 AQI。中美 AQI 分段不同，不能直接比较。
- 日均值至少需要 20 个有效小时，年均值至少需要 324 个有效日（GB 3095）。
- WAQI 返回的是美国 AQI 分指数，脚本会反算为浓度（见 `scripts/fetch_live.py`）。
- CAMS 模型在中国城市明显偏高（实测约为模型值的 0.5 倍），因此只用于预报，并按近 30 天实测/模型比值校正。

## 目录结构

```
scripts/
  config.py            城市列表、数据源地址、标准限值
  update_cn.py         国控站数据 → data/cn_daily/、data/hz_hourly/、data/cn_latest.json
  update_model.py      Open-Meteo 模型 → data/om_daily.csv、data/om_forecast.json
  update_intl.py       OpenAQ 实测 → data/intl_daily.csv
  fetch_live.py        WAQI / OpenAQ 实时读数 → data/live.json
  build_site_data.py   汇总 → site/data/dashboard.json
site/                  静态看板（ECharts）
data/                  历史数据（每天由 Actions 提交一次）
.github/workflows/update.yml
```

只用 Python 标准库，不需要安装依赖。

## 本地运行

```bash
python3 scripts/update_cn.py --days 3
python3 scripts/update_model.py
python3 scripts/fetch_live.py
python3 scripts/build_site_data.py
python3 -m http.server 8765 --directory site
```

首次回填历史数据（镜像站下载较慢，全量约需 10 小时，可中断后续传）：

```bash
python3 scripts/update_cn.py --start 2016-01-01 --workers 6
python3 scripts/update_model.py --full
OPENAQ_API_KEY=xxx python3 scripts/update_intl.py --start 2016-01-01
```

## 接入 WAQI 和 OpenAQ

1. WAQI：在 <https://aqicn.org/data-platform/token/> 申请 token。
2. OpenAQ：在 <https://explore.openaq.org> 注册，在账户设置里生成 API Key。
3. 在 GitHub 仓库 **Settings → Secrets and variables → Actions** 中添加 `WAQI_TOKEN` 和 `OPENAQ_API_KEY`。
4. 在 **Actions** 页面手动运行一次“更新数据并发布看板”。国外城市历史数据需要在本地用上面的回填命令跑一次。

## 自动更新

`.github/workflows/update.yml` 每小时运行一次：拉取最新数据，重新生成看板，发布到 GitHub Pages。北京时间 03 点那次还会把数据提交回仓库。
