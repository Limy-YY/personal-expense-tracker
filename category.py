# -*- coding: utf-8 -*-
"""
category.py — 分类管理模块（成员F 独立负责）
功能：默认分类初始化、分类列表查询、增删改、颜色配置、月度预算（亮点项4）
数据结构约定：data.json -> {
    "categories": [
        {"name": "饮食", "type": "expense", "color": "#ff7043", "budget": 1500},
        {"name": "工资", "type": "income",  "color": "#ffa726"}   # 收入类不设预算
    ],
    "records":    [ ... ]   # records.category 直接存分类名字符串
}
说明：
  - records 中 category 字段直接存分类名，因此本模块在改名/删除时会联动 records。
  - budget 为月度预算金额（元），仅支出类有；前端据此画进度条，超支变红。
"""

import json
import os
import re

# Flask 是部署依赖；本地自测时没装也不影响业务函数。
try:
    from flask import Blueprint, request, jsonify
    _HAS_FLASK = True
except ImportError:
    _HAS_FLASK = False

# ============ 配置 ============
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

# 默认分类（首次启动自动写入，幂等）
# budget = 月度预算金额（元），仅支出类设置；收入类不设预算
DEFAULT_CATEGORIES = [
    {"name": "饮食", "type": "expense", "color": "#ff7043", "budget": 1500},
    {"name": "交通", "type": "expense", "color": "#42a5f5", "budget": 300},
    {"name": "购物", "type": "expense", "color": "#ab47bc", "budget": 500},
    {"name": "娱乐", "type": "expense", "color": "#26a69a", "budget": 300},
    {"name": "居住", "type": "expense", "color": "#66bb6a", "budget": 2000},
    {"name": "医疗", "type": "expense", "color": "#ef5350", "budget": 200},
    {"name": "教育", "type": "expense", "color": "#5c6bc0", "budget": 200},
    {"name": "工资", "type": "income",  "color": "#ffa726"},
    {"name": "兼职", "type": "income",  "color": "#ec407a"},
    {"name": "红包", "type": "income",  "color": "#d4a017"},
    {"name": "其他", "type": "expense", "color": "#9e9e9e", "budget": 200},
]

VALID_TYPES = ("expense", "income")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


