"""项目入口：负责注册各模块 Blueprint 并启动服务。"""

from flask import Flask, redirect

# 各模块均暴露 bp = Blueprint(...)，路由在各自文件内定义，此处仅统一挂载
from record_add import record_add_bp as record_bp    # 成员C：记账录入（J 修正导入名，issue #12）
from record_list import bp as list_bp     # 成员D：记录查看
from stats import bp as stats_bp          # 成员E：统计
from category import bp as category_bp    # 成员F：分类管理
from export import bp as export_bp        # 成员A：数据导出

app = Flask(__name__)

app.register_blueprint(record_bp)
app.register_blueprint(list_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(category_bp)
app.register_blueprint(export_bp)


@app.route("/")
def index():
    """首页重定向至记账录入页。"""
    return redirect("/record")


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
