"""项目入口：负责注册各模块 Blueprint 并启动服务。"""

import datetime
import math

from flask import Flask, flash, redirect, render_template, request, url_for

# 各模块均暴露 bp = Blueprint(...)，路由在各自文件内定义，此处仅统一挂载
from record_add import record_add_bp as record_bp    # 成员C：记账录入
from record_list import bp as list_bp, filter_records as list_filter_records  # 成员D：记录查看
from stats import bp as stats_bp, get_stats, money, type_label  # 成员E：统计
from category import bp as category_bp, init_categories, list_categories  # 成员F：分类管理
from storage import (load_records as storage_load_records,            # 成员B：存储
                     get_record as storage_get_record,
                     add_record as storage_add_record,
                     update_record as storage_update_record,
                     delete_record as storage_delete_record)

init_categories()   # 确保 data/categories.json 存在（默认分类），否则类别校验全拒（J 补，issue #12）
from export import bp as export_bp        # 成员A：数据导出
from query import bp as query_bp          # 成员G：筛选与搜索

app = Flask(__name__)
app.secret_key = "ledger-demo-2026"   # flash 消息需要（J 补，issue #12）


app.register_blueprint(record_bp)
app.register_blueprint(list_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(category_bp)
app.register_blueprint(export_bp)
app.register_blueprint(query_bp)

# 模板过滤器（E 的契约，H/I 的模板使用 money/type_label）
app.jinja_env.filters["money"] = money
app.jinja_env.filters["type_label"] = type_label


@app.route("/")
def index():
    """首页重定向至记录列表页。"""
    return redirect("/records")


@app.route("/stats")
def stats_page():
    """统计页（页面视图）：复用 E 的 get_stats，契约字段与 templates/stats.html 对齐。"""
    args = request.args.to_dict()
    view = get_stats(
        date_from=args.get("date_from", ""),
        date_to=args.get("date_to", ""),
        category=args.get("category", ""),
        rtype=args.get("type", ""),
        amount_min=args.get("amount_min", ""),
        amount_max=args.get("amount_max", ""),
        filters=args,
    )
    return render_template("stats.html", **view)


@app.route("/categories", methods=["GET", "POST"])
def categories_page():
    """分类管理页：渲染 H 的 categories.html（F 只提供 API，页面视图由入口补齐）。
    POST 为表单提交新增类别（J 补，修复添加后 405 不跳转）。"""
    from category import list_categories, add_category
    from flask import flash
    if request.method == "POST":
        try:
            add_category(
                request.form.get("name", "").strip(),
                request.form.get("type", "expense").strip(),
                request.form.get("color", "#4f46e5").strip(),
            )
            flash("添加成功", "success")
        except (ValueError, TypeError) as e:
            flash(f"添加失败：{e}", "error")
        return redirect("/categories")
    return render_template("categories.html", categories=list_categories())


# ===== issue #8 方案1（A 拍板：后端适配 H）=====
# 补齐 H 模板引用的缺失 endpoint：record_new / record_edit / record_delete。
# 只做路由胶水，直接调用 B(storage)/F(category) 的现成函数，不改各成员模块。


def _validate_ledger_form(form):
    """record_form.html 表单校验，规则与 C 的 /add 对齐；H 表单无 account 字段，缺省记「未指定」。
    返回 (data, err)。"""
    rtype = (form.get("type") or "").strip()
    date_str = (form.get("date") or "").strip()
    amount_str = (form.get("amount") or "").strip()
    category = (form.get("category") or "").strip()
    note = (form.get("note") or "").strip()
    account = (form.get("account") or "").strip() or "未指定"

    if rtype not in ("income", "expense"):
        return None, "非法的收支类型"
    try:
        datetime.date.fromisoformat(date_str)
    except ValueError:
        return None, "日期格式错误，必须为 YYYY-MM-DD"
    try:
        amount = float(amount_str)
        if not math.isfinite(amount) or amount <= 0:
            return None, "金额无效，必须是大于 0 的有效数字"
    except ValueError:
        return None, "金额必须是有效的数字"
    if category not in [c.get("name") for c in list_categories()]:
        return None, f'类别"{category}"不存在'
    return {
        "type": rtype, "date": date_str, "amount": round(amount, 2),
        "category": category, "account": account, "note": note,
    }, None


@app.route("/record/new", methods=["GET", "POST"], endpoint="record_new")
def record_new_page():
    """记一笔（渲染 H 的 record_form.html，新模式）。"""
    if request.method == "POST":
        data, err = _validate_ledger_form(request.form)
        if err:
            flash(f"提交失败：{err}", "error")
        else:
            storage_add_record(data)
            flash("记账成功！", "success")
            return redirect(url_for("record_list.page_records"))
    return render_template("record_form.html", mode="new", record=None,
                           record_id=None, categories=list_categories(),
                           today=datetime.date.today().isoformat())


@app.route("/record/<record_id>/edit", methods=["GET", "POST"], endpoint="record_edit")
def record_edit_page(record_id):
    """编辑记录（编辑模式回填 record，POST 调 D/B 的更新接口）。"""
    record = storage_get_record(record_id)
    if record is None:
        flash("记录不存在或已删除", "error")
        return redirect(url_for("record_list.page_records"))
    if request.method == "POST":
        data, err = _validate_ledger_form(request.form)
        if err:
            flash(f"保存失败：{err}", "error")
        else:
            storage_update_record(record_id, data)
            flash("保存修改成功！", "success")
            return redirect(url_for("record_list.page_records"))
    return render_template("record_form.html", mode="edit", record=record,
                           record_id=record_id, categories=list_categories(),
                           today=datetime.date.today().isoformat())


@app.route("/record/<record_id>/delete", methods=["POST"], endpoint="record_delete")
def record_delete_action(record_id):
    """删除记录（record_list.html 的删除表单，POST + 前端确认弹窗）。"""
    ok = storage_delete_record(record_id)
    flash("删除成功！" if ok else "记录不存在或已删除", "success" if ok else "error")
    return redirect(url_for("record_list.page_records"))


if __name__ == "__main__":
    import os
    app.run(debug=False, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", 5000)))
