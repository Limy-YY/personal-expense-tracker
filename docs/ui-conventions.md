# UI 组件与接口约定（成员 H）

所有页面必须继承 `base.html`，内容放在 `{% block content %}`，额外脚本放在 `{% block scripts %}`。

## 一、页面需要的后端端点

| 模板 | 端点 | 说明 |
|---|---|---|
| `base.html` | `index`、`record_new`、`records`、`stats`、`categories` | 顶部导航 |
| `index.html` | `index` | 首页 |
| `record_form.html` | `record_new`、`record_edit`、`record_delete` | 新增/编辑/删除记录 |
| `record_list.html` | `records`、`record_edit`、`record_delete` | 明细、分页、编辑、删除 |
| `stats.html` | `stats` | 统计与图表 |
| `categories.html` | `categories`、`category_delete` | 分类管理 |

## 二、各页面需要的模板变量

| 模板 | 变量 |
|---|---|
| `index.html` | `summary`（income/expense/balance）、`recent`、`total`、`colors` |
| `record_form.html` | `categories`、`record`（新建为 `None`）、`mode`（new/edit）、`record_id`、`today` |
| `record_list.html` | `records`、`categories`、`colors`、`total`、`page`、`total_pages`、`filters` |
| `stats.html` | `summary`、`category_rows`、`chart_data`、`chart_category_type`、`categories`、`total`、`filters` |
| `categories.html` | `categories`（每项含 `count`） |

`colors` 是 `{类别名: 颜色}` 映射；`filters` 是 `request.args`。

## 三、组件类名规范

| 分类 | 类名 |
|---|---|
| 布局 | `.page` `.page-head` `.page-sub` `.two-col` `.stats-grid` `.charts-grid` `.chart-wide` |
| 卡片 | `.card` `.card-head` |
| 统计卡 | `.stat-card` `.stat-income` `.stat-expense` `.stat-balance` `.stat-label` `.stat-value` |
| 按钮 | `.btn` `.btn-primary` `.btn-ghost` `.btn-danger` `.btn-danger-ghost` `.btn-sm` |
| 表单 | `.form` `.form-grid` `.field` `.field-full` `.field-label` `.input-prefix` `.segmented` `.segment` `.field-error` `.form-actions` |
| 表格 | `.table-wrap` `.table` `.num` `.actions` |
| 标签 | `.badge` `.badge-income` `.badge-expense` `.chip` `.dot` |
| 筛选 | `.filter-bar` `.filter-grid` `.filter-keyword` `.filter-actions` |
| 反馈 | `.flash-stack` `.flash` `.flash-success` `.flash-error` `.empty` `.pagination` |
| 弹窗 | `.modal-backdrop` `.modal` `.modal-actions` |
| 图表 | `.chart-box` `.chart-box-tall` `#chart-overview` `#chart-category` `#chart-trend` |
| 导航 | `.topbar` `.nav` `.nav-link` `.active` `.nav-toggle` |

## 四、交互钩子

| 属性 | 作用 |
|---|---|
| `data-validate` | 启用表单前端校验 |
| `data-error-for="字段名"` | 错误提示显示位置 |
| `data-confirm="提示文案"` | 删除前二次确认 |
| `data-segmented` | 收入/支出分段选择 |
| `data-category-type="expense|income"` | 类别下拉随类型切换 |
| `data-nav-toggle` / `data-nav` | 移动端导航折叠 |
| `data-modal-cancel` / `data-modal-confirm` | 确认弹窗按钮 |

## 五、图表接入约定

统计页在成员 I 的 `partials/charts.html` 合入后，加一行：

```jinja
{% include "partials/charts.html" %}
```

后端需要传：

```python
chart_data = {
    "records": [...],      # 筛选后的原始记录
    "categories": [...],   # {name, type, color}
}
chart_category_type = "expense"  # 或 "income"
```

图表容器必须有高度：

```css
.chart-box { position: relative; height: 300px; }
```

## 六、其他约定

- 金额统一用 `money` 过滤器：`¥{{ value | money }}`
- 类型统一用 `type_label` 过滤器：`{{ record.type | type_label }}`
- 不要在页面里另写一套按钮/表格样式，优先复用组件类
- 页面之间的视觉差异只通过布局类调整，不改组件基础样式
