/* 杭州 PM2.5 看板：读取 data/dashboard.json 并绘制全部图表 */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const charts = [];
  let D = null;
  let cnPeriod = "last365";

  const css = () => {
    const s = getComputedStyle(document.documentElement);
    const v = (n) => s.getPropertyValue(n).trim();
    return {
      surface: v("--surface"), ink: v("--ink"), ink2: v("--ink-2"), muted: v("--muted"),
      grid: v("--grid"), axis: v("--axis"), accent: v("--accent"), weak: v("--accent-weak"),
      other: v("--other"), good: v("--good"), bad: v("--bad"),
      series: ["--s1", "--s2", "--s3", "--s4", "--s5"].map(v),
      seq: ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4"].map(v),
    };
  };

  const fmt = (v, d = 1) => (v == null ? "—" : Number(v).toFixed(d));
  const GRADES = [[35, "优"], [75, "良"], [115, "轻度污染"], [150, "中度污染"], [250, "重度污染"], [Infinity, "严重污染"]];
  const grade = (v) => {
    if (v == null) return "";
    const i = GRADES.findIndex(([hi]) => v <= hi);
    return `<span class="grade g${i}">${GRADES[i][1]}</span>`;
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const localTime = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  };

  function base(c) {
    return {
      backgroundColor: "transparent",
      animation: false,
      textStyle: { fontFamily: getComputedStyle(document.body).fontFamily, color: c.ink2 },
      grid: { left: 44, right: 16, top: 24, bottom: 32, containLabel: false },
      tooltip: {
        trigger: "axis", backgroundColor: c.surface, borderColor: c.axis, textStyle: { color: c.ink, fontSize: 12 },
        axisPointer: { type: "line", lineStyle: { color: c.axis } },
      },
    };
  }
  const axisStyle = (c) => ({
    axisLine: { lineStyle: { color: c.axis } }, axisTick: { show: false },
    axisLabel: { color: c.muted, fontSize: 11 }, splitLine: { lineStyle: { color: c.grid } },
  });
  const refLines = (c, items) => ({
    silent: true, symbol: "none",
    lineStyle: { type: "dashed", width: 1, color: c.muted },
    label: { position: "insideEndTop", color: c.ink2, fontSize: 11, formatter: (p) => p.name },
    data: items.map(([y, name]) => ({ yAxis: y, name })),
  });
  const refLinesX = (c, items) => ({
    silent: true, symbol: "none",
    lineStyle: { type: "dashed", width: 1, color: c.muted },
    label: { position: "end", color: c.ink2, fontSize: 11, formatter: (p) => p.name },
    data: items.map(([x, name]) => ({ xAxis: x, name })),
  });

  function emptyState(el, title, body) {
    el.innerHTML = `<div class="empty"><b>${esc(title)}</b><span>${body}</span></div>`;
  }

  function mount(id, option) {
    const el = $(id);
    if (!el) return;
    let ch = echarts.getInstanceByDom(el);
    if (!ch) { el.innerHTML = ""; ch = echarts.init(el, null, { renderer: "svg" }); charts.push(ch); }
    ch.setOption(option, true);
  }

  /* ---------- 概况卡片 ---------- */
  function tiles() {
    const h = D.hz, ch = h.changes || {}, L = D.limits;
    const lh = h.last_hour;
    const delta = (a, b, unit = "") => {
      if (a == null || b == null) return "";
      const d = a - b, pct = b ? (d / b) * 100 : 0;
      const cls = d > 0 ? "up" : "down";
      return `<span class="${cls}">${d > 0 ? "▲" : "▼"} ${Math.abs(pct).toFixed(0)}%</span>${unit}`;
    };
    const r = h.rank;
    const lastYear = h.yearly.filter((y) => !y.partial).slice(-1)[0];
    const cards = [
      {
        k: `最近一天日均 · ${h.last_day || "—"}`,
        v: `${fmt(ch.last)} <small>µg/m³</small> ${grade(ch.last)}`,
        d: ch.prev != null ? `较前一天 ${delta(ch.last, ch.prev)}` : "国控站官方数据",
      },
      {
        k: lh ? `最新小时值 · ${lh[0].slice(5, 10).replace("-", "/")} ${lh[0].slice(11)}时` : "最新小时值",
        v: lh ? `${fmt(lh[1], 0)} <small>µg/m³</small> ${grade(lh[1])}` : "—",
        d: "国控站城市均值，约 1–2 小时延迟",
      },
      {
        k: "近 30 天均值",
        v: `${fmt(ch.m30)} <small>µg/m³</small>`,
        d: ch.m30_last_year != null ? `较去年同期 ${delta(ch.m30, ch.m30_last_year)}` : "去年同期数据回填中",
      },
      r
        ? { k: "全国城市排名 · 近 365 天", v: `第 ${r.rank} <small>/ ${r.total} 城（1 = 最干净）</small>`, d: "按 PM2.5 均值从低到高" }
        : lastYear
          ? { k: `${lastYear.year} 年均`, v: `${fmt(lastYear.mean)} <small>µg/m³</small>`, d: `国标 ${L.cn_annual} · WHO ${L.who_annual}` }
          : { k: "全国城市排名", v: "—", d: "需要至少 300 天数据，历史回填中" },
    ];
    $("tiles").innerHTML = cards.map((c) => `<div class="tile"><span class="k">${c.k}</span><span class="v">${c.v}</span><span class="d">${c.d}</span></div>`).join("");
  }

  /* ---------- 杭州图表 ---------- */
  function hourly(c) {
    const L = D.limits;
    mount("c-hourly", {
      ...base(c),
      xAxis: { type: "time", ...axisStyle(c), splitLine: { show: false } },
      yAxis: { type: "value", name: "µg/m³", nameTextStyle: { color: c.muted, fontSize: 11 }, ...axisStyle(c) },
      tooltip: { ...base(c).tooltip, valueFormatter: (v) => `${fmt(v, 0)} µg/m³` },
      series: [{
        name: "PM2.5", type: "line", showSymbol: false, lineStyle: { width: 2, color: c.accent }, itemStyle: { color: c.accent },
        areaStyle: { color: c.weak, opacity: 0.5 },
        data: D.hz.hourly_7d.map(([t, v]) => [t.replace(" ", "T") + ":00:00+08:00", v]),
        markLine: refLines(c, [[L.cn_24h, `国标日均 ${L.cn_24h}`], [L.who_24h, `WHO 日均 ${L.who_24h}`]]),
      }],
    });
  }

  function daily(c) {
    const L = D.limits, data = D.hz.daily;
    const startIdx = Math.max(0, data.length - 365);
    mount("c-daily", {
      ...base(c),
      grid: { left: 44, right: 16, top: 24, bottom: 64 },
      xAxis: { type: "category", data: data.map((d) => d[0]), ...axisStyle(c), splitLine: { show: false } },
      yAxis: { type: "value", ...axisStyle(c) },
      tooltip: { ...base(c).tooltip, valueFormatter: (v) => `${fmt(v)} µg/m³` },
      dataZoom: [
        { type: "slider", startValue: startIdx, height: 20, bottom: 8, borderColor: c.grid, fillerColor: c.weak + "88",
          textStyle: { color: c.muted }, dataBackground: { lineStyle: { color: c.axis }, areaStyle: { color: c.grid } } },
        { type: "inside", startValue: startIdx },
      ],
      series: [{
        name: "日均", type: "line", showSymbol: false, sampling: "lttb", lineStyle: { width: 1.5, color: c.accent }, itemStyle: { color: c.accent },
        data: data.map((d) => d[1]),
        markLine: refLines(c, [[L.cn_24h, `国标 ${L.cn_24h}`], [L.who_24h, `WHO ${L.who_24h}`]]),
      }],
    });
  }

  function yearly(c) {
    const L = D.limits, ys = D.hz.yearly;
    if (!ys.length) return emptyState($("c-yearly"), "暂无数据", "历史数据回填中。");
    mount("c-yearly", {
      ...base(c),
      tooltip: { ...base(c).tooltip, axisPointer: { type: "shadow", shadowStyle: { color: c.grid + "66" } },
        formatter: (ps) => { const y = ys[ps[0].dataIndex]; return `${y.year} 年<br>均值 <b>${fmt(y.mean)}</b> µg/m³<br>有效 ${y.days} 天${y.partial ? "（不足一年）" : ""}`; } },
      xAxis: { type: "category", data: ys.map((y) => String(y.year)), ...axisStyle(c), splitLine: { show: false } },
      yAxis: { type: "value", ...axisStyle(c) },
      series: [{
        type: "bar", barMaxWidth: 28,
        data: ys.map((y) => ({ value: y.mean, itemStyle: { color: y.partial ? c.weak : c.accent, borderRadius: [4, 4, 0, 0] } })),
        label: { show: true, position: "top", color: c.ink2, fontSize: 11, formatter: (p) => fmt(p.value) },
        markLine: refLines(c, [[L.cn_annual, `国标年均 ${L.cn_annual}`], [L.who_annual, `WHO 年均 ${L.who_annual}`]]),
      }],
    });
  }

  function heat(c) {
    const hm = D.hz.heatmap;
    if (!hm.length) return emptyState($("c-heat"), "暂无数据", "历史数据回填中。");
    const vals = hm.map((x) => x[2]);
    mount("c-heat", {
      ...base(c),
      grid: { left: 44, right: 16, top: 8, bottom: 56 },
      tooltip: { trigger: "item", backgroundColor: c.surface, borderColor: c.axis, textStyle: { color: c.ink, fontSize: 12 },
        formatter: (p) => `${p.value[1] + 1} 月 ${p.value[0]}:00<br>平均 <b>${fmt(p.value[2])}</b> µg/m³` },
      xAxis: { type: "category", data: [...Array(24).keys()].map((h) => `${h}`), ...axisStyle(c), splitLine: { show: false }, name: "时", nameGap: 4, nameTextStyle: { color: c.muted } },
      yAxis: { type: "category", data: [...Array(12).keys()].map((m) => `${m + 1}月`), ...axisStyle(c), splitLine: { show: false } },
      visualMap: { min: Math.floor(Math.min(...vals)), max: Math.ceil(Math.max(...vals)), orient: "horizontal", left: "center", bottom: 0,
        itemHeight: 160, itemWidth: 10, calculable: false, text: ["高", "低"], textStyle: { color: c.muted, fontSize: 11 }, inRange: { color: c.seq } },
      series: [{ type: "heatmap", data: hm.map(([m, h, v]) => [h, m, v]), itemStyle: { borderColor: c.surface, borderWidth: 1 },
        emphasis: { itemStyle: { borderColor: c.ink, borderWidth: 1 } } }],
    });
  }

  function forecast(c) {
    const f = D.forecast;
    if (!f.daily.length) return emptyState($("c-fc"), "暂无预报", "预报数据每小时更新。");
    const useCorr = f.ratio != null;
    $("fc-note").textContent = useCorr
      ? `CAMS 模型按近 30 天实测校正（实测 ÷ 模型 = ${f.ratio}）。`
      : "CAMS 模型原始值，在中国城市通常偏高；实测数据满 14 天后自动校正。";
    const days = f.daily.map((d) => {
      const dt = new Date(d.date + "T00:00:00+08:00");
      return `${dt.getMonth() + 1}/${dt.getDate()} 周${"日一二三四五六"[dt.getDay()]}`;
    });
    const vals = f.daily.map((d) => (useCorr ? d.corrected : d.raw));
    mount("c-fc", {
      ...base(c),
      tooltip: { ...base(c).tooltip, axisPointer: { type: "shadow", shadowStyle: { color: c.grid + "66" } },
        formatter: (ps) => { const d = f.daily[ps[0].dataIndex]; return `${d.date}<br>${useCorr ? `校正后 <b>${fmt(d.corrected)}</b><br>模型原值 ${fmt(d.raw)}` : `模型 <b>${fmt(d.raw)}</b>`} µg/m³`; } },
      xAxis: { type: "category", data: days, ...axisStyle(c), splitLine: { show: false } },
      yAxis: { type: "value", ...axisStyle(c) },
      series: [{
        type: "bar", barMaxWidth: 36,
        data: vals.map((v) => ({ value: v, itemStyle: { color: c.accent, borderRadius: [4, 4, 0, 0] } })),
        label: { show: true, position: "top", color: c.ink2, fontSize: 11, formatter: (p) => fmt(p.value, 0) },
        markLine: refLines(c, [[D.limits.cn_24h, `国标 ${D.limits.cn_24h}`]]),
      }],
    });
  }

  /* ---------- 对比 ---------- */
  function rankBars(id, cities, key, c, refs) {
    const rows = cities.filter((x) => x[key] != null).sort((a, b) => b[key] - a[key]);
    mount(id, {
      ...base(c),
      grid: { left: 64, right: 48, top: 8, bottom: 24 },
      tooltip: { ...base(c).tooltip, axisPointer: { type: "shadow", shadowStyle: { color: c.grid + "66" } }, valueFormatter: (v) => `${fmt(v)} µg/m³` },
      xAxis: { type: "value", ...axisStyle(c) },
      yAxis: { type: "category", data: rows.map((r) => r.name), ...axisStyle(c), splitLine: { show: false },
        axisLabel: { color: c.ink2, fontSize: 12, formatter: (n) => (n === D.home ? `{h|${n}}` : n), rich: { h: { color: c.ink, fontWeight: 700 } } } },
      series: [{
        type: "bar", barMaxWidth: 18,
        data: rows.map((r) => ({ value: r[key], itemStyle: { color: r.name === D.home ? c.accent : c.other, borderRadius: [0, 4, 4, 0] } })),
        label: { show: true, position: "right", color: c.ink2, fontSize: 11, formatter: (p) => fmt(p.value) },
        markLine: refLinesX(c, refs),
      }],
    });
  }

  function cn(c) {
    if (!D.cn || !D.cn.cities.length) return emptyState($("c-cn"), "暂无数据", "国控站数据回填中。");
    const L = D.limits;
    rankBars("c-cn", D.cn.cities, cnPeriod, c, [[L.cn_annual, `国标 ${L.cn_annual}`]]);

    // 长三角各城市年均走势
    const yrd = D.cn.cities.filter((x) => D.yrd.includes(x.name));
    const years = [...new Set(yrd.flatMap((x) => x.yearly.map((y) => y.year)))].sort();
    if (years.length < 2) {
      emptyState($("c-yrd"), "长三角年均走势", "需要至少两年数据，历史回填中。");
    } else {
      mount("c-yrd", {
        ...base(c),
        color: c.series,
        legend: { top: 0, right: 0, textStyle: { color: c.ink2, fontSize: 12 }, itemWidth: 14, itemHeight: 3 },
        grid: { left: 36, right: 56, top: 32, bottom: 24 },
        tooltip: { ...base(c).tooltip, valueFormatter: (v) => `${fmt(v)} µg/m³` },
        xAxis: { type: "category", data: years.map(String), ...axisStyle(c), splitLine: { show: false } },
        yAxis: { type: "value", ...axisStyle(c) },
        series: yrd.map((x) => ({
          name: x.name, type: "line", symbolSize: 8, lineStyle: { width: x.name === D.home ? 3 : 2 },
          data: years.map((y) => (x.yearly.find((r) => r.year === y) || {}).mean ?? null),
          endLabel: { show: true, formatter: "{a}", color: c.ink2, fontSize: 11 },
        })),
      });
    }

    const r = D.hz.rank;
    $("rank").innerHTML = r
      ? `<div><h3>杭州在全国 ${r.total} 个城市中</h3><span class="big">第 ${r.rank} 名</span><p class="hint">近 365 天均值，从低到高排序</p></div>
         <div><h3>最干净的 5 个城市</h3><ol>${r.best.map((x) => `<li>${esc(x.name)}<span>${fmt(x.mean)}</span></li>`).join("")}</ol></div>
         <div><h3>浓度最高的 5 个城市</h3><ol>${r.worst.slice().reverse().map((x) => `<li>${esc(x.name)}<span>${fmt(x.mean)}</span></li>`).join("")}</ol></div>`
      : `<p class="hint">全国排名需要至少 300 天数据，历史回填完成后显示。</p>`;
  }

  function intl(c) {
    const el = $("c-intl");
    if (!D.intl || D.intl.cities.length < 2) {
      $("intl-note").textContent = "";
      return emptyState(el, "国外城市实测数据尚未接入",
        "在 GitHub 仓库的 Settings → Secrets 中添加 <code>OPENAQ_API_KEY</code>（在 explore.openaq.org 免费注册获取），下次更新后自动显示。");
    }
    $("intl-note").textContent = `近 365 天均值。杭州为国控站数据，国外城市为 ${D.intl.source}。`;
    rankBars("c-intl", D.intl.cities, "last365", c, [[D.limits.who_annual, `WHO ${D.limits.who_annual}`], [D.limits.cn_annual, `国标 ${D.limits.cn_annual}`]]);
  }

  function okTable() {
    const rows = [...(D.cn ? D.cn.cities : []), ...(D.intl ? D.intl.cities.filter((x) => x.name !== D.home) : [])]
      .filter((x) => x.days365 > 0)
      .map((x) => ({ ...x, cnPct: (x.cn_ok365 / x.days365) * 100, whoPct: (x.who_ok365 / x.days365) * 100 }))
      .sort((a, b) => b.whoPct - a.whoPct);
    if (!rows.length) { $("t-ok").innerHTML = `<tr><td>数据回填中</td></tr>`; return; }
    const intlNames = new Set(D.intl ? D.intl.cities.map((x) => x.name) : []);
    $("t-ok").innerHTML = `<thead><tr><th>城市</th><th class="n">有效天数</th><th class="n">国标达标</th><th class="n">WHO 达标</th><th>数据来源</th></tr></thead><tbody>` +
      rows.map((x) => `<tr class="${x.name === D.home ? "home" : ""}"><td>${esc(x.name)}</td><td class="n">${x.days365}</td>
        <td class="n">${x.cnPct.toFixed(0)}%</td>
        <td class="n">${x.whoPct.toFixed(0)}%<span class="bar" style="width:${(x.whoPct * 0.6).toFixed(0)}px"></span></td>
        <td class="src">${intlNames.has(x.name) && x.name !== D.home ? "OpenAQ" : "国控站"}</td></tr>`).join("") + "</tbody>";
  }

  function liveTable() {
    const entries = Object.entries(D.live || {});
    $("live-note").textContent = D.live_generated ? `更新于 ${localTime(D.live_generated)}（北京时间）` : "";
    if (!entries.length) { $("t-live").innerHTML = `<tr><td>暂无实时数据</td></tr>`; return; }
    $("t-live").innerHTML = `<thead><tr><th>城市</th><th class="n">PM2.5</th><th>等级</th><th>来源</th><th>观测时间</th></tr></thead><tbody>` +
      entries.map(([name, v]) => `<tr class="${name === D.home ? "home" : ""}"><td>${esc(name)}</td><td class="n">${v ? fmt(v.pm25) : "—"}</td>
        <td>${v ? grade(v.pm25) : ""}</td><td class="src">${v ? esc(v.source) + (v.note ? " · " + esc(v.note) : "") : "待接入 WAQI / OpenAQ"}</td>
        <td class="src">${v ? esc(String(v.time).replace("T", " ").slice(0, 16)) : "—"}</td></tr>`).join("") + "</tbody>";
  }

  function stations() {
    const st = D.stations || [];
    $("stations-block").hidden = !st.length;
    if (!st.length) return;
    $("t-st").innerHTML = `<thead><tr><th>站点</th><th class="n">PM2.5</th><th>等级</th><th>观测时间</th></tr></thead><tbody>` +
      st.sort((a, b) => b.pm25 - a.pm25).map((s) => `<tr><td>${esc(s.name)}</td><td class="n">${fmt(s.pm25)}</td><td>${grade(s.pm25)}</td>
        <td class="src">${esc(String(s.time).replace("T", " ").slice(0, 16))}</td></tr>`).join("") + "</tbody>";
  }

  function render() {
    const c = css();
    tiles(); hourly(c); daily(c); yearly(c); heat(c); forecast(c); cn(c); intl(c); okTable(); liveTable(); stations();
  }

  function rerenderCharts() {
    charts.splice(0).forEach((ch) => ch.dispose());
    render();
  }

  document.querySelectorAll("#cn-period button").forEach((b) =>
    b.addEventListener("click", () => {
      cnPeriod = b.dataset.k;
      document.querySelectorAll("#cn-period button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      cn(css());
    }));
  window.addEventListener("resize", () => charts.forEach((ch) => ch.resize()));
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rerenderCharts);
  new MutationObserver(rerenderCharts).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  fetch("data/dashboard.json", { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => {
      D = d;
      $("updated").textContent = `数据更新于 ${localTime(d.generated)}（北京时间）· 官方数据截至 ${d.hz.last_day || "—"}`;
      render();
    })
    .catch((e) => { $("updated").textContent = `数据加载失败（${e.message}），请稍后刷新。`; });
})();
