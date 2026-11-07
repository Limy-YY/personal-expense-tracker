
"""
个人记账本 - 数据存储模块（storage.py）

对外接口：
    load_records()
    get_record(record_id)
    add_record(record)
    update_record(record_id, updates)
    delete_record(record_id)

数据文件：
    data/records.json

职责：
    JSON 持久化、记录 CRUD、UUID 生成、
    基础数据校验、文件异常处理、安全写入。

不负责：
    Flask API、业务分类管理、筛选搜索、统计分析。
"""

import json
import math
import os
import tempfile
import threading
import uuid

from datetime import date
from pathlib import Path


# ==================== 基础配置 ====================

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "records.json"

DEFAULT_NOTE = ""
DEFAULT_ACCOUNT = "默认账户"

REQUIRED_FIELDS = {
    "type",
    "date",
    "amount",
    "category",
}

OPTIONAL_FIELDS = {
    "note",
    "account",
}

RECORD_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

VALID_TYPES = {"income", "expense"}

# 保护同一 Python 进程内的多线程读写
_STORAGE_LOCK = threading.RLock()


# ==================== 自定义异常 ====================

class StorageError(Exception):
    """数据文件读取、写入或格式损坏时抛出。"""
    pass


# ==================== 内部辅助函数 ====================

def _ensure_data_file():
    """
    确保数据目录及 JSON 文件存在。

    文件不存在时初始化为 []。
    文件已经存在时不覆盖原数据。
    """
    try:
        DATA_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        try:
            with DATA_FILE.open(
                "x",
                encoding="utf-8"
            ) as f:
                f.write("[]\n")

        except FileExistsError:
            pass

    except OSError as e:
        raise StorageError(
            f"初始化数据文件失败：{e}"
        ) from e


def _validate_record(record):
    """
    校验单条记录的基本数据结构。

    这里只检查存储数据是否符合统一格式，
    不检查分类是否存在等业务规则。
    """
    if not isinstance(record, dict):
        raise ValueError("记录必须是字典")

    # 检查必要字段
    missing = REQUIRED_FIELDS - record.keys()

    if missing:
        raise ValueError(
            "缺少必要字段：" + ", ".join(sorted(missing))
        )

    # 检查不支持的字段
    unknown = record.keys() - RECORD_FIELDS - {"id"}

    if unknown:
        raise ValueError(
            "不支持的字段：" + ", ".join(sorted(unknown))
        )

    # 收支类型
    if record["type"] not in VALID_TYPES:
        raise ValueError(
            "type 只能是 income 或 expense"
        )

    # 日期
    record_date = record["date"]

    if not isinstance(record_date, str):
        raise ValueError("date 必须是字符串")

    try:
        parsed_date = date.fromisoformat(record_date)

        if parsed_date.isoformat() != record_date:
            raise ValueError

    except ValueError:
        raise ValueError(
            "date 格式必须为 YYYY-MM-DD，且日期有效"
        ) from None

    # 金额
    amount = record["amount"]

    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
    ):
        raise ValueError("amount 必须是数值")

    if not math.isfinite(amount):
        raise ValueError("amount 必须是有限数值")

    if amount <= 0:
        raise ValueError("amount 必须大于 0")

    # 金额最多保留两位小数
    # 使用字符串转换，避免直接比较浮点乘法结果
    from decimal import Decimal

    decimal_amount = Decimal(str(amount))

    if decimal_amount != decimal_amount.quantize(
        Decimal("0.01")
    ):
        raise ValueError(
            "amount 最多保留两位小数"
        )

    # 分类
    category = record["category"]

    if (
        not isinstance(category, str)
        or not category.strip()
    ):
        raise ValueError(
            "category 必须是非空字符串"
        )

    # 备注
    note = record.get("note", DEFAULT_NOTE)

    if not isinstance(note, str):
        raise ValueError("note 必须是字符串")

    # 账户
    account = record.get(
        "account",
        DEFAULT_ACCOUNT
    )

    if (
        not isinstance(account, str)
        or not account.strip()
    ):
        raise ValueError(
            "account 必须是非空字符串"
        )

    # 记录 ID（如果存在）
    if "id" in record:
        record_id = record["id"]

        if (
            not isinstance(record_id, str)
            or not record_id
        ):
            raise ValueError(
                "id 必须是非空字符串"
            )


def _read_records():
    """
    内部读取函数。

    调用前应持有 _STORAGE_LOCK。
    """
    _ensure_data_file()

    try:
        with DATA_FILE.open(
            "r",
            encoding="utf-8"
        ) as f:
            records = json.load(f)

    except json.JSONDecodeError as e:
        raise StorageError(
            f"JSON 文件格式损坏：{e}"
        ) from e

    except (OSError, UnicodeError) as e:
        raise StorageError(
            f"读取数据失败：{e}"
        ) from e

    if not isinstance(records, list):
        raise StorageError(
            "数据格式错误：JSON 顶层必须是列表"
        )

    # 防止文件内容结构异常
    ids = set()

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise StorageError(
                f"第 {index + 1} 条记录不是对象"
            )

        try:
            _validate_record(record)
        except (ValueError, TypeError) as e:
            raise StorageError(
                f"第 {index + 1} 条记录无效：{e}"
            ) from e

        if "id" not in record:
            raise StorageError(
                f"第 {index + 1} 条记录缺少 id"
            )

        record_id = record["id"]

        if record_id in ids:
            raise StorageError(
                f"发现重复记录 ID：{record_id}"
            )

        ids.add(record_id)

    return records


