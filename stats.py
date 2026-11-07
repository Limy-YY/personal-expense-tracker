# -*- coding: utf-8 -*-
"""
stats.py — 统计模块（成员E 独立负责）
============================================================
模块职责：
  1. 按 日期区间 / 类别 / 收支类型 / 金额区间 过滤记录；
  2. 汇总总收入、总支出、结余与笔数；
  3. 按类别聚合金额、笔数、占比（供分类表与饼图，对接成员I 的图表脚本）；
  4. 组装统计页模板所需的视图数据（对齐 docs/ui-conventions.md）。

数据文件 data/records.json 由成员B 的 storage.py 统一读写；
联调时把 _load_records / _load_categories 换成 storage 的读取接口即可。

记录数据契约（与 storage.py / record_add.py 一致）：
  {"id": "...", "type": "income"|"expense", "date": "YYYY-MM-DD",
   "amount": 12.5, "category": "饮食", "note": "午餐"}

对外接口（给成员A 的 app.py 调用，勿随意改名）：
  filter_records(records, date_from, date_to, category, rtype, amount_min, amount_max)
  summarize(records)                       -> dict
  aggregate_by_category(records, rtype)   -> list[dict]
  get_stats(**filters)                     -> dict  # 模板上下文（契约字段）
"""
import os
from decimal import Decimal, ROUND_HALF_UP

# Flask 是部署依赖；本地自测时没装也不影响业务函数（与 category.py 同一写法）
try:
    from flask import Blueprint, request, jsonify
    _HAS_FLASK = True
except ImportError:
    _HAS_FLASK = False

# ============ 配置 ============
DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "records.json"
)

_CENT = Decimal("0.01")


# ============ 数据读取（联调时改为调用成员B storage.py 的统一接口） ============
# TODO(联调): 换成 from storage import load_records / load_categories
def _load_records():
    """读取记录列表；文件不存在或损坏时回退空列表。"""
    data = _load_data()
    return data.get("records", []) if isinstance(data, dict) else []


def _load_categories():
    """读取分类列表 [{name,type,color,...}]；供分类表与图表配色。"""
    data = _load_data()
    return data.get("categories", []) if isinstance(data, dict) else []


def _load_data():
    """读取整个 data/records.json；不存在或损坏时回退空结构。"""
    if not os.path.exists(DATA_FILE):
        return {"records": [], "categories": []}
    try:
        import json
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("records", [])
            data.setdefault("categories", [])
            return data
        return {"records": data if isinstance(data, list) else [], "categories": []}
    except Exception:
        return {"records": [], "categories": []}


# ============ 内部工具 ============
def _to_decimal(value):
    """安全转 Decimal；脏数据按 0 处理，不让统计崩。"""
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _round_money(value):
    """四舍五入到分，返回 float 便于序列化。"""
    return float(Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP))


# ============ Jinja 过滤器（在 app.py 注册：app.jinja_env.filters[...]） ============
def money(value):
    """金额过滤器：¥1,234.56；输入非法时显示 ¥0.00。"""
    try:
        return f"¥{float(value):.2f}"
    except Exception:
        return "¥0.00"


def type_label(record_type):
    """类型过滤器：income→收入，expense→支出。"""
    return "收入" if record_type == "income" else "支出"


# ============ 1. 过滤 ============
def filter_records(records, date_from="", date_to="", category="",
                   rtype="", amount_min=None, amount_max=None):
    """按条件过滤记录，任意条件为空表示不限；返回新列表，不改原列表。"""
    date_from = str(date_from or "").strip()
    date_to = str(date_to or "").strip()
    category = str(category or "").strip()
    rtype = str(rtype or "").strip()

    min_dec = _to_decimal(amount_min) if amount_min not in (None, "") else None
    max_dec = _to_decimal(amount_max) if amount_max not in (None, "") else None

    result = []
    for rec in records:
        date = str(rec.get("date", ""))
        if date_from and date < date_from:
            continue
        if date_to and date > date_to:
            continue
        if category and rec.get("category", "") != category:
            continue
        if rtype and rec.get("type") != rtype:
            continue
        amount = _to_decimal(rec.get("amount", 0))
        if min_dec is not None and amount < min_dec:
            continue
        if max_dec is not None and amount > max_dec:
            continue
        result.append(rec)
    return result


# ============ 2. 汇总 ============
def summarize(records):
    """
    汇总收支。

    :return: {"income": 收入, "expense": 支出, "balance": 结余, "count": 笔数}
    """
    income = Decimal("0")
    expense = Decimal("0")

    for rec in records:
        amount = _to_decimal(rec.get("amount", 0))
        if rec.get("type") == "income":
            income += amount
        else:
            expense += amount

    return {
        "income": _round_money(income),
        "expense": _round_money(expense),
        "balance": _round_money(income - expense),
        "count": len(records),
    }


