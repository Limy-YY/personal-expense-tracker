# 个人记账本（Personal Ledger）

> 一个基于 Web 的个人记账本：记录日常收入与支出，支持查看、统计与图表展示。
>
> 软件工程现场实践作业 · 2026-11-07 · 团队协作项目 · 仓库 `personal-expense-tracker`

## 功能特性

- **基础记账**：记录每笔收入/支出，包含日期、金额、类别、备注、账户
- **数据查看**：最近 N 条、分页、详情、编辑/删除
- **收支统计**：按日期区间、类别、类型、金额区间汇总总收入、总支出与结余
- **用户界面**：简洁易用的 Web 界面，响应式布局
- **图表展示**：收支占比饼图、分类柱状图、月度趋势图

## 技术栈

| 层面 | 技术 |
|---|---|
| 后端 | Python 3.12 + Flask（Blueprint 模块化） |
| 前端 | 原生 HTML / CSS / JavaScript + Chart.js |
| 数据存储 | 本地 JSON 文件（`data/records.json`） |
| 测试 | unittest + pytest |
| 持续集成 | GitHub Actions |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务
python app.py

# 3. 打开浏览器访问
# http://127.0.0.1:5000
```

## 数据存储

所有记账数据保存在本地 JSON 文件 `data/records.json`，顶层为数组，每笔记录字段如下：

```json
[
  {
    "id": "sample001",
    "type": "expense",
    "date": "2026-11-03",
    "amount": 18.5,
    "category": "餐饮",
    "note": "学校食堂午餐",
    "account": "微信"
  }
]
```

- `type`：`income`（收入）/ `expense`（支出）
- `amount`：一律存正数，正负由 `type` 决定，计算使用 `Decimal` 避免浮点误差
- `category`：类别（由 `category.py` 统一管理默认类别与增删改）
- `account`：账户（微信 / 支付宝 / 银行卡 / 默认账户）
- `id`：由 `storage.py` 生成的唯一标识

## 项目结构

```
personal-expense-tracker/
├── app.py                    # 入口：注册各模块 Blueprint 并启动
├── storage.py                # 数据存储核心（JSON 读写 / CRUD）
├── query.py                  # 筛选 / 聚合纯函数（供查看、统计调用）
├── category.py               # 类别管理
├── record_add.py             # 记账录入
├── record_list.py            # 记录查看
├── stats.py                  # 收支统计
├── export.py                 # 数据导出
├── requirements.txt          # 依赖清单
├── data/
│   └── records.json          # 本地数据（含样例数据）
├── templates/                # 页面模板（base / 录入 / 列表 / 统计 / 分类 / 图表局部）
├── static/
│   ├── css/                  # 全局样式（base / components / layout）
│   └── js/                   # ui.js、charts.js、vendor/chart.umd.min.js
├── tests/                    # 单元测试与接口测试
├── docs/                     # 文档
└── .github/workflows/        # CI 自动测试
```

## 团队成员与分工

| # | 姓名 | 角色 | 独立负责模块 | 主要代码/文件 |
|---|---|---|---|---|
| 1 | 李铭媛 | 组长/架构 | 项目集成与数据导出 | `app.py`、`export.py`、`requirements.txt` |
| 2 | 陈博淇 | 后端 | 数据存储层 | `storage.py`、`data/records.json` |
| 3 | 陈宝荣 | 后端 | 记账录入模块 | `record_add.py`、录入页模板 |
| 4 | 冯安娜 | 后端 | 记录查看模块 | `record_list.py`、列表页模板 |
| 5 | 陈媛 | 后端 | 统计模块 | `stats.py`、统计页模板 |
| 6 | 陈婉凤 | 后端 | 分类管理模块 | `category.py`、分类页模板 |
| 7 | 洪雅琳 | 后端 | 筛选与搜索模块 | `query.py` |
| 8 | 王怡婷 | 前端 | 用户界面模块（公共布局与全局样式） | `templates/base.html`、`static/css/`、`static/js/ui.js` |
| 9 | 李思淇 | 前端 | 图表可视化模块 | `static/js/charts.js`、`static/js/vendor/` |
| 10 | 马英慧 | 测试 | 测试与质量保障 | `tests/` |
| 11 | 林郑嘉同 | 文档/运维 | 文档、博客与 CI | `README.md`、`docs/`、`.github/` |

## 协作规范

分支模型、提交信息、合入顺序、PR 流程等见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 版本

- v1.0.0（2026-11-07 发布）