# ============ 数据读写（联调时改为调用成员B storage.py 的统一接口） ============
# TODO(联调): 把下面两个函数替换成 from storage import load_data / save_data
#             其余业务函数不用动，保证模块独立可测。
def _load_data():
    """读取整个 data.json；文件不存在或损坏时回退到空结构，避免整站崩。"""
    if not os.path.exists(DATA_FILE):
        return {"records": [], "categories": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("records", [])
        data.setdefault("categories", [])
        return data
    except (json.JSONDecodeError, OSError):
        return {"records": [], "categories": []}


def _save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============ 业务函数 ============
def init_categories():
    """首次启动：若 categories 为空则写入默认分类。可重复调用。"""
    data = _load_data()
    if not data["categories"]:
        data["categories"] = [dict(c) for c in DEFAULT_CATEGORIES]
        _save_data(data)


def list_categories(c_type=None):
    """
    列出分类。
    :param c_type: None=全部；'expense'=只返回支出类；'income'=只返回收入类
    :return: list[dict]
    """
    data = _load_data()
    cats = data["categories"]
    if c_type:
        cats = [c for c in cats if c["type"] == c_type]
    return cats


def _validate(name, c_type, color, budget=None):
    """表单校验；不合法直接抛 ValueError。"""
    if not name or not str(name).strip():
        raise ValueError("分类名称不能为空")
    if c_type not in VALID_TYPES:
        raise ValueError("type 必须是 expense 或 income")
    if not HEX_COLOR_RE.match(color or ""):
        raise ValueError("color 必须是 #RRGGBB 格式，例如 #ff7043")
    # 预算校验：仅支出类可设预算，且必须是 >=0 的数字
    if budget is not None:
        if c_type != "expense":
            raise ValueError("收入类分类不支持设置预算")
        if not isinstance(budget, (int, float)) or isinstance(budget, bool) or budget < 0:
            raise ValueError("budget 必须是不小于 0 的数字（单位：元）")


def add_category(name, c_type, color, budget=None):
    """新增分类；重名抛 ValueError。budget 仅支出类可传，单位元。"""
    name = (name or "").strip()
    _validate(name, c_type, color, budget)
    data = _load_data()
    if any(c["name"] == name for c in data["categories"]):
        raise ValueError(f"分类「{name}」已存在")
    cat = {"name": name, "type": c_type, "color": color}
    if budget is not None:
        cat["budget"] = budget
    data["categories"].append(cat)
    _save_data(data)
    return cat


def update_category(old_name, new_name, color=None, budget=None):
    """
    修改分类：可改名、可改色、可改预算。
    若改名，会同步把 records 里所有引用 old_name 的记录改成 new_name，避免历史记录丢分类。
    budget 传 None 表示不修改；传数字则更新月预算（仅支出类）。
    """
    new_name = (new_name or old_name).strip()
    data = _load_data()
    target = next((c for c in data["categories"] if c["name"] == old_name), None)
    if target is None:
        raise ValueError(f"分类「{old_name}」不存在")

    if new_name != old_name:
        if not new_name:
            raise ValueError("新分类名不能为空")
        if any(c["name"] == new_name for c in data["categories"]):
            raise ValueError(f"分类「{new_name}」已存在")
        # 联动 records：把历史记录里的旧分类名替换掉
        for r in data["records"]:
            if r.get("category") == old_name:
                r["category"] = new_name
        target["name"] = new_name

    if color:
        if not HEX_COLOR_RE.match(color):
            raise ValueError("color 必须是 #RRGGBB 格式")
        target["color"] = color

    if budget is not None:
        if target["type"] != "expense":
            raise ValueError("收入类分类不支持设置预算")
        if not isinstance(budget, (int, float)) or isinstance(budget, bool) or budget < 0:
            raise ValueError("budget 必须是不小于 0 的数字（单位：元）")
        target["budget"] = budget

    _save_data(data)
    return target


def delete_category(name):
    """删除分类；被任何记录引用时拒绝删除，提示先把记录改到「其他」。"""
    data = _load_data()
    if not any(c["name"] == name for c in data["categories"]):
        raise ValueError(f"分类「{name}」不存在")
    used = [r for r in data["records"] if r.get("category") == name]
    if used:
        raise ValueError(f"分类「{name}」被 {len(used)} 条记录使用，请先把这些记录改到其他分类")
    data["categories"] = [c for c in data["categories"] if c["name"] != name]
    _save_data(data)


# ============ Flask 蓝图（给组长A集成到 app.py） ============
# 在 app.py 里写：
#   from category import bp, init_categories
#   if bp: app.register_blueprint(bp)
#   init_categories()   # 启动时初始化默认分类
if _HAS_FLASK:
    bp = Blueprint("category", __name__, url_prefix="/api/categories")

    @bp.get("")
    def api_list():
        c_type = request.args.get("type")
        try:
            return jsonify({"code": 0, "data": list_categories(c_type)})
        except Exception as e:
            return jsonify({"code": 1, "msg": str(e)}), 400

    @bp.post("")
    def api_add():
        body = request.get_json(force=True) or {}
        try:
            cat = add_category(
                body.get("name"), body.get("type"), body.get("color"),
                body.get("budget"),
            )
            return jsonify({"code": 0, "data": cat})
        except ValueError as e:
            return jsonify({"code": 1, "msg": str(e)}), 400

    @bp.put("/<old_name>")
    def api_update(old_name):
        body = request.get_json(force=True) or {}
        try:
            cat = update_category(
                old_name, body.get("name", old_name),
                body.get("color"), body.get("budget"),
            )
            return jsonify({"code": 0, "data": cat})
        except ValueError as e:
            return jsonify({"code": 1, "msg": str(e)}), 400

    @bp.delete("/<name>")
    def api_delete(name):
        try:
            delete_category(name)
            return jsonify({"code": 0, "msg": "deleted"})
        except ValueError as e:
            return jsonify({"code": 1, "msg": str(e)}), 400
else:
    bp = None


# ============ 自测：直接 python category.py 即可跑 ============
if __name__ == "__main__":
    # 清掉旧数据，保证看到带 budget 的最新默认分类
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)

    init_categories()
    print("=== 默认分类（含预算） ===")
    for c in list_categories():
        print(c)

    print("\n=== 测试：新增支出类带预算 ===")
    print(add_category("宠物", "expense", "#8d6e63", budget=300))

    print("\n=== 测试：修改预算 ===")
    print(update_category("宠物", "宠物", budget=500))

    print("\n=== 测试：收入类设预算应报错 ===")
    try:
        add_category("稿费", "income", "#7e57c2", budget=100)
    except ValueError as e:
        print("预期报错：", e)

    print("\n=== 测试：非法预算应报错 ===")
    try:
        add_category("测试", "expense", "#999999", budget=-10)
    except ValueError as e:
        print("预期报错：", e)

    print("\n=== 清理测试数据 ===")
    delete_category("宠物")
    print("剩余分类数：", len(list_categories()))
