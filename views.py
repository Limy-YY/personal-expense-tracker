# -*- coding: utf-8 -*-
"""
views.py — 页面视图层（成员H 界面 + 成员I 图表）

把成员H 的 templates/static 接到真实数据上：路由名与模板变量按
`成员H-界面层/接口约定.md`，数据读写一律走 storage.py / category.py。
"""

import math
from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, url_for

import storage
from category import (
    add_category as cat_add,
    delete_category as cat_delete,
    list_categories as cat_list,
)

# 账簿配色（与 static/css/style.css 里的 muted 色一致）
PALETTE = [
    "#2c7a5b", "#3d6a8f", "#8c6e27", "#2f6f6a",
    "#a2613c", "#4a5a6a", "#7a6a3f", "#b23c2e",
]
ACCOUNTS = ["微信", "支付宝", "银行卡", "现金"]
FALLBACK_COLOR = "#8a9a91"
PER_PAGE = 20


# ------------------------------------------------------------------ 工具
def _load_categories():
    try:
        return cat_list()
    except Exception:
        return []


def _load_records():
    return storage.load_records()


def _color_map(categories):
    m = {}
    for c in categories:
        if c.get("name") and c.get("color"):
            m[c["name"]] = c["color"]
    return m


def _decorate(records, categories):
    """给每条记录补上类别颜色和账户，模板里直接用 r.color / r.account。"""
    cm = _color_map(categories)
    out = []
    for r in records:
        item = dict(r)
        item["color"] = cm.get(r.get("category"), FALLBACK_COLOR)
        item.setdefault("account", ACCOUNTS[0])
        out.append(item)
    return out


def _all_categories(categories):
    """支出在前、收入在后，返回模板下拉用的扁平列表。"""
    expense = [c for c in categories if c.get("type") == "expense"]
    income = [c for c in categories if c.get("type") == "income"]
    return expense + income


def _sort_records(records):
    """日期倒序；同日按原列表顺序倒序（后录入的在前），排序稳定。"""
    indexed = list(enumerate(records))
    indexed.sort(key=lambda x: (str(x[1].get("date", "")), x[0]), reverse=True)
    return [r for _, r in indexed]


def _filter_records(records, start="", end="", kind="", category="", keyword=""):
    out = []
    for r in records:
        d = str(r.get("date", ""))
        if start and d < start:
            continue
        if end and d > end:
            continue
        if kind and r.get("type") != kind:
            continue
        if category and r.get("category") != category:
            continue
        if keyword and keyword not in str(r.get("note", "")):
            continue
        out.append(r)
    return _sort_records(out)


def _build_summary(records, label):
    income = sum(r["amount"] for r in records if r.get("type") == "income")
    expense = sum(r["amount"] for r in records if r.get("type") == "expense")
    return {
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "income_count": sum(1 for r in records if r.get("type") == "income"),
        "expense_count": sum(1 for r in records if r.get("type") == "expense"),
        "total_count": len(records),
        "month_label": label,
        "range_label": label,
    }


def _month_bounds(d):
    first = d.replace(day=1)
    if first.month == 12:
        nxt = first.replace(year=first.year + 1, month=1)
    else:
        nxt = first.replace(month=first.month + 1)
    return first, nxt - timedelta(days=1)


def _categories_view(categories, records):
    groups = []
    for kind, title in (("expense", "支出类别"), ("income", "收入类别")):
        items = []
        for c in categories:
            if c.get("type") != kind:
                continue
            name = c.get("name")
            count = sum(1 for r in records if r.get("category") == name)
            items.append({
                "name": name,
                "type": kind,
                "color": c.get("color", FALLBACK_COLOR),
                "count": count,
            })
        groups.append({"type": kind, "title": title, "items": items})
    return groups


