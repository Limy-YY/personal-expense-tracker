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
import math
import os
import re

# Flask 是部署依赖；本地自测时没装也不影响业务函数。
try:
    from flask import Blueprint, request, jsonify
    _HAS_FLASK = True
except ImportError:
    _HAS_FLASK = False

# ============ 配置 ============
# 数据文件统一放在 data/ 目录（与成员B的 records.json 同目录）
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CATEGORIES_FILE = os.path.join(DATA_DIR, "categories.json")
RECORDS_FILE = os.path.join(DATA_DIR, "records.json")

# 默认分类（首次启动自动写入，幂等）
# budget = 月度预算金额（元），仅支出类设置；收入类不设预算
# icon = 前端展示图标（emoji），可选
DEFAULT_CATEGORIES = [
    {"name": "饮食", "type": "expense", "color": "#ff7043", "budget": 1500, "icon": "🍜"},
    {"name": "交通", "type": "expense", "color": "#42a5f5", "budget": 300,  "icon": "🚌"},
    {"name": "购物", "type": "expense", "color": "#ab47bc", "budget": 500,  "icon": "🛍️"},
    {"name": "娱乐", "type": "expense", "color": "#26a69a", "budget": 300,  "icon": "🎮"},
    {"name": "居住", "type": "expense", "color": "#66bb6a", "budget": 2000, "icon": "🏠"},
    {"name": "医疗", "type": "expense", "color": "#ef5350", "budget": 200,  "icon": "💊"},
    {"name": "教育", "type": "expense", "color": "#5c6bc0", "budget": 200,  "icon": "📚"},
    {"name": "工资", "type": "income",  "color": "#ffa726", "icon": "💰"},
    {"name": "兼职", "type": "income",  "color": "#ec407a", "icon": "💴"},
    {"name": "红包", "type": "income",  "color": "#d4a017", "icon": "🧧"},
    {"name": "其他收入", "type": "income", "color": "#9e9e9e", "icon": "📦"},
    {"name": "其他支出", "type": "expense", "color": "#9e9e9e", "budget": 200,  "icon": "📦"},
]

VALID_TYPES = ("expense", "income")  # 校验 type，只能是支出/收入
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")  # 校验 6 位十六进制颜色码
# 分类名禁止出现 URL 路由特殊字符，否则 /api/categories/<name> 匹配不到
NAME_BAD_CHARS = re.compile(r"[/?#&=]")  # 检查名字里不能包含 / ? # & = 这些字符
# 兜底分类：受保护不可删除，删除其他分类时历史记录自动迁移到同类型兜底
PROTECTED_CATEGORY = "其他支出"  # 支出类兜底；收入类兜底是"其他收入"


# ============ 数据读写 ============
# categories 存 data/categories.json；records 由成员B的 storage.py 管理在 data/records.json
# 本模块只在改名/删除时读取 records 做联动，不负责 records 的 CRUD。

def _load_categories():
    """读取分类列表；文件不存在返回空 list。"""
    if not os.path.exists(CATEGORIES_FILE):
        return []
    try:
        with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
            cats = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"categories.json 已损坏：{e}") from e
    except OSError as e:
        raise RuntimeError(f"categories.json 读取失败：{e}") from e
    if not isinstance(cats, list):
        raise RuntimeError("categories.json 顶层不是数组")
    # 元素级校验
    for i, c in enumerate(cats):
        if not isinstance(c, dict):
            raise RuntimeError(f"categories[{i}] 不是对象")
        if not isinstance(c.get("name"), str) or not c.get("name"):
            raise RuntimeError(f"categories[{i}] 缺少合法 name")
        if c.get("type") not in VALID_TYPES:
            raise RuntimeError(f"categories[{i}] 的 type 非法")
        if not isinstance(c.get("color"), str) or not HEX_COLOR_RE.match(c.get("color", "")):
            raise RuntimeError(f"categories[{i}] 的 color 不是 #RRGGBB 格式")
    return cats


def _save_categories(cats):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CATEGORIES_FILE, "w", encoding="utf-8") as f:
        json.dump(cats, f, ensure_ascii=False, indent=2)


def _load_records():
    """读取 records（用于改名/删除时联动）；文件不存在返回空 list。
    损坏时抛 RuntimeError，不静默返回空列表，防止删除分类时漏迁移记录。
    """
    if not os.path.exists(RECORDS_FILE):
        return []
    try:
        with open(RECORDS_FILE, "r", encoding="utf-8") as f:
            records = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"records.json 已损坏：{e}") from e
    except OSError as e:
        raise RuntimeError(f"records.json 读取失败：{e}") from e
    if not isinstance(records, list):
        raise RuntimeError("records.json 顶层不是数组")
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise RuntimeError(f"records[{i}] 不是对象")
    return records


