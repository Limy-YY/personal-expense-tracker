"""项目入口：注册各模块 Blueprint 与页面视图，启动服务。"""

import os

from flask import Flask

from category import bp as category_bp, init_categories
from stats import bp as stats_bp, money, type_label
from export import bp as export_bp
from query import bp as query_bp

import views

init_categories()  # 确保 data/categories.json 存在（默认分类），否则类别校验全拒

app = Flask(__name__)
app.secret_key = "ledger-demo-2026"  # flash 消息需要

# JSON API 蓝图（成员E/F/G/A 的接口，保留供可能的后续前端分离）
app.register_blueprint(category_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(export_bp)
app.register_blueprint(query_bp)

# 页面视图（成员H 界面 + 成员I 图表）：路由名/变量按 成员H-界面层/接口约定.md
views.init_app(app)

# 模板过滤器（E 的契约，H/I 的模板使用 money/type_label）
app.jinja_env.filters["money"] = money
app.jinja_env.filters["type_label"] = type_label


if __name__ == "__main__":
    app.run(
        debug=False,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", 5000)),
    )
