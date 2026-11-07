# -*- coding: utf-8 -*-
"""
stats.py — 统计模块（成员E 独立负责）
============================================================
模块职责：
  1. 按 日期区间 / 类别 / 收支类型 / 金额区间 过滤记录；
  2. 汇总总收入、总支出、结余与笔数；
  3. 按类别聚合金额与笔数（供分类饼图 / 柱状图，对接成员I 的 charts.js）；
  4. 按月份聚合收入与支出（供月度趋势图 + 成员F 预算进度条）。

数据结构约定（与 category.py / storage.py 一致）：
  data.json -> {
      "categories": [ {"name": "饮食", "type": "expense", "color": "#ff7043", "budget": 1500}, ... ],
      "records":    [ {"id": "...", "type": "expense"|"income", "date": "YYYY-MM-DD",
                       "amount": 12.5, "category": "饮食", "note": "午餐"}, ... ]
  }
  说明：records.category 直接存分类名；amount 一律存正数，正负由 type 决定。

对外接口（给成员A 的 app.py 调用，勿随意改名）：
  filter_records(records, date_from, date_to, category, rtype, amount_min, amount_max)
  summarize(records)                       -> dict
  aggregate_by_category(records, rtype)    -> list[dict]
  aggregate_by_month(records)              -> list[dict]
  get_stats(**filters)                     -> dict   # 主入口，直接读 data.json
"""
import os
from decimal import Decimal, ROUND_HALF_UP

# Flask 是部署依赖；本地自测时没装也不影响业务函数（与 category.py 保持同一写法）
try:
    from flask import Blueprint, request, jsonify
    _HAS_FLASK = True
except ImportError:
    _HAS_FLASK = False

# ============ 配置 ============
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

# 金额保留两位小数的精度
_CENT = Decimal("0.01")


# ============ 数据读取（联调时改为调用成员B storage.py 的统一接口） ============
# TODO(联调): 把 _load_data 换成 from storage import load_data，其余函数不用动
def _load_data():
    """读取整个 data.json；不存在或损坏时回退空结构，避免统计页直接崩。"""
    if not os.path.exists(DATA_FILE):
        return {"records": [], "categories": []}
    try:
        import json
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("records", [])
        data.setdefault("categories", [])
        return data
    except Exception:
        return {"records": [], "categories": []}


# ============ 内部工具 ============
def _to_decimal(value):
    """安全转 Decimal；脏数据（None、空串、非数字）一律按 0 处理，不让统计崩。"""
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _round_money(value):
    """Decimal 四舍五入到分，返回 float 便于 jsonify 序列化。"""
    return float(Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP))


# ============ 1. 过滤 ============
def filter_records(records, date_from="", date_to="", category="",
                   rtype="", amount_min=None, amount_max=None):
    """
    按条件过滤记录，任意条件为空表示不限。返回新列表，不修改原列表。

    :param records:    原始记录列表
    :param date_from:  起始日期 'YYYY-MM-DD'（含）
    :param date_to:    结束日期 'YYYY-MM-DD'（含）
    :param category:   类别名（精确匹配，与 records.category 一致）
    :param rtype:      'expense' / 'income'
    :param amount_min: 最小金额（含），可传 '' 或 None 表示不限
    :param amount_max: 最大金额（含）
    """
    date_from = str(date_from or "").strip()
    date_to = str(date_to or "").strip()
    category = str(category or "").strip()
    rtype = str(rtype or "").strip()

    min_dec = _to_decimal(amount_min) if amount_min not in (None, "") else None
    max_dec = _to_decimal(amount_max) if amount_max not in (None, "") else None

    result = []
    for rec in records:
        # 日期：统一 YYYY-MM-DD 字符串，可直接字典序比较
        date = str(rec.get("date", ""))
        if date_from and date < date_from:
            continue
        if date_to and date > date_to:
            continue
        # 类别精确匹配
        if category and rec.get("category", "") != category:
            continue
        # 收支类型
        if rtype and rec.get("type") != rtype:
            continue
        # 金额区间
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

    :return: {
        "total_income":  总收入(float, 两位小数),
        "total_expense": 总支出(float, 两位小数),
        "balance":       结余 = 收入 - 支出(float, 两位小数),
        "count":         记录笔数(int)
    }
    """
    total_income = Decimal("0")
    total_expense = Decimal("0")

    for rec in records:
        amount = _to_decimal(rec.get("amount", 0))
        if rec.get("type") == "income":
            total_income += amount
        else:
            total_expense += amount

    return {
        "total_income": _round_money(total_income),
        "total_expense": _round_money(total_expense),
        "balance": _round_money(total_income - total_expense),
        "count": len(records),
    }


# ============ 3. 按类别聚合 ============
def aggregate_by_category(records, rtype):
    """
    按类别聚合某一类型的金额与笔数。

    :param rtype: 'expense' 或 'income'
    :return: [{"category": str, "amount": float, "count": int}, ...]，按金额降序
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

    # 金额从高到低，方便饼图 / 柱状图按占比排序
    result.sort(key=lambda x: x["amount"], reverse=True)
    return result


