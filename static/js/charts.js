/* ============================================================
   charts.js —— 图表模块（成员I）
   数据来源：stats.html 里 <script id="chart-data"> 的 JSON
   挂载点：#chart-cat（支出构成饼图）/#chart-bar（收入构成柱状图）
           #chart-month（月度趋势折线图）
   说明：ECharts 没加载成功时直接返回，页面保留模板里的 CSS 条形图兜底。
   ============================================================ */
(function () {
  "use strict";

  var dataNode = document.getElementById("chart-data");
  if (!dataNode || !window.echarts) return;

  var data;
  try {
    data = JSON.parse(dataNode.textContent);
  } catch (err) {
    return;
  }

  var INK = "#3b4642";
  var MUTED = "#8a9a91";
  var LINE = "#e6e8e2";
  var INCOME = "#2c7a5b";
  var EXPENSE = "#b23c2e";
  var NUM_FONT = '"Consolas", "Menlo", monospace';
  var TEXT_FONT = '"Microsoft YaHei", "PingFang SC", sans-serif';

  var charts = [];

  var BASE_TEXT = {
    fontFamily: TEXT_FONT,
    color: INK,
    fontSize: 11
  };

  var TOOLTIP = {
    backgroundColor: "rgba(255,255,255,.96)",
    borderColor: LINE,
    borderWidth: 1,
    padding: [8, 10],
    textStyle: { color: INK, fontSize: 12, fontFamily: TEXT_FONT },
    extraCssText: "box-shadow:0 6px 18px rgba(31,42,36,.10);border-radius:2px;"
  };

  /* 把面板里的 CSS 图换成 ECharts 画布，返回画布元素 */
  function prepare(panelId) {
    var panel = document.getElementById(panelId);
    if (!panel) return null;
    var body = panel.querySelector(".chart-body");
    if (!body) return null;
    body.innerHTML = '<div class="echart-box" role="img"></div>';
    return body.firstChild;
  }

  function emptyBox(box, text) {
    box.innerHTML =
      '<p style="margin:0;padding:56px 0 0;text-align:center;font-size:13px;color:' +
      MUTED + '">' + text + "</p>";
  }

  /* ---------------- 1. 支出构成：环形饼图 ---------------- */
  function drawPie(rows) {
    var box = prepare("chart-cat");
    if (!box) return;

    var items = rows
      .filter(function (r) { return r.type === "expense" && r.amount > 0; })
      .sort(function (a, b) { return b.amount - a.amount; });

    if (!items.length) {
      emptyBox(box, "这段时间没有支出");
      return;
    }

    var chart = echarts.init(box, null, { renderer: "canvas" });
    chart.setOption({
      color: items.map(function (it) { return it.color; }),
      textStyle: BASE_TEXT,
      tooltip: Object.assign({}, TOOLTIP, {
        trigger: "item",
        formatter: function (p) {
          var it = items[p.dataIndex];
          return "<b>" + it.name + "</b><br/>" +
            '<span style="font-family:' + NUM_FONT + '">' +
            it.amount.toFixed(2) + "</span> 元 · " + it.count + " 笔 · " +
            (it.ratio * 100).toFixed(1) + "%";
        }
      }),
      legend: {
        orient: "vertical",
        right: 4,
        top: "center",
        itemWidth: 8,
        itemHeight: 8,
        itemGap: 10,
        icon: "circle",
        textStyle: { color: INK, fontSize: 11, fontFamily: TEXT_FONT },
        formatter: function (name) { return name.length > 5 ? name.slice(0, 5) : name; }
      },
      series: [{
        type: "pie",
        radius: ["44%", "70%"],
        center: ["34%", "52%"],
        avoidLabelOverlap: true,
        minAngle: 3,
        itemStyle: { borderColor: "#fff", borderWidth: 1.5 },
        label: { show: false },
        labelLine: { show: false },
        emphasis: {
          scaleSize: 4,
          label: {
            show: true,
            fontSize: 12,
            fontWeight: "bold",
            color: INK,
            formatter: "{b}\n{d}%"
          }
        },
        data: items.map(function (it) {
          return { name: it.name, value: it.amount };
        })
      }]
    });
    charts.push(chart);
  }

  /* ---------------- 2. 收入构成：柱状图 ---------------- */
  function drawBar(rows) {
    var box = prepare("chart-bar");
    if (!box) return;

    var items = rows
      .filter(function (r) { return r.type === "income" && r.amount > 0; })
      .sort(function (a, b) { return b.amount - a.amount; })
      .slice(0, 6);

    if (!items.length) {
      emptyBox(box, "这段时间没有收入");
      return;
    }

    var chart = echarts.init(box, null, { renderer: "canvas" });
    chart.setOption({
      textStyle: BASE_TEXT,
      grid: { left: 6, right: 10, top: 26, bottom: 4, containLabel: true },
      tooltip: Object.assign({}, TOOLTIP, {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: "rgba(44,122,91,.06)" } },
        formatter: function (ps) {
          var it = items[ps[0].dataIndex];
          return "<b>" + it.name + "</b><br/>" +
            '<span style="font-family:' + NUM_FONT + '">' +
            it.amount.toFixed(2) + "</span> 元 · " + it.count + " 笔";
        }
      }),
      xAxis: {
        type: "category",
        data: items.map(function (it) { return it.name; }),
        axisLine: { lineStyle: { color: LINE } },
        axisTick: { show: false },
        axisLabel: { color: INK, fontSize: 11, margin: 8 }
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: LINE, type: "dashed" } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: MUTED,
          fontSize: 10,
          fontFamily: NUM_FONT,
          formatter: function (v) { return v >= 1000 ? (v / 1000) + "k" : v; }
        }
      },
      series: [{
        type: "bar",
        barWidth: "46%",
        itemStyle: {
          color: function (p) { return items[p.dataIndex].color || INCOME; },
          borderRadius: [2, 2, 0, 0]
        },
        label: {
          show: true,
          position: "top",
          distance: 4,
          color: MUTED,
          fontSize: 10,
          fontFamily: NUM_FONT,
          formatter: function (p) { return p.value.toFixed(0); }
        },
        data: items.map(function (it) { return it.amount; })
      }]
    });
    charts.push(chart);
  }

  /* ---------------- 3. 月度趋势：双折线 ---------------- */
  function drawTrend(months) {
    var box = prepare("chart-month");
    if (!box) return;

    if (!months.length) {
      emptyBox(box, "还没有跨月的记录");
      return;
    }

    var chart = echarts.init(box, null, { renderer: "canvas" });
    chart.setOption({
      color: [INCOME, EXPENSE],
      textStyle: BASE_TEXT,
      legend: {
        right: 4,
        top: 0,
        itemWidth: 12,
        itemHeight: 8,
        itemGap: 14,
        textStyle: { color: INK, fontSize: 11, fontFamily: TEXT_FONT },
        data: ["收入", "支出"]
      },
      grid: { left: 6, right: 10, top: 34, bottom: 4, containLabel: true },
      tooltip: Object.assign({}, TOOLTIP, {
        trigger: "axis",
        axisPointer: { type: "line", lineStyle: { color: "#c9cfc6", width: 1 } },
        formatter: function (ps) {
          var m = months[ps[0].dataIndex];
          var net = (m.income || 0) - (m.expense || 0);
          return "<b>" + m.month + "</b><br/>收入 " +
            '<span style="font-family:' + NUM_FONT + '">' + (m.income || 0).toFixed(2) + "</span><br/>支出 " +
            '<span style="font-family:' + NUM_FONT + '">' + (m.expense || 0).toFixed(2) + "</span><br/>结余 " +
            '<span style="font-family:' + NUM_FONT + '">' + net.toFixed(2) + "</span>";
        }
      }),
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: months.map(function (m) { return m.month; }),
        axisLine: { lineStyle: { color: LINE } },
        axisTick: { show: false },
        axisLabel: { color: INK, fontSize: 11, margin: 8 }
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: LINE, type: "dashed" } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: MUTED,
          fontSize: 10,
          fontFamily: NUM_FONT,
          formatter: function (v) { return v >= 1000 ? (v / 1000) + "k" : v; }
        }
      },
      series: [
        {
          name: "收入",
          type: "line",
          smooth: false,
          symbol: "circle",
          symbolSize: 5,
          lineStyle: { width: 2 },
          itemStyle: { color: INCOME },
          emphasis: { focus: "series" },
          data: months.map(function (m) { return +(m.income || 0).toFixed(2); })
        },
        {
          name: "支出",
          type: "line",
          smooth: false,
          symbol: "circle",
          symbolSize: 5,
          lineStyle: { width: 2 },
          itemStyle: { color: EXPENSE },
          emphasis: { focus: "series" },
          data: months.map(function (m) { return +(m.expense || 0).toFixed(2); })
        }
      ]
    });
    charts.push(chart);
  }

  function drawAll() {
    charts.forEach(function (c) { c.dispose(); });
    charts = [];
    var rows = data.by_category || [];
    var months = data.by_month || [];
    drawPie(rows);
    drawBar(rows);
    drawTrend(months);
  }

  drawAll();

  /* 窗口变化后重排，避免图表被压扁或留白 */
  var timer = null;
  window.addEventListener("resize", function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      charts.forEach(function (c) { c.resize(); });
    }, 120);
  });
})();
