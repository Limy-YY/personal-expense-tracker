"""项目入口：负责注册各模块 Blueprint 并启动服务。"""

from flask import Flask, redirect, render_template, request

# 各模块均暴露 bp = Blueprint(...)，路由在各自文件内定义，此处仅统一挂载
from record_add import record_add_bp as record_bp    # 成员C：记账录入
from record_list import bp as list_bp     # 成员D：记录查看
from stats import bp as stats_bp, get_stats, money, type_label  # 成员E：统计
from category import bp as category_bp    # 成员F：分类管理
from export import bp as export_bp        # 成员A：数据导出

app = Flask(__name__)
app.secret_key = "ledger-demo-2026"   # flash 消息需要（J 补，issue #12）

app.register_blueprint(record_bp)
app.register_blueprint(list_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(category_bp)
app.register_blueprint(export_bp)

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


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
