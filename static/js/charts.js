(function (global) {
  'use strict';

  if (typeof global.Chart === 'undefined') {
    throw new Error('LedgerCharts 需要先加载 Chart.js 4.x');
  }

  const DEFAULT_COLORS = [
    '#f97316', '#3b82f6', '#a855f7', '#ec4899', '#eab308',
    '#14b8a6', '#f43f5e', '#6366f1', '#84cc16', '#06b6d4',
    '#8b5cf6', '#ef4444'
  ];

  const INCOME_COLOR = '#10b981';
  const EXPENSE_COLOR = '#ef4444';

  const state = {
    mode: 'records',
    records: [],
    categories: [],
    stats: null,
    colorMap: new Map(),
    currency: '¥'
  };

  const chartByCanvas = new WeakMap();

  function toNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  function round2(value) {
    return Math.round((toNumber(value) + Number.EPSILON) * 100) / 100;
  }

  function normalizeRecord(raw) {
    const record = raw || {};
    return {
      id: String(record.id == null ? '' : record.id),
      date: String(record.date == null ? '' : record.date).slice(0, 10),
      type: record.type === 'income' ? 'income' : 'expense',
      amount: Math.abs(toNumber(record.amount)),
      category: String(record.category == null || record.category === '' ? '未分类' : record.category),
      note: String(record.note == null ? '' : record.note)
    };
  }

  function buildColorMap(categories) {
    const map = new Map();
    let index = 0;
    (Array.isArray(categories) ? categories : []).forEach(function (item) {
      if (!item || !item.name) return;
      map.set(String(item.name), item.color || DEFAULT_COLORS[index++ % DEFAULT_COLORS.length]);
    });
    return map;
  }

  function colorOf(name) {
    const key = String(name || '未分类');
    if (!state.colorMap.has(key)) {
      state.colorMap.set(key, DEFAULT_COLORS[state.colorMap.size % DEFAULT_COLORS.length]);
    }
    return state.colorMap.get(key);
  }

  function formatMoney(value) {
    const n = round2(value);
    const text = Math.abs(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (n < 0 ? '-' : '') + state.currency + text;
  }

  function formatCompact(value) {
    const n = toNumber(value);
    const sign = n < 0 ? '-' : '';
    const abs = Math.abs(n);
    if (abs >= 10000) return sign + state.currency + (abs / 10000).toFixed(1) + '万';
    if (abs >= 1000) return sign + state.currency + (abs / 1000).toFixed(1) + 'k';
    return sign + state.currency + abs;
  }

  function aggregateOverview(records) {
    const result = { income: 0, expense: 0, balance: 0 };
    (Array.isArray(records) ? records : []).forEach(function (record) {
      const item = normalizeRecord(record);
      if (item.type === 'income') result.income += item.amount;
      else result.expense += item.amount;
    });
    result.income = round2(result.income);
    result.expense = round2(result.expense);
    result.balance = round2(result.income - result.expense);
    return result;
  }

  function aggregateByCategory(records, type) {
    const targetType = type === 'income' ? 'income' : 'expense';
    const map = new Map();
    (Array.isArray(records) ? records : []).forEach(function (record) {
      const item = normalizeRecord(record);
      if (item.type !== targetType) return;
      map.set(item.category, (map.get(item.category) || 0) + item.amount);
    });
    return Array.from(map.entries())
      .map(function (entry) {
        return {
          category: entry[0],
          amount: round2(entry[1]),
          color: colorOf(entry[0])
        };
      })
      .sort(function (a, b) { return b.amount - a.amount; });
  }

  function aggregateByMonth(records) {
    const map = new Map();
    (Array.isArray(records) ? records : []).forEach(function (raw) {
      const record = normalizeRecord(raw);
      if (!/^\d{4}-\d{2}/.test(record.date)) return;
      const month = record.date.slice(0, 7);
      if (!map.has(month)) map.set(month, { income: 0, expense: 0 });
      map.get(month)[record.type] += record.amount;
    });
    return Array.from(map.entries())
      .sort(function (a, b) { return a[0].localeCompare(b[0]); })
      .map(function (entry) {
        return {
          month: entry[0],
          income: round2(entry[1].income),
          expense: round2(entry[1].expense)
        };
      });
  }

  function filterByDateRange(records, start, end) {
    const from = start ? String(start).slice(0, 10) : '';
    const to = end ? String(end).slice(0, 10) : '';
    return (Array.isArray(records) ? records : []).filter(function (raw) {
      const date = normalizeRecord(raw).date;
      if (!date) return false;
      if (from && date < from) return false;
      if (to && date > to) return false;
      return true;
    });
  }

  function unwrapStats(payload) {
    const raw = payload || {};
    if (raw.data && typeof raw.data === 'object' &&
        (raw.code !== undefined || raw.data.summary || raw.data.by_category)) {
      return raw.data;
    }
    return raw;
  }

  function normalizeSummary(raw) {
    const source = raw || {};
    const income = round2(source.total_income != null ? source.total_income : source.income);
    const expense = round2(source.total_expense != null ? source.total_expense : source.expense);
    return {
      income: income,
      expense: expense,
      balance: source.balance != null ? round2(source.balance) : round2(income - expense),
      count: Number(source.count) || 0
    };
  }

  function normalizeCategoryRows(rows) {
    return (Array.isArray(rows) ? rows : []).map(function (row) {
      const item = row || {};
      const name = String(item.category == null || item.category === '' ? '未分类' : item.category);
      return {
        category: name,
        amount: round2(item.amount),
        count: Number(item.count) || 0,
        color: colorOf(name)
      };
    }).sort(function (a, b) { return b.amount - a.amount; });
  }

  function normalizeMonthRows(rows) {
    return (Array.isArray(rows) ? rows : []).map(function (row) {
      const item = row || {};
      return {
        month: String(item.month == null ? '' : item.month).slice(0, 7),
        income: round2(item.income),
        expense: round2(item.expense),
        balance: item.balance != null ? round2(item.balance) : round2(toNumber(item.income) - toNumber(item.expense))
      };
    }).filter(function (row) {
      return /^\d{4}-\d{2}$/.test(row.month);
    }).sort(function (a, b) {
      return a.month.localeCompare(b.month);
    });
  }

  function currentOverview() {
    if (state.mode === 'stats' && state.stats) return state.stats.summary;
    return aggregateOverview(state.records);
  }

  function currentCategoryRows(type) {
    if (state.mode === 'stats' && state.stats) {
      return state.stats.byCategory[type] || [];
    }
    return aggregateByCategory(state.records, type);
  }

  function currentMonthRows() {
    if (state.mode === 'stats' && state.stats) return state.stats.byMonth;
    return aggregateByMonth(state.records);
  }

  function resolveCanvas(target) {
    let element = target;
    if (typeof element === 'string') element = document.querySelector(element);
    if (!element) return null;
    if (element instanceof HTMLCanvasElement) return element;
    let canvas = element.querySelector('canvas');
    if (!canvas) {
      canvas = document.createElement('canvas');
      element.appendChild(canvas);
    }
    return canvas;
  }

  function mount(canvas, config) {
    const previous = chartByCanvas.get(canvas);
    if (previous) previous.destroy();
    const chart = new global.Chart(canvas.getContext('2d'), config);
    chartByCanvas.set(canvas, chart);
    return chart;
  }

  const centerTextPlugin = {
    id: 'ledgerCenterText',
    afterDraw: function (chart) {
      const options = chart.options.plugins && chart.options.plugins.ledgerCenterText;
      if (!options || !options.text) return;
      const area = chart.chartArea;
      if (!area) return;
      const ctx = chart.ctx;
      const x = (area.left + area.right) / 2;
      const y = (area.top + area.bottom) / 2;
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = options.color || '#111827';
      ctx.font = '700 ' + (options.fontSize || 18) + 'px "Microsoft YaHei", "PingFang SC", sans-serif';
      ctx.fillText(options.text, x, y - 9);
      if (options.subtext) {
        ctx.fillStyle = options.subColor || '#6b7280';
        ctx.font = '12px "Microsoft YaHei", "PingFang SC", sans-serif';
        ctx.fillText(options.subtext, x, y + 15);
      }
      ctx.restore();
    }
  };

  const emptyStatePlugin = {
    id: 'ledgerEmptyState',
    afterDraw: function (chart) {
      const datasets = chart.data.datasets || [];
      const hasValue = datasets.some(function (dataset) {
        return (dataset.data || []).some(function (value) {
          return toNumber(value) > 0;
        });
      });
      if (hasValue) return;
      const area = chart.chartArea;
      if (!area) return;
      const ctx = chart.ctx;
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#9ca3af';
      ctx.font = '14px "Microsoft YaHei", "PingFang SC", sans-serif';
      ctx.fillText('暂无数据', (area.left + area.right) / 2, (area.top + area.bottom) / 2);
      ctx.restore();
    }
  };

  global.Chart.register(centerTextPlugin, emptyStatePlugin);

  const baseTooltip = {
    backgroundColor: 'rgba(17, 24, 39, 0.92)',
    padding: 10,
    cornerRadius: 8,
    titleFont: { size: 13 },
    bodyFont: { size: 12 },
    displayColors: true
  };

  function renderOverview(target) {
    const canvas = resolveCanvas(target);
    if (!canvas) return null;
    const overview = currentOverview();
    const total = overview.income + overview.expense;
    const balanceColor = overview.balance < 0 ? EXPENSE_COLOR : '#111827';
    return mount(canvas, {
      type: 'doughnut',
      data: {
        labels: ['收入', '支出'],
        datasets: [{
          data: [overview.income, overview.expense],
          backgroundColor: [INCOME_COLOR, EXPENSE_COLOR],
          borderWidth: 0,
          hoverOffset: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: { usePointStyle: true, boxWidth: 10, padding: 16 }
          },
          tooltip: Object.assign({}, baseTooltip, {
            callbacks: {
              label: function (ctx) {
                const value = toNumber(ctx.parsed);
                const pct = total > 0 ? (value / total * 100).toFixed(1) : '0.0';
                return ctx.label + ': ' + formatMoney(value) + ' (' + pct + '%)';
              }
            }
          }),
          ledgerCenterText: {
            text: formatMoney(overview.balance),
            subtext: '结余',
            color: balanceColor
          }
        }
      }
    });
  }

  function renderCategory(target, type) {
    const canvas = resolveCanvas(target);
    if (!canvas) return null;
    const targetType = type === 'income' ? 'income' : 'expense';
    const rows = currentCategoryRows(targetType).slice(0, 8);
    return mount(canvas, {
      type: 'bar',
      data: {
        labels: rows.map(function (row) { return row.category; }),
        datasets: [{
          label: targetType === 'income' ? '收入' : '支出',
          data: rows.map(function (row) { return row.amount; }),
          backgroundColor: rows.map(function (row) { return row.color; }),
          borderRadius: 6,
          borderSkipped: false,
          maxBarThickness: 26
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: Object.assign({}, baseTooltip, {
            callbacks: {
              label: function (ctx) {
                return ctx.label + ': ' + formatMoney(ctx.parsed.x);
              }
            }
          })
        },
        scales: {
          x: {
            beginAtZero: true,
            grid: { color: 'rgba(148, 163, 184, 0.18)' },
            ticks: { callback: function (value) { return formatCompact(value); } }
          },
          y: {
            grid: { display: false },
            ticks: { font: { size: 12 } }
          }
        }
      }
    });
  }

  function renderTrend(target) {
    const canvas = resolveCanvas(target);
    if (!canvas) return null;
    const rows = currentMonthRows();
    return mount(canvas, {
      type: 'line',
      data: {
        labels: rows.map(function (row) { return row.month; }),
        datasets: [
          {
            label: '收入',
            data: rows.map(function (row) { return row.income; }),
            borderColor: INCOME_COLOR,
            backgroundColor: 'rgba(16, 185, 129, 0.12)',
            pointBackgroundColor: INCOME_COLOR,
            pointRadius: 4,
            pointHoverRadius: 6,
            borderWidth: 2,
            tension: 0.32,
            fill: true
          },
          {
            label: '支出',
            data: rows.map(function (row) { return row.expense; }),
            borderColor: EXPENSE_COLOR,
            backgroundColor: 'rgba(239, 68, 68, 0.10)',
            pointBackgroundColor: EXPENSE_COLOR,
            pointRadius: 4,
            pointHoverRadius: 6,
            borderWidth: 2,
            tension: 0.32,
            fill: true
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { usePointStyle: true, boxWidth: 10, padding: 16 }
          },
          tooltip: Object.assign({}, baseTooltip, {
            callbacks: {
              label: function (ctx) {
                return ctx.dataset.label + ': ' + formatMoney(ctx.parsed.y);
              }
            }
          })
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { font: { size: 12 } }
          },
          y: {
            beginAtZero: true,
            grid: { color: 'rgba(148, 163, 184, 0.18)' },
            ticks: { callback: function (value) { return formatCompact(value); } }
          }
        }
      }
    });
  }

  function renderAll(selectors) {
    const options = Object.assign({
      overview: '#chart-overview',
      category: '#chart-category',
      trend: '#chart-trend'
    }, selectors || {});
    const statsFilters = state.mode === 'stats' && state.stats ? state.stats.filters : null;
    const categoryType = options.categoryType || (statsFilters && statsFilters.rtype) || 'expense';
    if (options.overview && document.querySelector(options.overview)) renderOverview(options.overview);
    if (options.category && document.querySelector(options.category)) renderCategory(options.category, categoryType);
    if (options.trend && document.querySelector(options.trend)) renderTrend(options.trend);
    return api;
  }

  function setData(data) {
    const safe = data || {};
    state.mode = 'records';
    state.stats = null;
    state.records = (Array.isArray(safe.records) ? safe.records : []).map(normalizeRecord);
    state.categories = Array.isArray(safe.categories) ? safe.categories : [];
    state.colorMap = buildColorMap(state.categories);
    return api;
  }

  function setStats(payload, categories) {
    const raw = unwrapStats(payload);
    state.mode = 'stats';
    state.records = [];
    state.categories = Array.isArray(categories)
      ? categories
      : (Array.isArray(raw.categories) ? raw.categories : []);
    state.colorMap = buildColorMap(state.categories);

    const byCategory = raw.by_category || raw.byCategory || {};
    state.stats = {
      filters: raw.filters || {},
      summary: normalizeSummary(raw.summary || raw),
      byCategory: {
        income: normalizeCategoryRows(byCategory.income),
        expense: normalizeCategoryRows(byCategory.expense)
      },
      byMonth: normalizeMonthRows(raw.by_month || raw.byMonth)
    };
    return api;
  }

  function setCurrency(symbol) {
    if (symbol) state.currency = String(symbol);
    return api;
  }

  function destroyAll() {
    state.mode = 'records';
    state.records = [];
    state.stats = null;
    document.querySelectorAll('canvas').forEach(function (canvas) {
      const chart = chartByCanvas.get(canvas);
      if (chart) {
        chart.destroy();
        chartByCanvas.delete(canvas);
      }
    });
    return api;
  }

  function getRecords() {
    return state.records.slice();
  }

  const api = {
    setData: setData,
    setStats: setStats,
    setCurrency: setCurrency,
    getRecords: getRecords,
    renderAll: renderAll,
    renderOverview: renderOverview,
    renderCategory: renderCategory,
    renderTrend: renderTrend,
    destroyAll: destroyAll,
    aggregateOverview: aggregateOverview,
    aggregateByCategory: aggregateByCategory,
    aggregateByMonth: aggregateByMonth,
    filterByDateRange: filterByDateRange,
    formatMoney: formatMoney,
    formatCompact: formatCompact
  };

  global.LedgerCharts = api;
})(window);