def _save_records(records):
    """
    安全保存记录。

    先写入同目录临时文件，
    再使用 os.replace() 替换原文件。

    调用前应持有 _STORAGE_LOCK。
    """
    temp_path = None

    try:
        DATA_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DATA_FILE.parent,
            prefix=".records_",
            suffix=".tmp",
            delete=False
        ) as f:

            temp_path = Path(f.name)

            json.dump(
                records,
                f,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )

            f.write("\n")
            f.flush()

            # 尽量确保数据写入磁盘
            os.fsync(f.fileno())

        # 同目录原子替换
        os.replace(temp_path, DATA_FILE)

    except (OSError, TypeError, ValueError) as e:
        raise StorageError(
            f"保存数据失败：{e}"
        ) from e

    finally:
        # 清理尚未被替换的临时文件
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


# ==================== 对外接口 ====================

def load_records():
    """
    获取全部记账记录。

    Returns:
        list[dict]: 全部记录。

    Raises:
        StorageError: 数据文件损坏或读取失败。
    """
    with _STORAGE_LOCK:
        records = _read_records()

        # 返回独立副本，避免调用方直接修改内部数据
        return [
            record.copy()
            for record in records
        ]


def get_record(record_id):
    """
    根据 ID 获取单条记录。

    Args:
        record_id (str): 记录唯一 ID。

    Returns:
        dict | None:
            找到返回记录。
            未找到返回 None。
    """
    with _STORAGE_LOCK:
        records = _read_records()

        for record in records:
            if record["id"] == record_id:
                return record.copy()

        return None


def add_record(record):
    """
    新增记账记录。

    Args:
        record (dict):
            包含 type、date、amount、category
            等字段的记录，不需要提供 id。

    Returns:
        dict: 新增成功后的完整记录。

    Raises:
        ValueError: 记录字段不合法。
        StorageError: 数据读写失败。
    """
    if not isinstance(record, dict):
        raise ValueError(
            "record 必须是字典"
        )

    # 防止调用方字典受到修改
    new_record = record.copy()

    # ID 由存储层生成，不接受外部传入
    new_record.pop("id", None)

    # 填充可选字段
    new_record.setdefault(
        "note",
        DEFAULT_NOTE
    )

    new_record.setdefault(
        "account",
        DEFAULT_ACCOUNT
    )

    # 校验字段
    _validate_record(new_record)

    with _STORAGE_LOCK:
        records = _read_records()

        existing_ids = {
            item["id"]
            for item in records
        }

        # 生成唯一 ID
        record_id = uuid.uuid4().hex

        while record_id in existing_ids:
            record_id = uuid.uuid4().hex

        new_record["id"] = record_id

        records.append(new_record)

        # 成功写入后才返回
        _save_records(records)

        return new_record.copy()


def update_record(record_id, updates):
    """
    根据 ID 部分更新记录。

    只更新 updates 中提供的字段，
    未提供的字段保持不变。

    不允许修改 id。

    Args:
        record_id (str): 记录 ID。
        updates (dict): 要更新的字段。

    Returns:
        dict | None:
            成功返回更新后的记录。
            未找到返回 None。

    Raises:
        ValueError: 更新内容不合法。
        StorageError: 数据读写失败。
    """
    if not isinstance(updates, dict):
        raise ValueError(
            "updates 必须是字典"
        )

    if "id" in updates:
        raise ValueError(
            "不允许修改记录 ID"
        )

    unknown = updates.keys() - RECORD_FIELDS

    if unknown:
        raise ValueError(
            "不支持修改的字段："
            + ", ".join(sorted(unknown))
        )

    with _STORAGE_LOCK:
        records = _read_records()

        for index, record in enumerate(records):

            if record["id"] != record_id:
                continue

            # 复制原记录进行部分更新
            updated_record = record.copy()

            updated_record.update(updates)

            # 对更新后的完整记录进行校验
            _validate_record(updated_record)

            records[index] = updated_record

            _save_records(records)

            return updated_record.copy()

        return None


def delete_record(record_id):
    """
    根据 ID 删除指定记录。

    Args:
        record_id (str): 记录 ID。

    Returns:
        bool:
            删除成功返回 True。
            记录不存在返回 False。

    Raises:
        StorageError: 数据读写失败。
    """
    with _STORAGE_LOCK:
        records = _read_records()

        for index, record in enumerate(records):

            if record["id"] == record_id:

                records.pop(index)

                _save_records(records)

                return True

        return False
