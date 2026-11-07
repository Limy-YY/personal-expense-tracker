
"""个人记账本的数据存储模块：JSON 持久化与 CRUD。"""

import json
import math
import os
import tempfile
import threading
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "records.json"

DEFAULT_NOTE = ""
DEFAULT_ACCOUNT = "默认账户"
REQUIRED_FIELDS = {"type", "date", "amount", "category"}
OPTIONAL_FIELDS = {"note", "account"}
RECORD_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS
VALID_TYPES = {"income", "expense"}

# 保护同一进程内的多线程读写
_STORAGE_LOCK = threading.RLock()


class StorageError(Exception):
    """数据文件读取、写入或内容损坏时抛出。"""


def _ensure_data_file():
    """数据文件不存在时初始化为空列表，不覆盖已有数据。"""
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with DATA_FILE.open("x", encoding="utf-8") as f:
                f.write("[]\n")
        except FileExistsError:
            pass
    except OSError as e:
        raise StorageError(f"初始化数据文件失败：{e}") from e


def _validate_record(record):
    """校验记录格式，不负责业务分类有效性判断。"""
    if not isinstance(record, dict):
        raise ValueError("记录必须是字典")

    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        raise ValueError("缺少必要字段：" + ", ".join(sorted(missing)))

    unknown = record.keys() - RECORD_FIELDS - {"id"}
    if unknown:
        raise ValueError("不支持的字段：" + ", ".join(sorted(unknown)))

    if record["type"] not in VALID_TYPES:
        raise ValueError("type 只能是 income 或 expense")

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

    amount = record["amount"]
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueError("amount 必须是数值")
    if not math.isfinite(amount):
        raise ValueError("amount 必须是有限数值")
    if amount <= 0:
        raise ValueError("amount 必须大于 0")
    value = Decimal(str(amount))
    if value != value.quantize(Decimal("0.01")):
        raise ValueError("amount 最多保留两位小数")

    category = record["category"]
    if not isinstance(category, str) or not category.strip():
        raise ValueError("category 必须是非空字符串")

    if not isinstance(record.get("note", DEFAULT_NOTE), str):
        raise ValueError("note 必须是字符串")

    account = record.get("account", DEFAULT_ACCOUNT)
    if not isinstance(account, str) or not account.strip():
        raise ValueError("account 必须是非空字符串")

    if "id" in record:
        record_id = record["id"]
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("id 必须是非空字符串")


def _read_records():
    """从 JSON 读取记录并检查文件结构。调用前需持有锁。"""
    _ensure_data_file()
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            records = json.load(f)
    except json.JSONDecodeError as e:
        raise StorageError(f"JSON 文件格式损坏：{e}") from e
    except (OSError, UnicodeError) as e:
        raise StorageError(f"读取数据失败：{e}") from e

    if not isinstance(records, list):
        raise StorageError("数据格式错误：JSON 顶层必须是列表")

    ids = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise StorageError(f"第 {index} 条记录不是对象")
        try:
            _validate_record(record)
        except (ValueError, TypeError) as e:
            raise StorageError(f"第 {index} 条记录无效：{e}") from e

        if "id" not in record:
            raise StorageError(f"第 {index} 条记录缺少 id")

        record_id = record["id"]
        if record_id in ids:
            raise StorageError(f"发现重复记录 ID：{record_id}")
        ids.add(record_id)

    return records


def _save_records(records):
    """先写临时文件，再原子替换正式文件。调用前需持有锁。"""
    temp_path = None
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
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
                records, f,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, DATA_FILE)
    except (OSError, TypeError, ValueError) as e:
        raise StorageError(f"保存数据失败：{e}") from e
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def load_records():
    """返回全部记录的独立副本。"""
    with _STORAGE_LOCK:
        return [record.copy() for record in _read_records()]


def get_record(record_id):
    """按 ID 查找记录，不存在时返回 None。"""
    with _STORAGE_LOCK:
        for record in _read_records():
            if record["id"] == record_id:
                return record.copy()
        return None


def add_record(record):
    """新增记录，生成 UUID 并返回保存后的完整记录。"""
    if not isinstance(record, dict):
        raise ValueError("record 必须是字典")

    new_record = record.copy()
    new_record.pop("id", None)
    new_record.setdefault("note", DEFAULT_NOTE)
    new_record.setdefault("account", DEFAULT_ACCOUNT)
    _validate_record(new_record)

    with _STORAGE_LOCK:
        records = _read_records()
        existing_ids = {item["id"] for item in records}

        record_id = uuid.uuid4().hex
        while record_id in existing_ids:
            record_id = uuid.uuid4().hex

        new_record["id"] = record_id
        records.append(new_record)
        _save_records(records)
        return new_record.copy()


def update_record(record_id, updates):
    """部分更新记录；不存在返回 None，不允许修改 ID。"""
    if not isinstance(updates, dict):
        raise ValueError("updates 必须是字典")
    if "id" in updates:
        raise ValueError("不允许修改记录 ID")

    unknown = updates.keys() - RECORD_FIELDS
    if unknown:
        raise ValueError(
            "不支持修改的字段：" + ", ".join(sorted(unknown))
        )

    with _STORAGE_LOCK:
        records = _read_records()
        for index, record in enumerate(records):
            if record["id"] != record_id:
                continue

            updated_record = record.copy()
            updated_record.update(updates)
            _validate_record(updated_record)

            records[index] = updated_record
            _save_records(records)
            return updated_record.copy()
        return None


def delete_record(record_id):
    """根据 ID 删除记录；成功返回 True，不存在返回 False。"""
    with _STORAGE_LOCK:
        records = _read_records()
        for index, record in enumerate(records):
            if record["id"] == record_id:
                records.pop(index)
                _save_records(records)
                return True
        return False