def _read_form():
    """解析记账/编辑表单，返回 (payload, errors)；不合法时 errors 非空。"""
    form = request.form
    rtype = form.get("type") if form.get("type") in ("expense", "income") else "expense"
    category = (form.get("category") or "").strip()
    date_text = (form.get("date") or "").strip()
    amount_text = (form.get("amount") or "").strip()
    note = (form.get("note") or "").strip()
    account = (form.get("account") or "").strip() or ACCOUNTS[0]
    if account not in ACCOUNTS:
        account = ACCOUNTS[0]

    errors = {}
    amount = 0.0
    if not date_text:
        errors["date"] = "请选择日期"
    if not category:
        errors["category"] = "请选择类别"
    elif category not in {c.get("name") for c in cat_list()}:
        errors["category"] = "类别不存在，请先在分类管理中添加"
    try:
        amount = float(amount_text)
    except (TypeError, ValueError):
        errors["amount"] = "金额只能填数字"
    else:
        if not math.isfinite(amount) or amount <= 0:
            errors["amount"] = "金额要大于 0"
        else:
            amount = round(amount, 2)

    payload = {
        "date": date_text, "type": rtype, "category": category,
        "amount": amount, "note": note, "account": account,
    }
    return payload, errors


# ------------------------------------------------------------------ 页面
def init_app(app):
    @app.context_processor
    def inject_globals():
        return {
            "palette": PALETTE,
            "accounts": ACCOUNTS,
            "today": date.today().isoformat(),
        }

    @app.route("/")
    def index():
        records = _load_records()
        categories = _load_categories()

        first, last = _month_bounds(date.today())
        month_records = [
            r for r in records
            if first.isoformat() <= str(r.get("date", "")) <= last.isoformat()
        ]
        summary = _build_summary(month_records, date.today().strftime("%Y 年 %m 月"))
        recent = _sort_records(records)[:8]

        return render_template(
            "index.html",
            active="index",
            summary=summary,
            recent=_decorate(recent, categories),
            categories=_all_categories(categories),
            form=None,
        )

    @app.route("/list")
    def record_list():
        records = _load_records()
        categories = _load_categories()

        start = request.args.get("start", "").strip()
        end = request.args.get("end", "").strip()
        kind = request.args.get("type", "").strip()
        category = request.args.get("category", "").strip()
        keyword = request.args.get("keyword", "").strip()

        filtered = _filter_records(records, start, end, kind, category, keyword)

        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        total_pages = max(1, (len(filtered) + PER_PAGE - 1) // PER_PAGE)
        page = min(page, total_pages)
        rows = filtered[(page - 1) * PER_PAGE: page * PER_PAGE]

        return render_template(
            "list.html",
            active="list",
            records=_decorate(rows, categories),
            page=page,
            total_pages=total_pages,
            total=len(filtered),
            categories=_all_categories(categories),
            filters={
                "start": start, "end": end, "type": kind,
                "category": category, "keyword": keyword,
            },
        )

    @app.route("/add", methods=["POST"])
    def record_add():
        payload, errors = _read_form()
        if errors:
            for message in errors.values():
                flash(message, "error")
            return redirect(url_for("index"))
        try:
            storage.add_record(payload)
            flash("已记上「%s %s 元」" % (payload["category"], "%.2f" % payload["amount"]), "success")
        except (ValueError, storage.StorageError) as e:
            flash("保存失败：%s" % e, "error")
        return redirect(url_for("index"))

    @app.route("/edit/<record_id>", methods=["GET", "POST"])
    def record_edit(record_id):
        records = _load_records()
        categories = _load_categories()
        target = next((r for r in records if str(r.get("id")) == str(record_id)), None)
        if target is None:
            abort(404)

        errors = {}
        if request.method == "POST":
            payload, errors = _read_form()
            if not errors:
                try:
                    storage.update_record(record_id, payload)
                    flash("记录已更新", "success")
                    return redirect(url_for("record_list"))
                except (ValueError, storage.StorageError) as e:
                    flash("保存失败：%s" % e, "error")

        return render_template(
            "record_form.html",
            active="list",
            mode="edit",
            record=target,
            errors=errors,
            categories=_all_categories(categories),
        )

    @app.route("/delete/<record_id>", methods=["POST"])
    def record_delete(record_id):
        if not storage.delete_record(record_id):
            abort(404)
        flash("已删除 1 笔记录", "success")
        return redirect(url_for("record_list"))

    @app.route("/stats")
    def stats():
        records = _load_records()
        categories = _load_categories()

        today = date.today()
        first_this_month, last_this_month = _month_bounds(today)

        start = request.args.get("start", "").strip()
        end = request.args.get("end", "").strip()
        kind = request.args.get("type", "").strip()
        category = request.args.get("category", "").strip()

        if not start and not end:
            start, end = first_this_month.isoformat(), last_this_month.isoformat()

        filtered = _filter_records(records, start, end, kind, category, "")
        label = "%s ~ %s" % (start or "最早", end or "今天")
        summary = _build_summary(filtered, label)

        type_totals = {
            "expense": sum(r["amount"] for r in filtered if r.get("type") == "expense") or 0.0,
            "income": sum(r["amount"] for r in filtered if r.get("type") == "income") or 0.0,
        }

        cm = _color_map(categories)
        agg = {}
        for r in filtered:
            key = (r.get("type"), r.get("category"))
            agg[key] = agg.get(key, 0.0) + r["amount"]

        by_category = []
        for (rtype, name), amount in agg.items():
            base = type_totals.get(rtype) or 1
            by_category.append({
                "name": name,
                "type": rtype,
                "color": cm.get(name, FALLBACK_COLOR),
                "amount": amount,
                "count": sum(1 for r in filtered if r.get("type") == rtype and r.get("category") == name),
                "ratio": amount / base if base else 0,
            })
        by_category.sort(key=lambda x: x["amount"], reverse=True)

        # 最近 6 个月趋势
        months = []
        cursor = today.replace(day=1)
        for _ in range(6):
            months.append(cursor)
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        months.reverse()

        by_month = []
        for m in months:
            mf, ml = _month_bounds(m)
            rows = [r for r in records if mf.isoformat() <= str(r.get("date", "")) <= ml.isoformat()]
            by_month.append({
                "month": "%d月" % m.month,
                "income": sum(r["amount"] for r in rows if r.get("type") == "income"),
                "expense": sum(r["amount"] for r in rows if r.get("type") == "expense"),
            })

        # 快捷区间
        prev_month_first = (first_this_month - timedelta(days=1)).replace(day=1)
        prev_month_last = first_this_month - timedelta(days=1)
        three_month_first = (first_this_month - timedelta(days=62)).replace(day=1)
        year_first = today.replace(month=1, day=1)

        presets_def = [
            ("本月", first_this_month, last_this_month),
            ("上月", prev_month_first, prev_month_last),
            ("近三个月", three_month_first, last_this_month),
            ("本年", year_first, last_this_month),
        ]
        presets = []
        for name, s, e in presets_def:
            presets.append({
                "label": name,
                "start": s.isoformat(),
                "end": e.isoformat(),
                "on": start == s.isoformat() and end == e.isoformat(),
            })

        return render_template(
            "stats.html",
            active="stats",
            summary=summary,
            by_category=by_category,
            by_month=by_month,
            presets=presets,
            categories=_all_categories(categories),
            filters={"start": start, "end": end, "type": kind, "category": category},
        )

    @app.route("/categories")
    def categories():
        records = _load_records()
        cats = _load_categories()
        return render_template(
            "categories.html",
            active="categories",
            cat_groups=_categories_view(cats, records),
            palette=PALETTE,
        )

    @app.route("/categories/add", methods=["POST"])
    def category_add():
        name = (request.form.get("name") or "").strip()
        kind = request.form.get("type") if request.form.get("type") in ("expense", "income") else "expense"
        color = request.form.get("color") or PALETTE[0]
        if not name:
            flash("类别名称不能为空", "error")
            return redirect(url_for("categories"))
        try:
            cat_add(name, kind, color)
            flash("已添加类别「%s」" % name, "success")
        except ValueError as e:
            flash("添加失败：%s" % e, "error")
        return redirect(url_for("categories"))

    @app.route("/categories/delete", methods=["POST"])
    def category_delete():
        name = (request.form.get("name") or "").strip()
        if not name:
            abort(404)
        try:
            cat_delete(name)
            flash("已删除类别「%s」" % name, "success")
        except ValueError as e:
            flash("删除失败：%s" % e, "error")
        return redirect(url_for("categories"))