def _save_records(records):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


# ============ 业务函数 ============
def init_categories():
    """首次启动：若 categories 为空则写入默认分类。可重复调用。"""
    cats = _load_categories()
    if not cats:
        _save_categories([dict(c) for c in DEFAULT_CATEGORIES])


def list_categories(c_type=None):
    """列出分类；c_type=None=全部，'expense'/'income' 按收支类型筛选。"""
    cats = _load_categories()
    if c_type:
        if c_type not in VALID_TYPES:
            raise ValueError("type 必须是 expense 或 income")
        cats = [c for c in cats if c["type"] == c_type]
    return cats


def _validate(name, c_type, color, budget=None, icon=None):
    """表单校验；不合法直接抛 ValueError。"""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("分类名称必须是非空字符串")
    if NAME_BAD_CHARS.search(name):
        raise ValueError("分类名称不能包含 / ? # & = 等特殊字符")
    if c_type not in VALID_TYPES:
        raise ValueError("type 必须是 expense 或 income")
    if not isinstance(color, str) or not HEX_COLOR_RE.match(color):
        raise ValueError("color 必须是 #RRGGBB 格式，例如 #ff7043")
    if icon is not None and not isinstance(icon, str):
        raise ValueError("icon 必须是字符串（emoji）")
    # 预算校验：仅支出类可设预算，且必须是有限数字
    if budget is not None:
        if c_type != "expense":
            raise ValueError("收入类分类不支持设置预算")
        if isinstance(budget, bool) or not isinstance(budget, (int, float)):
            raise ValueError("budget 必须是不小于 0 的数字（单位：元）")
        if not math.isfinite(budget) or budget < 0:
            raise ValueError("budget 必须是不小于 0 的有限数字（不能是 NaN/∞）")


def add_category(name, c_type, color, budget=None, icon=None):
    """新增分类；重名抛 ValueError。budget 仅支出类可传，单位元。icon 可选 emoji。"""
    if not isinstance(name, str):
        raise ValueError("分类名称必须是字符串")
    name = name.strip()
    _validate(name, c_type, color, budget, icon)
    cats = _load_categories()
    if any(c["name"] == name for c in cats):
        raise ValueError(f"分类「{name}」已存在")
    cat = {"name": name, "type": c_type, "color": color}
    if budget is not None:
        cat["budget"] = budget
    if icon:
        cat["icon"] = icon
    cats.append(cat)
    _save_categories(cats)
    return cat


def update_category(old_name, new_name=None, color=None, budget=None, icon=None):
    """
    修改分类：可改名、可改色、可改预算、可改图标。
    - 参数传 None 表示不修改该字段；
    - 传空字符串/空值视为非法输入，返回校验错误。
    若改名，会同步把 records 里所有引用 old_name 的记录改成 new_name。
    """
    cats = _load_categories()
    target = next((c for c in cats if c["name"] == old_name), None)
    if target is None:
        raise ValueError(f"分类「{old_name}」不存在")

    # --- 改名：None=不改；空串=报错 ---
    if new_name is not None:
        if not isinstance(new_name, str) or not new_name.strip():
            raise ValueError("新分类名不能为空")
        new_name = new_name.strip()
        if NAME_BAD_CHARS.search(new_name):
            raise ValueError("分类名称不能包含 / ? # & = 等特殊字符")
        if new_name != old_name:
            if any(c["name"] == new_name for c in cats):
                raise ValueError(f"分类「{new_name}」已存在")
            # 联动 records：把历史记录里的旧分类名替换掉
            records = _load_records()
            for r in records:
                if r.get("category") == old_name:
                    r["category"] = new_name
            _save_records(records)
            target["name"] = new_name

    # --- 改色：None=不改；空串=报错 ---
    if color is not None:
        if not isinstance(color, str) or not HEX_COLOR_RE.match(color):
            raise ValueError("color 必须是 #RRGGBB 格式")
        target["color"] = color

    # --- 改预算：None=不改；数字=更新（仅支出类） ---
    if budget is not None:
        if target["type"] != "expense":
            raise ValueError("收入类分类不支持设置预算")
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget < 0:
            raise ValueError("budget 必须是不小于 0 的有限数字（单位：元）")
        target["budget"] = budget

    # --- 改图标：None=不改；传字符串=更新 ---
    if icon is not None:
        if not isinstance(icon, str):
            raise ValueError("icon 必须是字符串（emoji）")
        target["icon"] = icon

    _save_categories(cats)
    return target


