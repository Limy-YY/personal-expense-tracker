# -*- coding: utf-8 -*-
"""
record_list.py — 记录查看模块（成员D 独立负责）
============================================================
模块职责：
  1. 记录列表：最近 N 条 / 分页 / 按日期、金额排序；
  2. 记录详情：单条完整字段 + 上一笔 / 下一笔（按当前排序实时计算）；
  3. 编辑记录：字段白名单过滤 + 数值规范化，交给成员B 的 storage.py 落盘；
  4. 删除记录：删除后返回剩余条数，列表自动夹到有效页码。

数据结构约定（与 storage.py 一致）：
  data/records.json -> [                      # 顶层是列表，不是字典
      {"id": "0d3f...", "type": "expense"|"income", "date": "YYYY-MM-DD",
       "amount": 25.5, "category": "饮食", "note": "午饭", "account": "默认账户"}
  ]
  说明：amount 一律存正数，正负由 type 决定；id 由 storage.py 生成（uuid hex）。

对外接口（给成员A 的 app.py 调用，勿随意改名）：
  list_records(page, size, sort, **filters)   -> dict    # 分页主入口
  record_detail(record_id, sort)              -> dict    # 详情 + 相邻记录
  update_record(record_id, updates)           -> dict    # 编辑
  delete_record(record_id)                    -> dict    # 删除
  filter_records(records, keyword, ...)       -> list    # 兜底筛选（G 合并后自动切换）
  bp                                                     # Flask 蓝图，app.py 注册即可

依赖：
  成员B storage.py（数据读写）、成员G query.py（筛选，可选）、成员H base.html（页面布局）。
  三者任一尚未合并时，本模块都能独立运行，见下方 TODO(联调) 说明。
"""

import json
import os
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Flask 是部署依赖；本地自测时没装也不影响业务函数（与 stats.py / category.py 保持同一写法）
try:
    from flask import Blueprint, jsonify, render_template, request, redirect, url_for
    _HAS_FLASK = True
except ImportError:
    _HAS_FLASK = False

# 成员B 的存储层（分支 feature/storage，合入 main 后自动生效）
try:
    import storage
except ImportError:
    storage = None

# 成员G 的筛选模块（分工约定由他为"查看/统计"提供统一查询接口）
try:
    import query
except ImportError:
    query = None


# ============ 配置 ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 与 storage.py 完全一致的数据文件位置；联调后本模块不再直接读写它
DATA_FILE = os.path.join(BASE_DIR, "data", "records.json")

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100          # 单页上限，防止一次把整份数据返回
MAX_NOTE_LEN = 100
MAX_CATEGORY_LEN = 20

VALID_SORTS = ("date_desc", "date_asc", "amount_desc", "amount_asc")
DEFAULT_SORT = "date_desc"

VALID_TYPES = ("income", "expense")

# 允许编辑的字段白名单：account 由 storage 维护，id 不可改
EDITABLE_FIELDS = ("date", "type", "amount", "category", "note")

_CENT = Decimal("0.01")


class RecordListError(Exception):
    """业务错误（参数非法、记录不存在等），由蓝图统一转成提示信息。"""
    pass


# ============ 1. 数据读取 ============
# TODO(联调): storage.py 合入 main 后，下面的兜底分支不再被走到，无需再改代码。
def _use_storage():
    return storage is not None and hasattr(storage, "load_records")


