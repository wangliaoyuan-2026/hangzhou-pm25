"""网络请求、CSV 读写等共用工具。"""
import csv
import json
import time
import urllib.error
import urllib.request

from config import USER_AGENT


def http_get(url, headers=None, timeout=60, retries=3):
    """GET 请求，返回 bytes；404 返回 None，其他错误重试后抛出。"""
    h = {"User-Agent": USER_AGENT}
    h.update(headers or {})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt * 2)


def get_json(url, headers=None, timeout=60):
    body = http_get(url, headers, timeout)
    return None if body is None else json.loads(body)


def read_wide_csv(path):
    """读取 date 为首列的宽表：返回 ({date: {col: float|None}}, [列名])。"""
    if not path.exists():
        return {}, []
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return {}, []
    cols = rows[0][1:]
    out = {}
    for r in rows[1:]:
        out[r[0]] = {c: (float(v) if v else None) for c, v in zip(cols, r[1:])}
    return out, cols


def write_wide_csv(path, table, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", *cols])
        for d in sorted(table):
            row = table[d]
            w.writerow([d, *("" if row.get(c) is None else f"{row[c]:.1f}" for c in cols)])


def mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def read_yearly(dirpath, legacy=None):
    """读取按年拆分的宽表目录（dir/2026.csv …），可同时合并旧的单文件。"""
    table, cols = {}, []
    files = sorted(dirpath.glob("*.csv")) if dirpath.exists() else []
    if legacy is not None and legacy.exists():
        files.insert(0, legacy)
    for p in files:
        t, c = read_wide_csv(p)
        table.update(t)
        cols += [x for x in c if x not in cols]
    return table, cols


def write_yearly(dirpath, table, cols, only_years=None):
    """按年写出；only_years 指定时只重写这些年份的文件。"""
    by_year = {}
    for d, row in table.items():
        by_year.setdefault(d[:4], {})[d] = row
    for y, t in by_year.items():
        if only_years is None or y in only_years:
            write_wide_csv(dirpath / f"{y}.csv", t, cols)