def delete_category(name):
    """
    删除分类（方案②：自动迁移到同类型兜底分类「其他」）。
    - 「其他」是受保护兜底分类，禁止删除；
    - 被记录引用的分类删除时，历史记录的 category 自动改为同类型的「其他」，不跨类型迁移。
    """
    cats = _load_categories()
    target = next((c for c in cats if c["name"] == name), None)
    if target is None:
        raise ValueError(f"分类「{name}」不存在")
    if name == PROTECTED_CATEGORY:
        raise ValueError(f"「{PROTECTED_CATEGORY}」是系统兜底分类，禁止删除")

    # 找同类型的兜底分类：支出→「其他」，收入→「其他收入」
    fallback_name = PROTECTED_CATEGORY if target["type"] == "expense" else "其他收入"
    fallback = next(
        (c for c in cats if c["name"] == fallback_name and c["type"] == target["type"]),
        None,
    )
    if fallback is None:
        raise ValueError(f"没有{target['type']}类型的兜底分类「{fallback_name}」，无法删除")

    # 把引用该分类的记录迁移到同类型兜底分类
    records = _load_records()
    migrated = 0
    for r in records:
        if r.get("category") == name:
            r["category"] = fallback_name
            migrated += 1
    _save_records(records)

    cats = [c for c in cats if c["name"] != name]
    _save_categories(cats)
    return {"migrated_records": migrated}


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
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            return jsonify({"code": 1, "msg": "请求体必须是 JSON 对象"}), 400
        try:
            cat = add_category(
                body.get("name"), body.get("type"), body.get("color"),
                body.get("budget"), body.get("icon"),
            )
            return jsonify({"code": 0, "data": cat})
        except ValueError as e:
            return jsonify({"code": 1, "msg": str(e)}), 400

    @bp.put("/<old_name>")
    def api_update(old_name):
        body = request.get_json(force=True)
        if not isinstance(body, dict):
            return jsonify({"code": 1, "msg": "请求体必须是 JSON 对象"}), 400
        try:
            cat = update_category(
                old_name,
                body.get("name"), body.get("color"),
                body.get("budget"), body.get("icon"),
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
# 使用临时目录，绝不触碰真实数据文件
if __name__ == "__main__":
    import shutil
    import tempfile

    tmp_dir = tempfile.mkdtemp(prefix="category_test_")
    # 把数据文件指向临时目录
    DATA_DIR = os.path.join(tmp_dir, "data")
    CATEGORIES_FILE = os.path.join(DATA_DIR, "categories.json")
    RECORDS_FILE = os.path.join(DATA_DIR, "records.json")

    try:
        init_categories()
        print("=== 默认分类（含预算/图标） ===")
        for c in list_categories():
            print(c)

        print("\n=== 测试：新增支出类带预算和图标 ===")
        print(add_category("宠物", "expense", "#8d6e63", budget=300, icon="🐱"))

        print("\n=== 测试：修改预算和图标 ===")
        print(update_category("宠物", budget=500, icon="🐶"))

        print("\n=== 测试：收入类设预算应报错 ===")
        try:
            add_category("稿费", "income", "#7e57c2", budget=100)
        except ValueError as e:
            print("预期报错：", e)

        print("\n=== 测试：NaN/负数预算应报错 ===")
        try:
            add_category("测试", "expense", "#999999", budget=float("nan"))
        except ValueError as e:
            print("预期报错：", e)

        print("\n=== 测试：分类名带 / 应报错 ===")
        try:
            add_category("饮/食", "expense", "#999999")
        except ValueError as e:
            print("预期报错：", e)

        print("\n=== 测试：更新传空名称应报错 ===")
        try:
            update_category("宠物", new_name="")
        except ValueError as e:
            print("预期报错：", e)

        print("\n=== 测试：删除兜底分类「其他支出」应报错 ===")
        try:
            delete_category("其他支出")
        except ValueError as e:
            print("预期报错：", e)

        print("\n=== 测试：删除有记录引用的分类，记录自动迁移到「其他支出」 ===")
        # 手动塞两条引用"宠物"的记录
        records = [
            {"id": "r1", "type": "expense", "date": "2026-11-07", "amount": 100, "category": "宠物", "note": "猫粮"},
            {"id": "r2", "type": "expense", "date": "2026-11-07", "amount": 50, "category": "交通", "note": "打车"},
        ]
        _save_records(records)
        result = delete_category("宠物")
        print("删除结果：", result)
        print("迁移后记录：", _load_records())

        print("\n=== 最终分类数 ===")
        print(len(list_categories()))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