# ============ 4. 按月份聚合 ============
def aggregate_by_month(records):
    """
    按月份（YYYY-MM）聚合收入与支出，供趋势图与预算进度使用。

    :return: [{"month": "YYYY-MM", "income": float, "expense": float, "balance": float}, ...]，按月升序
    """
    bucket = {}
    for rec in records:
        month = str(rec.get("date", ""))[:7]
        if not month:
            continue
        if month not in bucket:
            bucket[month] = {"month": month, "income": Decimal("0"), "expense": Decimal("0")}
        amount = _to_decimal(rec.get("amount", 0))
        if rec.get("type") == "income":
            bucket[month]["income"] += amount
        else:
            bucket[month]["expense"] += amount

    result = [{
        "month": k,
        "income": _round_money(v["income"]),
        "expense": _round_money(v["expense"]),
        "balance": _round_money(v["income"] - v["expense"]),
    } for k, v in bucket.items()]

    result.sort(key=lambda x: x["month"])
    return result


# ============ 5. 主入口 ============
def get_stats(date_from="", date_to="", category="", rtype="",
              amount_min=None, amount_max=None, records=None):
    """
    统计主入口：读取（或接收）记录 → 过滤 → 汇总 → 分类 / 月度聚合。
    返回结构可直接丢给模板渲染，也可 jsonify 给 charts.js。

    :param records: 可选，传入则直接用（便于单元测试）；不传则读 data.json
    :return: {
        "filters":     回显的筛选条件,
        "summary":     summarize(...),
        "by_category": {"income": [...], "expense": [...]},
        "by_month":    [...],
        "filtered_count": int
    }
    """
    if records is None:
        records = _load_data()["records"]

    filtered = filter_records(records, date_from, date_to, category,
                              rtype, amount_min, amount_max)

    return {
        "filters": {
            "date_from": date_from or "",
            "date_to": date_to or "",
            "category": category or "",
            "rtype": rtype or "",
            "amount_min": "" if amount_min in (None, "") else amount_min,
            "amount_max": "" if amount_max in (None, "") else amount_max,
        },
        "summary": summarize(filtered),
        "by_category": {
            "income": aggregate_by_category(filtered, "income"),
            "expense": aggregate_by_category(filtered, "expense"),
        },
        "by_month": aggregate_by_month(filtered),
        "filtered_count": len(filtered),
    }


# ============ Flask 蓝图（给组长A 集成到 app.py） ============
# 在 app.py 里写：
#   from stats import bp
#   if bp: app.register_blueprint(bp)
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

    print("=== 全量汇总 ===")
    print(summarize(demo))

    print("\n=== 只看 11 月 ===")
    print(get_stats(date_from="2026-11-01", date_to="2026-11-30", records=demo)["summary"])

    print("\n=== 只看支出，金额 >= 100 ===")
    print(get_stats(rtype="expense", amount_min=100, records=demo)["by_category"]["expense"])

    print("\n=== 按月趋势 ===")
    for m in aggregate_by_month(demo):
        print(m)

    print("\n=== 真实 data.json（若存在）===")
    print(get_stats()["summary"])
