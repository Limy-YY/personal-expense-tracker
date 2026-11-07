# -*- coding: utf-8 -*-
"""
query.py — 筛选与搜索模块（成员G 独立负责）
============================================================
模块职责：
  1. 关键字搜索（多词“且”匹配：id / 类别 / 备注 / 账户）；
  2. 组合条件筛选（类型 + 类别 + 账户 + 日期区间 + 金额区间 + 指定 id，条件之间“且”）；
  3. 排序（日期 / 金额 / id，升序或降序）与分页，供「记录查看」（成员D）直接用；
  4. 输出筛选下拉框的取值（类别 / 账户 / 类型）。

定位：**统一查询入口**。本模块只读，绝不写数据；写入只走成员B 的 storage 层。
汇总/统计仍由成员E 的 stats.py 负责，两边不重复实现。

数据文件（全项目唯一的一份）：
  data/records.json -> [                      # 顶层是记录数组，不是字典
      {"id": "r1", "type": "expense"|"income", "date": "YYYY-MM-DD",
       "amount": 12.5, "category": "饮食", "note": "午餐", "account": "微信"},
      ...
  ]
  说明：amount 一律存正数，正负由 type 决定；category 存分类名字符串。
  兼容：旧版 data.json 的 {"records": [...], "categories": [...]} 结构仍能读（只取 records）。

依赖 storage 层（成员B）已约定的行为（本模块据此假设，不重复实现）：
  load_records() 取全部记录；update_record(id, updates) 为部分更新、id 不允许修改、
  记录不存在返回 None；分类被删除后其下记录 category 自动归入「其他」，且「其他」禁止删除
  —— 因此查询结果里的 category 必然是现存分类，无需特殊兜底。
  路径上本模块直接沿用 storage.DATA_FILE，读的就是成员B 写的那份文件，不会产生
  “第二个数据文件”；读侧只做结构级校验（不重复 storage 的字段级校验），
  这样一条脏记录不会让整页查询失败。

对外接口（给成员A 的 app.py / 成员D 的查看页调用，勿随意改名）：
  query_records(**cond)                     -> list[dict]    组合查询 + 排序
  query_page(**cond)                        -> dict           分页查询（含 total / 页码信息）
  count_records(**cond)                     -> int
  latest_records(n=10, **cond)              -> list[dict]    最近 N 条
  apply_filters(records, **cond)            -> list[dict]    纯函数版，注入 records 便于测试
  distinct_values(field, **cond)            -> list[str]     下拉框取值
  约定条件名（均可省略，也兼容 date_from / date_to / amount_min / amount_max / rtype 等叫法）：
    keyword, type, category, account, ids, start_date, end_date,
    min_amount, max_amount, sort_by, order, page, page_size
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence

# Flask 是部署依赖；本地自测时没装也不影响业务函数（与 category.py / stats.py 同一写法）
try:
    from flask import Blueprint, request, jsonify
    _HAS_FLASK = True
except ImportError:
    _HAS_FLASK = False

# 数据存储层：成员B 的 storage.py 合入后自动切换过去
try:
    import storage
    _HAS_STORAGE = True
except ImportError:
    _HAS_STORAGE = False

# ============ 配置 ============
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 记录文件的唯一路径：默认取 storage 层声明的 DATA_FILE（data/records.json），
# 保证与成员B 读写的是同一份文件；storage.py 尚未合入时退回同一路径约定。
DATA_FILE = (
    str(getattr(storage, "DATA_FILE", os.path.join(_BASE_DIR, "data", "records.json")))
    if _HAS_STORAGE
    else os.path.join(_BASE_DIR, "data", "records.json")
)

TYPE_INCOME = "income"
TYPE_EXPENSE = "expense"
# 兜底分类（受保护、不可删除）：分类删除后记录归属，用于汇总兜底
DEFAULT_CATEGORY = "其他"
RECORD_FIELDS = ("id", "type", "date", "amount", "category", "note", "account")

_DATE_FMT = "%Y-%m-%d"
_MIN_DATE = _dt.date(1970, 1, 1)     # 日期缺失/非法时的排序占位（视为最早）


# ============ 数据读取 ============
def _load_records() -> List[Dict[str, Any]]:
    """
    取全部记录（只读）。

    正常运行时调用成员B 的 storage.load_records()（唯一数据出处，字段校验也在那一层）；
    仅当 DATA_FILE 被外部重定向（单元测试注入临时文件）时，才直读 DATA_FILE，
    这样测试不碰真实账本，生产路径又保持分层。

    直读分支两种结构都认：顶层记录数组（现行），或旧版 {"records": [...], "categories": [...]}。
    文件损坏/结构异常抛 RuntimeError，不静默回退空数组。
    """
    path = str(DATA_FILE)

    # 正常态：DATA_FILE 就是 storage 声明的那份文件 -> 走存储层
    if _HAS_STORAGE and os.path.abspath(path) == os.path.abspath(str(storage.DATA_FILE)):
        return storage.load_records()

    # 测试态：DATA_FILE 被重定向到临时文件 -> 直读（storage 不认这个路径）
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"{os.path.basename(path)} 已损坏：{e}，请联系存储模块恢复备份") from e
    except OSError as e:
        raise RuntimeError(f"{os.path.basename(path)} 读取失败：{e}") from e

    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data["records"]
    raise RuntimeError(
        f"{os.path.basename(path)} 结构异常：既不是记录数组，也没有 records 数组（路径：{path}）"
    )


# ============ 条件标准化 ============
# 条件名 -> 标准名（兼容前端和其他模块的各种叫法）
_KEY_ALIASES = {
    "q": "keyword", "kw": "keyword", "search": "keyword",
    "date_from": "start_date", "from_date": "start_date", "begin_date": "start_date",
    "date_to": "end_date", "to_date": "end_date",
    "amount_min": "min_amount", "amount_max": "max_amount",
    "rtype": "type",                # stats.py 里的叫法
    "sort": "sort_by", "order_by": "sort_by",
}

_ALLOWED_KEYS = {
    "keyword", "type", "category", "account", "ids",
    "start_date", "end_date", "min_amount", "max_amount", "sort_by", "order",
}

_TYPE_MAP = {
    "income": TYPE_INCOME, "收入": TYPE_INCOME, "in": TYPE_INCOME, "i": TYPE_INCOME,
    "expense": TYPE_EXPENSE, "支出": TYPE_EXPENSE, "out": TYPE_EXPENSE, "e": TYPE_EXPENSE,
}

# “不筛”的写法：空串 / 全部 / all 等，统一视为 None
_NO_FILTER_WORDS = {"", "全部", "所有", "任意", "不限", "all", "any", "*"}

_SORT_ALIASES = {
    "date": "date", "日期": "date", "time": "date", "day": "date",
    "amount": "amount", "金额": "amount", "money": "amount",
    "id": "id", "编号": "id", "序号": "id",
}

_ORDER_ALIASES = {
    "desc": "desc", "descending": "desc", "降序": "desc", "倒序": "desc", "-": "desc",
    "asc": "asc", "ascending": "asc", "升序": "asc", "正序": "asc", "+": "asc",
}


def _norm_text(value: Any) -> str:
    """把任意值规整成用于比较的文本：去空白、小写、None -> ''。"""
    if value is None:
        return ""
    return str(value).strip().casefold()


def _to_list(value: Any, name: str) -> Optional[List[str]]:
    """把单值 / 列表 / 逗号分隔字符串统一成去重列表；空或“全部”返回 None。"""
    if value is None:
        return None
    if isinstance(value, str):
        raw: Iterable[Any] = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raise TypeError(f"{name} 需要字符串或字符串列表，收到 {type(value).__name__}: {value!r}")

    items: List[str] = []
    for item in raw:
        text = "" if item is None else str(item).strip()
        if _norm_text(text) in _NO_FILTER_WORDS:
            continue
        if text not in items:
            items.append(text)
    return items or None


def _to_float(value: Any, name: str) -> Optional[float]:
    """金额条件转 float，容忍前端传来的 '1,000' / '￥100' / '' 等写法。"""
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError(f"{name} 需要数字，收到布尔值: {value!r}")
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if _norm_text(text) in _NO_FILTER_WORDS:
        return None
    for token in ("￥", "¥", "$", ",", "，", " "):
        text = text.replace(token, "")
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{name} 需要数字，收到: {value!r}") from None


def _to_int(value: Any, name: str, minimum: int) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} 需要整数，收到布尔值: {value!r}")
    try:
        number = int(str(value).strip()) if not isinstance(value, int) else value
    except (TypeError, ValueError):
        raise ValueError(f"{name} 需要整数，收到: {value!r}") from None
    if number < minimum:
        raise ValueError(f"{name} 不能小于 {minimum}，收到: {number}")
    return number


def _parse_date(value: Any, name: str) -> Optional[_dt.date]:
    """统一解析成 date；支持 'YYYY-MM-DD'、date/datetime 对象、带时间的字符串。"""
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if not isinstance(value, str):
        raise TypeError(f"{name} 需要 YYYY-MM-DD 格式的日期，收到 {type(value).__name__}: {value!r}")

    text = value.strip()
    if _norm_text(text) in _NO_FILTER_WORDS:
        return None
    try:
        return _dt.datetime.strptime(text[:10], _DATE_FMT).date()
    except ValueError:
        raise ValueError(f"{name} 需要 YYYY-MM-DD 格式的日期，收到: {value!r}") from None


def _record_date(record: Dict[str, Any]) -> Optional[_dt.date]:
    """读取记录日期；脏数据（缺失/非法）返回 None，不让整页查询崩。"""
    raw = record.get("date")
    if isinstance(raw, _dt.datetime):
        return raw.date()
    if isinstance(raw, _dt.date):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return _dt.datetime.strptime(raw.strip()[:10], _DATE_FMT).date()
    except ValueError:
        return None


def _record_amount(record: Dict[str, Any]) -> float:
    try:
        return float(record.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def _record_type(record: Dict[str, Any]) -> str:
    """记录类型标准化为 income/expense；无法识别时返回小写原文，比较时自然被排除。"""
    raw = _norm_text(record.get("type"))
    return _TYPE_MAP.get(raw, raw)


def _search_text(record: Dict[str, Any]) -> str:
    """
    关键字检索的文本池：ID、类别、备注、账户。

    刻意不包含 amount 和 date：
      - 金额：否则搜“2”会命中一片（金额用 min_amount / max_amount 专管）；
      - 日期：否则每笔都以“2026”开头，搜年份/月份等于全量（日期用 start_date / end_date 专管）。
    """
    return " ".join(
        _norm_text(record.get(field)) for field in ("id", "category", "note", "account")
    )


def _normalize_conditions(raw: Dict[str, Any], allow_paging: bool = False) -> Dict[str, Any]:
    """校验并标准化查询条件；不认识的参数名直接报错，避免前端拼错字段被静默忽略。"""
    allowed = set(_ALLOWED_KEYS)
    if allow_paging:
        allowed |= {"page", "page_size"}

    given: Dict[str, Any] = {}
    for key, value in raw.items():
        name = _KEY_ALIASES.get(key, key)
        if name not in allowed:
            raise TypeError(f"不支持的查询条件: {key!r}（可用: {', '.join(sorted(allowed))}）")
        if name in given and given[name] is not None:
            raise TypeError(f"查询条件重复: {key!r} 与 {name!r} 指向同一项")
        given[name] = value

    # 关键字：按空白切词，多个词之间“且”
    tokens = [t for t in _norm_text(given.get("keyword")).split() if t]

    # 类型：单值
    type_raw = given.get("type")
    if type_raw is None or _norm_text(type_raw) in _NO_FILTER_WORDS:
        type_value: Optional[str] = None
    else:
        key = _norm_text(type_raw)
        if key not in _TYPE_MAP:
            raise ValueError(f"type 只支持 income / expense（或“收入 / 支出 / 全部”），收到: {type_raw!r}")
        type_value = _TYPE_MAP[key]

    categories = _to_list(given.get("category"), "category")
    accounts = _to_list(given.get("account"), "account")
    ids = _to_list(given.get("ids"), "ids")

    start_date = _parse_date(given.get("start_date"), "start_date")
    end_date = _parse_date(given.get("end_date"), "end_date")
    if start_date and end_date and start_date > end_date:
        raise ValueError(f"开始日期不能晚于结束日期: {start_date} > {end_date}")

    min_amount = _to_float(given.get("min_amount"), "min_amount")
    max_amount = _to_float(given.get("max_amount"), "max_amount")
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise ValueError(f"最小金额不能大于最大金额: {min_amount} > {max_amount}")

    sort_raw = given.get("sort_by")
    sort_key = "date" if sort_raw is None or _norm_text(sort_raw) in _NO_FILTER_WORDS else _norm_text(sort_raw)
    if sort_key not in _SORT_ALIASES:
        raise ValueError(f"sort_by 只支持 date / amount / id，收到: {sort_raw!r}")
    sort_by = _SORT_ALIASES[sort_key]

    order_raw = given.get("order")
    if isinstance(order_raw, bool):
        order = "asc" if order_raw else "desc"
    elif order_raw is None or _norm_text(order_raw) in _NO_FILTER_WORDS:
        order = "desc"
    else:
        order_key = _norm_text(order_raw)
        if order_key not in _ORDER_ALIASES:
            raise ValueError(f"order 只支持 asc / desc（或“升序 / 降序”），收到: {order_raw!r}")
        order = _ORDER_ALIASES[order_key]

    result: Dict[str, Any] = {
        "keyword_tokens": tokens,
        "type": type_value,
        "categories": categories,
        "accounts": accounts,
        "ids": ids,
        "start_date": start_date,
        "end_date": end_date,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "sort_by": sort_by,
        "order": order,
    }
    if allow_paging:
        result["page"] = _to_int(given.get("page", 1), "page", 1)
        result["page_size"] = _to_int(given.get("page_size", 20), "page_size", 1)
    return result


# ============ 匹配与排序 ============
def _matches(record: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    """单条记录是否满足全部条件（条件之间“且”，同一条件的多个值之间“或”）。"""
    if cond["keyword_tokens"]:
        haystack = _search_text(record)
        if not all(token in haystack for token in cond["keyword_tokens"]):
            return False

    if cond["type"] is not None and _record_type(record) != cond["type"]:
        return False

    if cond["ids"] is not None and str(record.get("id", "")) not in cond["ids"]:
        return False

    if cond["categories"] is not None:
        wanted = {_norm_text(c) for c in cond["categories"]}
        if _norm_text(record.get("category")) not in wanted:
            return False

    if cond["accounts"] is not None:
        wanted = {_norm_text(a) for a in cond["accounts"]}
        if _norm_text(record.get("account")) not in wanted:
            return False

    if cond["start_date"] is not None or cond["end_date"] is not None:
        day = _record_date(record)
        if day is None:                     # 日期缺失/非法，无法落在区间内
            return False
        if cond["start_date"] is not None and day < cond["start_date"]:
            return False
        if cond["end_date"] is not None and day > cond["end_date"]:
            return False

    if cond["min_amount"] is not None or cond["max_amount"] is not None:
        amount = _record_amount(record)
        if cond["min_amount"] is not None and amount < cond["min_amount"]:
            return False
        if cond["max_amount"] is not None and amount > cond["max_amount"]:
            return False

    return True


def _sort_records(records: List[Dict[str, Any]], cond: Dict[str, Any]) -> List[Dict[str, Any]]:
    """排序：主键按 sort_by/order，次键固定用 id 保证同值时顺序稳定（分页不会跳条）。"""
    order = cond["order"]

    if cond["sort_by"] == "amount":
        def key(record: Dict[str, Any]):
            amount = _record_amount(record)
            return (-amount if order == "desc" else amount, str(record.get("id", "")))
        return sorted(records, key=key)

    if cond["sort_by"] == "id":
        return sorted(records, key=lambda r: str(r.get("id", "")), reverse=(order == "desc"))

    # 默认按日期；日期缺失/非法视为最早，降序时排在最后
    def date_key(record: Dict[str, Any]):
        return (_record_date(record) or _MIN_DATE, str(record.get("id", "")))
    return sorted(records, key=date_key, reverse=(order == "desc"))


# ============ 对外接口 ============
def apply_filters(records: Sequence[Dict[str, Any]], **conditions: Any) -> List[Dict[str, Any]]:
    """
    对**已加载**的记录做筛选 + 排序（纯函数，不读文件），方便测试和复用。
    返回浅拷贝的新列表，不修改传入的 records。
    注意：名字特意不叫 filter_records，避免和 stats.py 的同名函数混淆。
    """
    if records is None:
        records = []
    cond = _normalize_conditions(conditions)
    picked = [dict(record) for record in records if _matches(record, cond)]
    return _sort_records(picked, cond)


def query_records(**conditions: Any) -> List[Dict[str, Any]]:
    """
    统一查询入口：取全部记录 → 组合条件筛选 → 排序。

    支持的条件（都可省略、可任意组合）：
        keyword     关键字，空格分词后需全部命中；检索 id / 类别 / 备注 / 账户（金额与日期不参与）
        type        income / expense，也接受“收入 / 支出 / 全部”（别名 rtype）
        category    类别，单值、列表或逗号分隔，多值时“或”
        account     账户，同上
        ids         记录 ID 列表，精确命中
        start_date  起始日期（含当天），YYYY-MM-DD（别名 date_from）
        end_date    结束日期（含当天），YYYY-MM-DD（别名 date_to）
        min_amount  金额下限（含）（别名 amount_min）
        max_amount  金额上限（含）（别名 amount_max）
        sort_by     date / amount / id，默认 date
        order       desc / asc，默认 desc
    """
    return apply_filters(_load_records(), **conditions)


def count_records(**conditions: Any) -> int:
    """只取命中条数（分页总数、轻量校验用）。"""
    return len(query_records(**conditions))


def query_page(**conditions: Any) -> Dict[str, Any]:
    """
    分页查询，给查看页（成员D）直接用。page 从 1 开始，page_size 默认 20。

    :return: {"items": [...], "total": 命中总数, "page": 当前页, "page_size": 每页条数,
              "total_pages": 总页数, "has_prev": bool, "has_next": bool}
    页码越界不报错，返回空 items，由前端决定是否回跳；无数据时 total_pages 为 0。
    """
    cond = _normalize_conditions(conditions, allow_paging=True)
    page, page_size = cond.pop("page"), cond.pop("page_size")

    rows = [dict(record) for record in _load_records() if _matches(record, cond)]
    rows = _sort_records(rows, cond)

    total = len(rows)
    total_pages = math.ceil(total / page_size) if total else 0
    start = (page - 1) * page_size

    return {
        "items": rows[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_prev": page > 1 and total > 0,
        "has_next": page < total_pages,
    }


def latest_records(n: int = 10, **conditions: Any) -> List[Dict[str, Any]]:
    """最近 n 条（先按条件筛，再按日期倒序取前 n），查看页“最近记录”直接用。"""
    n = _to_int(n, "n", 1)
    return query_records(**conditions)[:n]


def distinct_values(field: str, **conditions: Any) -> List[str]:
    """
    取某字段在（可筛选范围内的）所有取值，供筛选下拉框。
    支持 category / account / type；按出现次数从多到少、同次数按名称排序。
    """
    name = _norm_text(field)
    if name in ("category", "类别", "分类"):
        real = "category"
    elif name in ("account", "账户", "账号"):
        real = "account"
    elif name in ("type", "类型"):
        real = "type"
    else:
        raise ValueError(f"distinct_values 只支持 category / account / type，收到: {field!r}")

    counter: Dict[str, int] = {}
    for record in query_records(**conditions):
        if real == "type":
            text = _record_type(record)
        else:
            text = str(record.get(real) or "").strip()
        if not text:
            continue
        counter[text] = counter.get(text, 0) + 1

    return [value for value, _ in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]


# ============ Flask 蓝图（给组长A 集成到 app.py） ============
# 在 app.py 里写：
#   from query import bp
#   if bp: app.register_blueprint(bp)
if _HAS_FLASK:
    bp = Blueprint("query", __name__, url_prefix="/api/query")

    @bp.get("/records")
    def api_records():
        """GET /api/query/records?keyword=&type=&category=&account=&start_date=&end_date=&min_amount=&max_amount=&sort_by=&order=&page=&page_size="""
        try:
            return jsonify({"code": 0, "data": query_page(**request.args)})
        except (ValueError, TypeError) as e:
            return jsonify({"code": 1, "msg": str(e)}), 400
        except RuntimeError as e:
            return jsonify({"code": 1, "msg": str(e)}), 500

    @bp.get("/latest")
    def api_latest():
        """GET /api/query/latest?n=10（其余条件同上）"""
        try:
            n = _to_int(request.args.get("n", 10), "n", 1)
            return jsonify({"code": 0, "data": latest_records(n, **{
                k: v for k, v in request.args.items() if k != "n"
            })})
        except (ValueError, TypeError) as e:
            return jsonify({"code": 1, "msg": str(e)}), 400
        except RuntimeError as e:
            return jsonify({"code": 1, "msg": str(e)}), 500

    @bp.get("/values")
    def api_values():
        """GET /api/query/values?field=category（给筛选下拉框；可带 category/account 等范围条件）"""
        try:
            field = request.args.get("field", "category")
            scope = {k: v for k, v in request.args.items() if k not in ("field", "page", "page_size")}
            return jsonify({"code": 0, "data": distinct_values(field, **scope)})
        except (ValueError, TypeError) as e:
            return jsonify({"code": 1, "msg": str(e)}), 400
        except RuntimeError as e:
            return jsonify({"code": 1, "msg": str(e)}), 500
else:
    bp = None


# ============ 自测：直接 python query.py 即可跑（使用临时 data.json，绝不碰真实数据） ============
if __name__ == "__main__":
    import shutil
    import tempfile

    demo = [
        {"id": "r1", "type": "expense", "date": "2026-11-05", "amount": 28.5,   "category": "饮食", "note": "午餐", "account": "微信"},
        {"id": "r2", "type": "expense", "date": "2026-11-06", "amount": 6.0,    "category": "交通", "note": "地铁", "account": "支付宝"},
        {"id": "r3", "type": "income",  "date": "2026-11-05", "amount": 6500.0, "category": "工资", "note": "十月工资", "account": "银行卡"},
        {"id": "r4", "type": "expense", "date": "2026-10-18", "amount": 1800.0, "category": "居住", "note": "房租", "account": "银行卡"},
        {"id": "r5", "type": "expense", "date": "2026-11-07", "amount": 120.0,  "category": "饮食", "note": "火锅", "account": "微信"},
    ]

    print("=== 全部（默认日期倒序）===")
    for r in apply_filters(demo):
        print(r["date"], r["id"], r["category"], r["amount"])

    print("\n=== 11 月餐饮支出，金额降序 ===")
    for r in apply_filters(demo, type="支出", category="餐饮,饮食",
                           start_date="2026-11-01", end_date="2026-11-30",
                           sort_by="amount", order="desc"):
        print(r["date"], r["category"], r["amount"], r["note"])

    print("\n=== 关键字“微信 火锅” ===")
    print([r["id"] for r in apply_filters(demo, keyword="微信 火锅")])

    print("\n=== 金额 / 日期不参与关键字检索（否则搜 2、搜 2026 等于全量）===")
    for bad_kw in ("2026", "2026-11"):
        assert apply_filters(demo, keyword=bad_kw) == [], f"关键字 {bad_kw!r} 不该命中任何记录"
    assert len(apply_filters(demo, keyword="2")) < len(demo), "关键字 '2' 不该命中全部"
    print("搜 2026 / 2026-11 命中 0 条、搜 2 不再全量：通过")

    print("\n=== 金额 6~120（含边界）===")
    print([(r["id"], r["amount"]) for r in apply_filters(demo, min_amount="6", max_amount="120")])

    print("\n=== 纯函数不改原数据 ===")
    snapshot = [dict(r) for r in demo]
    apply_filters(demo, category="饮食")
    print("未被修改：", demo == snapshot)

    print("\n=== 非法条件应报错 ===")
    for bad in ({"start_date": "2026-13-01"}, {"sort_by": "note"}, {"min_amount": 10, "max_amount": 5}):
        try:
            apply_filters(demo, **bad)
        except (ValueError, TypeError) as e:
            print("预期报错：", e)

    print("\n=== 分页：金额从高到低，page_size=2 ===")
    tmp_dir = tempfile.mkdtemp(prefix="query_test_")
    DATA_FILE = os.path.join(tmp_dir, "records.json")   # 覆盖模块内路径，指向临时文件（绝不碰真实账本）
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        # 与 data/records.json 同一结构：顶层就是记录数组
        json.dump(demo, f, ensure_ascii=False, indent=2)
    try:
        print("当前取数文件：", DATA_FILE)
        p1 = query_page(sort_by="amount", order="desc", page_size=2, page=1)
        p2 = query_page(sort_by="amount", order="desc", page_size=2, page=2)
        print("第1页:", [(r["id"], r["amount"]) for r in p1["items"]], "total=", p1["total"],
              "pages=", p1["total_pages"], "has_next=", p1["has_next"])
        print("第2页:", [(r["id"], r["amount"]) for r in p2["items"]], "has_prev=", p2["has_prev"])
        print("越界页（第 9 页）:", query_page(page=9, page_size=2)["items"])

        print("\n=== 最近 2 条（日期倒序）===")
        print([(r["id"], r["date"]) for r in latest_records(2)])

        print("\n=== 下拉取值 ===")
        print("category:", distinct_values("category"))
        print("account :", distinct_values("account"))
        print("type    :", distinct_values("type"))

        print("\n=== 关键字“微信 火锅”（多词且）===")
        print("命中:", [r["id"] for r in query_records(keyword="微信 火锅")])

        print("\n=== 非法条件（应报 400 级错误）===")
        for bad in ({"start_date": "2026-13-01"}, {"sort_by": "note"},
                    {"min_amount": 10, "max_amount": 5}, {"foo": 1}):
            try:
                query_records(**bad)
            except (ValueError, TypeError) as e:
                print("预期报错：", e)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("\n自测结束。")