# ============ 3. 按类别聚合 ============
def aggregate_by_category(records, rtype):
    """
    按类别聚合某一类型的金额与笔数。

    :return: [{"category": str, "amount": float, "count": int}, ...]，金额降序
    """
    bucket = {}
    for rec in records:
        if rec.get("type") != rtype:
            continue
        name = rec.get("category") or "其他"
        if name not in bucket:
            bucket[name] = {"category": name, "amount": Decimal("0"), "count": 0}
        bucket[name]["amount"] += _to_decimal(rec.get("amount", 0))
        bucket[name]["count"] += 1

    result = [{
        "category": k,
        "amount": _round_money(v["amount"]),
        "count": v["count"],
    } for k, v in bucket.items()]
    result.sort(key=lambda x: x["amount"], reverse=True)
    return result


# ============ 4. 模板视图组装（对齐 ui-conventions.md） ============
def get_stats(date_from="", date_to="", category="", rtype="",
              amount_min=None, amount_max=None, records=None, categories=None,
              filters=None):
    """
    统计主入口：过滤 → 汇总 → 分类聚合，返回统计页模板上下文。

    契约字段（供 templates/stats.html 使用）：
      summary             {"income", "expense", "balance"}
      category_rows       [{name, color, amount, count, percent}]
      chart_data          {"records": 筛选后记录, "categories": [{name,type,color}]}
      chart_category_type "expense" / "income"
      categories          全部分类
      total               筛选后笔数
      filters             原始筛选参数（request.args 转 dict）
    """
    if records is None:
        records = _load_records()
    if categories is None:
        categories = _load_categories()

    filtered = filter_records(records, date_from, date_to, category,
                              rtype, amount_min, amount_max)

    summary = summarize(filtered)

    # 分类表：按当前类型聚合，关联颜色并算占比
    active_type = rtype or "expense"
    type_rows = aggregate_by_category(filtered, active_type)
    color_map = {c.get("name"): c.get("color", "#9e9e9e") for c in categories}
    type_total = sum(r["amount"] for r in type_rows)
    category_rows = [{
        "name": r["category"],
        "color": color_map.get(r["category"], "#9e9e9e"),
        "amount": r["amount"],
        "count": r["count"],
        "percent": round(r["amount"] / type_total * 100, 1) if type_total else 0.0,
    } for r in type_rows]

    chart_data = {
        "records": filtered,
        "categories": [
            {"name": c.get("name"), "type": c.get("type"), "color": c.get("color")}
            for c in categories
        ],
    }

    return {
        "summary": {
            "income": summary["income"],
            "expense": summary["expense"],
            "balance": summary["balance"],
        },
        "category_rows": category_rows,
        "chart_data": chart_data,
        "chart_category_type": active_type,
        "categories": categories,
        "total": len(filtered),
        "filters": filters or {
            "date_from": date_from, "date_to": date_to, "category": category,
            "type": rtype, "amount_min": amount_min, "amount_max": amount_max,
        },
    }


# ============ Flask 蓝图（给成员A 的 app.py 注册） ============
# app.py 里：
#   from stats import bp, money, type_label
#   if bp: app.register_blueprint(bp)
#   app.jinja_env.filters["money"] = money
#   app.jinja_env.filters["type_label"] = type_label
if _HAS_FLASK:
    bp = Blueprint("stats", __name__, url_prefix="/api/stats")

    @bp.get("")
    def api_stats():
        """GET /api/stats?date_from=&date_to=&category=&type=&amount_min=&amount_max="""
        try:
            data = get_stats(
                date_from=request.args.get("date_from", ""),
                date_to=request.args.get("date_to", ""),
                category=request.args.get("category", ""),
                rtype=request.args.get("type", ""),
                amount_min=request.args.get("amount_min", ""),
                amount_max=request.args.get("amount_max", ""),
                filters=request.args.to_dict(),
            )
            return jsonify({"code": 0, "data": data})
        except Exception as e:
            return jsonify({"code": 1, "msg": str(e)}), 400
else:
    bp = None


# ============ 自测：直接 python stats.py 即可跑 ============
if __name__ == "__main__":
    demo = [
        {"id": "1", "type": "expense", "date": "2026-11-05", "amount": 28.5,   "category": "饮食", "note": "午餐"},
        {"id": "2", "type": "expense", "date": "2026-11-06", "amount": 6.0,    "category": "交通", "note": "地铁"},
        {"id": "3", "type": "income",  "date": "2026-11-05", "amount": 6500.0, "category": "工资", "note": "工资"},
        {"id": "4", "type": "expense", "date": "2026-10-18", "amount": 1800.0, "category": "居住", "note": "房租"},
        {"id": "5", "type": "income",  "date": "2026-10-20", "amount": 400.0,  "category": "兼职", "note": "家教"},
    ]
    demo_cats = [
        {"name": "饮食", "type": "expense", "color": "#ff7043"},
        {"name": "交通", "type": "expense", "color": "#42a5f5"},
        {"name": "居住", "type": "expense", "color": "#66bb6a"},
        {"name": "工资", "type": "income", "color": "#ffa726"},
        {"name": "兼职", "type": "income", "color": "#ec407a"},
    ]

    view = get_stats(records=demo, categories=demo_cats)
    print("=== 汇总 ===", view["summary"])
    print("=== 分类行 ===", view["category_rows"])
    print("=== 图表数据条数 ===", len(view["chart_data"]["records"]))
    print("=== 笔数 ===", view["total"])