def _read_json_file(path):
    """兜底读取：兼容 storage.py 的列表格式和 category/stats 的字典格式。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeError):
        # 数据损坏时不让列表页直接 500，返回空列表并保持程序可用
        return []
    if isinstance(data, dict):
        data = data.get("records", [])
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict)]


def load_all_records():
    """
    读取全部记录。

    storage.py 可用时用它（含完整校验与并发保护）；
    不可用时退回读取 data/records.json（或 data.json），保证本模块能独立自测。
    """
    if _use_storage():
        return storage.load_records()

    for path in (DATA_FILE, os.path.join(BASE_DIR, "data.json")):
        records = _read_json_file(path)
        if records:
            return records
    return []


def _write_all_records(records):
    """兜底写入（仅 storage 不可用时使用）；先写临时文件再原子替换。"""
    directory = os.path.dirname(DATA_FILE)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=directory,
        prefix=".records_", suffix=".tmp", delete=False
    ) as f:
        temp_path = f.name
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(temp_path, DATA_FILE)


def _find(records, record_id):
    rid = str(record_id or "").strip()
    if not rid:
        raise RecordListError("记录 id 不能为空")
    for record in records:
        if str(record.get("id")) == rid:
            return record
    raise RecordListError("记录不存在或已被删除")


# ============ 2. 筛选 ============
# TODO(联调): 成员G 的 query.py 合入后自动接管，本函数只作兜底。
def _apply_filter(records, filters):
    if query is not None and hasattr(query, "filter_records"):
        try:
            return query.filter_records(
                records,
                date_from=filters.get("start", ""),
                date_to=filters.get("end", ""),
                category=filters.get("category", ""),
                rtype=filters.get("type", ""),
                amount_min=filters.get("min_amount", ""),
                amount_max=filters.get("max_amount", ""),
                keyword=filters.get("keyword", ""),
            )
        except TypeError:
            # G 的签名可能不含 keyword，退化为本模块实现，保证页面不报错
            pass
    return filter_records(records, **filters)


def filter_records(records, keyword="", type="", category="", start="", end="",
                   min_amount="", max_amount=""):
    """
    按条件过滤记录，任意条件为空表示不限。返回新列表，不修改原列表。

    :param keyword:    关键字，匹配备注 / 类别 / 金额 / 日期
    :param type:       'expense' / 'income'
    :param category:   类别名（精确匹配）
    :param start:      起始日期 'YYYY-MM-DD'（含）
    :param end:        结束日期 'YYYY-MM-DD'（含）
    :param min_amount: 最小金额（含），'' 或 None 表示不限
    :param max_amount: 最大金额（含）
    """
    keyword = str(keyword or "").strip().lower()
    rtype = str(type or "").strip()
    category = str(category or "").strip()
    start = str(start or "").strip()
    end = str(end or "").strip()

    if rtype and rtype not in VALID_TYPES:
        raise RecordListError("类型只能是 income 或 expense")
    if start and end and start > end:
        raise RecordListError("开始日期不能晚于结束日期")

    min_dec = _to_decimal(min_amount, "最小金额")
    max_dec = _to_decimal(max_amount, "最大金额")
    if min_dec is not None and max_dec is not None and min_dec > max_dec:
        raise RecordListError("最小金额不能大于最大金额")

    result = []
    for record in records:
        # 日期统一为 YYYY-MM-DD 字符串，可直接字典序比较
        rdate = str(record.get("date", ""))
        if start and rdate < start:
            continue
        if end and rdate > end:
            continue
        if category and str(record.get("category", "")) != category:
            continue
        if rtype and record.get("type") != rtype:
            continue
        amount = _record_amount(record)
        if min_dec is not None and amount < min_dec:
            continue
        if max_dec is not None and amount > max_dec:
            continue
        if keyword:
            haystack = " ".join(
                str(record.get(k, "")) for k in ("note", "category", "date", "amount")
            ).lower()
            if keyword not in haystack:
                continue
        result.append(record)
    return result


def _to_decimal(value, field="金额"):
    """安全转 Decimal；空值返回 None，非法值抛业务错误。"""
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise RecordListError("%s 必须是数字" % field)
    if result.is_nan() or result.is_infinite() or result < 0:
        raise RecordListError("%s 必须是不小于 0 的数字" % field)
    return result


def _record_amount(record):
    """读取记录金额；脏数据按 0 处理，不让排序和筛选崩。"""
    try:
        return Decimal(str(record.get("amount", 0)))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _record_date(record):
    """读取记录日期字符串，非法则按空串处理（排到最旧一侧）。"""
    return str(record.get("date", ""))


# ============ 3. 排序 ============
def _sort_records(records, sort=DEFAULT_SORT):
    """
    排序：日期或金额，箭头由 *_desc / *_asc 决定。
    同值时用 id 兜底，保证分页结果稳定（不会出现同一个 id 在两页各出现一次）。
    """
    if sort not in VALID_SORTS:
        raise RecordListError("排序方式不支持：%s" % sort)
    if sort.startswith("date"):
        key = lambda r: (_record_date(r), str(r.get("id", "")))
    else:
        key = lambda r: (_record_amount(r), _record_date(r), str(r.get("id", "")))
    return sorted(records, key=key, reverse=sort.endswith("_desc"))


# ============ 4. 分页（主入口） ============
def list_records(page=1, size=DEFAULT_PAGE_SIZE, sort=DEFAULT_SORT,
                 records=None, **filters):
    """
    分页查询记录。

    :param page:    页码，从 1 开始
    :param size:    每页条数，1 ~ 100
    :param sort:    VALID_SORTS 之一
    :param records: 可选，传入则直接用（便于单元测试）；不传则读数据文件
    :param filters: keyword / type / category / start / end / min_amount / max_amount
    :return: {
        "page", "size", "pages", "total", "offset",
        "has_prev", "has_next",
        "records": [...],        # 当前页记录（不要叫 items：模板里 result.items 会解析成字典的 items() 方法）
        "filters": {...},        # 回显生效中的筛选条件
        "sort": str,
    }
    """
    page = _int_param(page, "page", 1)
    size = _int_param(size, "size", 1, MAX_PAGE_SIZE)
    if page < 1:
        raise RecordListError("页码必须是不小于 1 的整数")

    filters = {k: v for k, v in (filters or {}).items() if v not in (None, "")}
    if records is None:
        records = load_all_records()

    all_records = [r for r in records if isinstance(r, dict)]
    matched = _apply_filter(all_records, filters)
    matched = _sort_records(matched, sort)

    total = len(matched)
    # 空结果也按 1 页返回，前端分页条不会消失
    pages = max(1, (total + size - 1) // size)
    # 越界页夹到最后一页：删掉当前页最后一条后不会出现空白页
    if page > pages:
        page = pages
    offset = (page - 1) * size

    return {
        "page": page,
        "size": size,
        "pages": pages,
        "total": total,
        "offset": offset,
        "has_prev": page > 1,
        "has_next": page < pages,
        "records": matched[offset: offset + size],
        "filters": filters,
        "sort": sort,
    }


def _int_param(value, name, minimum, maximum=None):
    """把 HTTP 参数转成正整数并做范围检查，非法值抛业务错误而不是 500。"""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise RecordListError("%s 必须是整数" % name)
    if number < minimum or (maximum is not None and number > maximum):
        raise RecordListError("%s 超出允许范围" % name)
    return number


# ============ 5. 详情 ============
def record_detail(record_id, sort=DEFAULT_SORT, records=None):
    """
    单条记录详情，附带"上一笔 / 下一笔"。

    相邻项按当前排序实时计算，因此用户改排序后翻阅顺序依然正确；
    详情页据此可以连续翻阅，不必退回列表再点。

    :return: {
        "record": {...},
        "neighbors": {"prev": {...}|None, "next": {...}|None, "index": int, "total": int}
    }
    """
    if records is None:
        records = load_all_records()
    record = _find(records, record_id)

    ordered = _sort_records([r for r in records if isinstance(r, dict)], sort)
    ids = [str(r.get("id")) for r in ordered]
    index = ids.index(str(record.get("id")))

    return {
        "record": record,
        "neighbors": {
            "prev": _brief(ordered[index - 1]) if index > 0 else None,
            "next": _brief(ordered[index + 1]) if index + 1 < len(ordered) else None,
            "index": index + 1,
            "total": len(ordered),
        },
    }


def _brief(record):
    """列表/相邻导航只需要这几个字段，避免整条记录塞进模板。"""
    if not record:
        return None
    return {
        "id": record.get("id"),
        "date": record.get("date"),
        "type": record.get("type"),
        "amount": record.get("amount"),
        "category": record.get("category"),
    }


# ============ 6. 编辑 ============
def update_record(record_id, updates):
    """
    编辑记录：先按白名单过滤字段、规范化数值，再交给 storage.py 局部更新。

    storage.update_record 只改传入的字段，未传字段保持原值，
    因此前端只提交改动过的字段也不会丢数据。

    :return: {"record": 更新后的记录, "changed": [实际生效的字段]}
    :raises RecordListError: 字段非法 / 记录不存在
    """
    if not isinstance(updates, dict) or not updates:
        raise RecordListError("没有需要保存的修改")

    unknown = set(updates) - set(EDITABLE_FIELDS)
    if unknown:
        raise RecordListError("不支持修改的字段：" + "、".join(sorted(unknown)))

    cleaned = {}
    if "date" in updates:
        cleaned["date"] = _normalize_date(updates["date"])
    if "type" in updates:
        cleaned["type"] = _normalize_type(updates["type"])
    if "amount" in updates:
        cleaned["amount"] = _normalize_amount(updates["amount"])
    if "category" in updates:
        cleaned["category"] = _normalize_text(updates["category"], "类别", MAX_CATEGORY_LEN)
    if "note" in updates:
        cleaned["note"] = _normalize_text(updates["note"], "备注", MAX_NOTE_LEN, required=False)

    if _use_storage():
        try:
            record = storage.update_record(record_id, cleaned)
        except ValueError as e:
            # storage 的校验错误（金额小数位、日期格式等）转成页面提示，避免 500
            raise RecordListError(str(e))
        if record is None:
            raise RecordListError("记录不存在或已被删除")
    else:
        records = load_all_records()
        record = _find(records, record_id)
        merged = dict(record)
        merged.update(cleaned)
        merged["amount"] = _normalize_amount(merged.get("amount"))
        merged["date"] = _normalize_date(merged.get("date"))
        merged["type"] = _normalize_type(merged.get("type"))
        merged["category"] = _normalize_text(merged.get("category"), "类别", MAX_CATEGORY_LEN)
        merged["note"] = _normalize_text(merged.get("note", ""), "备注", MAX_NOTE_LEN, required=False)
        for index, item in enumerate(records):
            if str(item.get("id")) == str(record_id):
                records[index] = merged
                break
        _write_all_records(records)
        record = merged

    return {"record": record, "changed": sorted(cleaned)}


def _normalize_date(value):
    """日期必须是严格 YYYY-MM-DD，'2026/11/7' 这类模糊写法直接拒绝。"""
    text = str(value or "").strip()
    if not text:
        raise RecordListError("日期不能为空")
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        raise RecordListError("日期格式应为 YYYY-MM-DD，例如 2026-11-07")
    if parsed.isoformat() != text:
        raise RecordListError("日期格式应为 YYYY-MM-DD，例如 2026-11-07")
    return text


def _normalize_type(value):
    text = str(value or "").strip()
    if text not in VALID_TYPES:
        raise RecordListError("类型只能是 income(收入) 或 expense(支出)")
    return text


def _normalize_amount(value):
    """
    金额统一走 Decimal 再四舍五入到分，返回 float。
    这样做既挡掉 'abc'、'-3'、0 这类非法值，也避免 19.999 被 storage 拒收。
    """
    if value in (None, ""):
        raise RecordListError("金额不能为空")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise RecordListError("金额必须是数字，例如 25.5")
    if amount.is_nan() or amount.is_infinite():
        raise RecordListError("金额必须是有限数字")
    if amount <= 0:
        raise RecordListError("金额必须大于 0")
    amount = amount.quantize(_CENT, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise RecordListError("金额四舍五入后为 0，请填写不小于 0.01 的金额")
    return float(amount)


def _normalize_text(value, field, max_len, required=True):
    text = str(value or "").strip()
    if required and not text:
        raise RecordListError("%s不能为空" % field)
    if len(text) > max_len:
        raise RecordListError("%s长度不能超过 %d 个字符" % (field, max_len))
    return text


# ============ 7. 删除 ============
def delete_record(record_id):
    """
    删除记录。

    :return: {"id": 被删记录 id, "deleted": True, "total": 删除后总条数}
    :raises RecordListError: 记录不存在
    """
    rid = str(record_id or "").strip()
    if not rid:
        raise RecordListError("记录 id 不能为空")

    if _use_storage():
        # storage 返回 False 表示记录不存在
        if not storage.delete_record(rid):
            raise RecordListError("记录不存在或已被删除")
    else:
        records = load_all_records()
        _find(records, rid)
        remaining = [r for r in records if str(r.get("id")) != rid]
        _write_all_records(remaining)

    return {"id": rid, "deleted": True, "total": len(load_all_records())}


# ============ 8. Flask 蓝图（给组长A 集成到 app.py） ============
# 在 app.py 里写：
#   from record_list import bp as record_list_bp
#   app.register_blueprint(record_list_bp)
if _HAS_FLASK:
    bp = Blueprint("record_list", __name__)

    # 页面路由参数名与筛选条件同名，模板里可直接把 filters 回填到表单
    PAGE_ARGS = ("page", "size", "sort", "keyword", "type", "category",
                 "start", "end", "min_amount", "max_amount")

    def _filters_from_request():
        return {
            "keyword": request.args.get("keyword", ""),
            "type": request.args.get("type", ""),
            "category": request.args.get("category", ""),
            "start": request.args.get("start", ""),
            "end": request.args.get("end", ""),
            "min_amount": request.args.get("min_amount", ""),
            "max_amount": request.args.get("max_amount", ""),
        }

    def _int_arg(name, default, minimum=1, maximum=None):
        raw = request.args.get(name, "")
        if str(raw).strip() == "":
            return default
        return _int_param(raw, name, minimum, maximum)

    @bp.get("/records")
    def page_records():
        """
        GET /records —— 记录列表页（服务端渲染，无 JS 依赖）

        支持：?page=&size=&sort=&keyword=&type=&category=&start=&end=&min_amount=&max_amount=&focus=<id>
        focus 指定某条记录时，页面上方展开它的详情面板（含编辑表单、上一笔/下一笔）。
        """
        try:
            size = _int_arg("size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
            sort = request.args.get("sort", DEFAULT_SORT) or DEFAULT_SORT
            filters = _filters_from_request()
            result = list_records(
                page=_int_arg("page", 1),
                size=size,
                sort=sort,
                **filters
            )
            error = ""
        except RecordListError as e:
            # 参数非法时退回默认列表，并在页面顶部提示，而不是直接 500
            result = list_records()
            error = str(e)
            sort = DEFAULT_SORT
            filters = {}

        focus_id = request.args.get("focus", "").strip()
        detail = None
        if focus_id:
            try:
                # 详情按当前排序计算相邻记录，用户改了排序后"上一笔/下一笔"依旧正确
                detail = record_detail(focus_id, sort=sort)
            except RecordListError:
                detail = None

        def build_url(**overrides):
            """
            生成"保留当前筛选条件"的列表链接：翻页、查看详情、上一笔/下一笔都用它。
            模板里直接 build_url(page=3) / build_url(focus=xxx) 调用，避免在 Jinja 里拼查询串。
            """
            args = {"page": result["page"], "size": result["size"], "sort": result["sort"]}
            args.update(result["filters"])
            args.update(overrides)
            args = {k: v for k, v in args.items() if str(v or "").strip() != ""}
            return url_for("record_list.page_records", **args)

        return render_template(
            "list.html",
            result=result,
            filters=result["filters"],
            sort=result["sort"],
            detail=detail,
            category_options=_category_options(),
            build_url=build_url,
            error=error,
            notice=request.args.get("notice", ""),
        )

    def _category_options():
        """
        类别下拉选项：优先读成员F 的 category.py，读不到则用当前记录里出现过的类别。
        这样即使 F 的模块尚未合并，筛选也不缺选项。
        """
        try:
            import category
            names = [c.get("name") for c in category.list_categories() if c.get("name")]
            if names:
                return names
        except Exception:
            pass
        names = sorted({str(r.get("category", "")) for r in load_all_records() if r.get("category")})
        return [n for n in names if n]

    @bp.get("/api/records")
    def api_list_records():
        """GET /api/records?page=&size=&sort=&keyword=&type=&category=&start=&end=&min_amount=&max_amount="""
        try:
            size = _int_arg("size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
            data = list_records(
                page=_int_arg("page", 1),
                size=size,
                sort=request.args.get("sort", DEFAULT_SORT) or DEFAULT_SORT,
                **_filters_from_request()
            )
            return jsonify({"code": 0, "data": data})
        except RecordListError as e:
            return jsonify({"code": 1, "msg": str(e)}), 400

    @bp.get("/api/records/<record_id>")
    def api_record_detail(record_id):
        """GET /api/records/<id> —— 详情 + 相邻记录，供前端按需拉取"""
        try:
            return jsonify({"code": 0, "data": record_detail(record_id)})
        except RecordListError as e:
            return jsonify({"code": 1, "msg": str(e)}), 404

    @bp.post("/records/<record_id>/edit")
    def page_edit_record(record_id):
        """
        POST /records/<id>/edit —— 表单提交编辑（编辑、删除都用原生表单，不依赖 JS）

        成功后回到列表页并保留原筛选条件与页码，避免用户改完一条就"迷路"。
        """
        updates = {k: request.form.get(k, "") for k in EDITABLE_FIELDS if k in request.form}
        try:
            update_record(record_id, updates)
        except RecordListError as e:
            return redirect(url_for("record_list.page_records", focus=record_id, notice="保存失败：" + str(e),
                                    **_keep_args()))
        return redirect(url_for("record_list.page_records", focus=record_id, notice="已保存修改",
                                **_keep_args()))

    @bp.post("/records/<record_id>/delete")
    def page_delete_record(record_id):
        """POST /records/<id>/delete —— 删除记录后回到列表（页码越界会自动夹到最后一页）"""
        try:
            delete_record(record_id)
        except RecordListError as e:
            return redirect(url_for("record_list.page_records", notice="删除失败：" + str(e), **_keep_args()))
        return redirect(url_for("record_list.page_records", notice="已删除 1 条记录", **_keep_args()))

    def _keep_args():
        """
        把当前页码/每页条数/排序/筛选条件带回列表页。

        表单里统一用 ret_ 前缀存放这些状态，避免与编辑表单自身的 type / category 字段重名：
        否则跳回列表时会把"这条记录的类别/类型"误当成"筛选条件"。
        """
        mapping = {
            "page": "ret_page",
            "size": "ret_size",
            "sort": "ret_sort",
            "keyword": "ret_keyword",
            "type": "ret_type",
            "category": "ret_category",
            "start": "ret_start",
            "end": "ret_end",
            "min_amount": "ret_min_amount",
        }
        keep = {}
        for key, form_key in mapping.items():
            value = request.form.get(form_key, "")
            if str(value).strip() != "":
                keep[key] = value
        return keep
else:  # pragma: no cover
    bp = None

# 团队里两种命名都出现过（stats.py 用 bp、record_add.py 用 record_add_bp），
# 这里同时导出两个名字，成员A 用哪个都不会报 ImportError。
record_list_bp = bp


# ============ 自测：直接 python record_list.py 即可单独跑起来 ============
if __name__ == "__main__":
    # 仅本地自测：数据文件不存在时写 6 条样例（不要把这些数据提交到仓库，成员B 会放样例数据）
    if not os.path.exists(DATA_FILE):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        _write_all_records([
            {"id": "r001", "type": "expense", "date": "2026-11-07", "amount": 25.5, "category": "饮食", "note": "午饭", "account": "默认账户"},
            {"id": "r002", "type": "expense", "date": "2026-11-07", "amount": 4.0, "category": "交通", "note": "公交", "account": "默认账户"},
            {"id": "r003", "type": "income", "date": "2026-11-06", "amount": 300.0, "category": "兼职", "note": "家教", "account": "默认账户"},
            {"id": "r004", "type": "expense", "date": "2026-11-05", "amount": 88.0, "category": "饮食", "note": "聚餐 AA", "account": "默认账户"},
            {"id": "r005", "type": "expense", "date": "2026-11-04", "amount": 59.9, "category": "教育", "note": "教材", "account": "默认账户"},
            {"id": "r006", "type": "income", "date": "2026-11-03", "amount": 1200.0, "category": "工资", "note": "生活费", "account": "默认账户"},
        ])

    print("=== 最近 3 笔 ===")
    for r in list_records(size=3)["records"]:
        print(r)

    print("\n=== 只看 11-05 之后的支出，金额 >= 50 ===")
    print([r["id"] for r in list_records(type="expense", start="2026-11-05", min_amount=50)["records"]])
    print("\n注意：自测会写入 data/records.json（该文件由成员B 负责）。"
          "\n      演示结束后执行  git checkout -- data/records.json  还原，切勿把它提交进仓库。")

    FLASK_FALLBACK_BASE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>个人记账本</title>
<style>body{font-family:"Microsoft YaHei",system-ui,sans-serif;margin:0;background:#f4f6f5;color:#1f2a28}
nav{padding:12px 20px;background:#0f766e;color:#fff}main{max-width:960px;margin:20px auto;padding:0 16px}</style>
</head><body><nav>个人记账本 · 本地自测</nav>
<main>{% block content %}{% endblock %}</main></body></html>"""

    if not _HAS_FLASK:
        print("\n未安装 Flask，跳过页面演示（pip install flask 后可看页面）")
    else:
        from flask import Flask
        from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader

        app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
        # 成员H 的 base.html 合并后自动使用真实文件；未合并时用内置兜底布局，保证本模块能单独演示
        app.jinja_loader = ChoiceLoader([
            FileSystemLoader(os.path.join(BASE_DIR, "templates")),
            DictLoader({"base.html": FLASK_FALLBACK_BASE}),
        ])
        app.register_blueprint(bp)
        import sys
        port = int(sys.argv[1]) if len(sys.argv) > 1 and str(sys.argv[1]).isdigit() else 5001
        print("\n打开 http://127.0.0.1:%d/records 查看列表页" % port)
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
