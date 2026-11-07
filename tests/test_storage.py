# -*- coding: utf-8 -*-
"""
tests/test_storage.py —— 数据存储模块单元测试（成员J 独立负责）
被测模块：storage.py（成员B，feature/storage 分支）
运行方式：仓库根目录执行  python tests/test_storage.py
说明：DATA_FILE 重定向到临时目录，绝不触碰真实数据
"""
import math
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import storage  # noqa: E402


def valid_record(**overrides):
    base = {"type": "expense", "date": "2026-11-07",
            "amount": 25.5, "category": "饮食", "note": "午餐", "account": "微信"}
    base.update(overrides)
    return base


class StorageTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="storage_test_")
        self._orig = storage.DATA_FILE
        storage.DATA_FILE = Path(self.tmp) / "records.json"

    def tearDown(self):
        storage.DATA_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestBasicCrud(StorageTestBase):
    def test_b01_missing_file_returns_empty(self):
        """B-01 文件不存在时读取：返回空列表，不崩溃"""
        self.assertEqual(storage.load_records(), [])

    def test_b02_write_read_roundtrip_chinese(self):
        """B-02 写入后读取：数据一致，中文不乱码"""
        saved = storage.add_record(valid_record(note="午餐and火锅"))
        loaded = storage.load_records()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["note"], "午餐and火锅")
        self.assertAlmostEqual(loaded[0]["amount"], 25.5)

    def test_b03_id_auto_generated_unique(self):
        """B-03 id 由存储层生成（UUID），多条不重复、类型为 str"""
        r1 = storage.add_record(valid_record())
        r2 = storage.add_record(valid_record(date="2026-11-06"))
        self.assertIsInstance(r1["id"], str)
        self.assertTrue(len(r1["id"]) >= 32)
        self.assertNotEqual(r1["id"], r2["id"])

    def test_b04_add_after_delete_all(self):
        """B-04 删光后再新增：功能正常（UUID 方案无自增回退问题）"""
        r1 = storage.add_record(valid_record())
        storage.delete_record(r1["id"])
        self.assertEqual(storage.load_records(), [])
        r2 = storage.add_record(valid_record())
        self.assertEqual(len(storage.load_records()), 1)

    def test_caller_id_stripped(self):
        """外部传入的 id 会被丢弃，id 只能由存储层生成"""
        r = storage.add_record(valid_record(id="hacker-id"))
        self.assertNotEqual(r["id"], "hacker-id")


class TestValidation(StorageTestBase):
    def test_missing_required_field(self):
        for field in ["type", "date", "amount", "category"]:
            bad = valid_record()
            del bad[field]
            with self.assertRaises(ValueError, msg=f"缺少 {field} 应报错"):
                storage.add_record(bad)

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            storage.add_record(valid_record(extra="x"))

    def test_invalid_type(self):
        with self.assertRaises(ValueError):
            storage.add_record(valid_record(type="transfer"))

    def test_invalid_date_format_and_real_dates(self):
        for bad_date in ["2026/11/07", "2026-11-7", "2026-02-30", "2026-13-01", ""]:
            with self.assertRaises(ValueError, msg=f"应拒绝日期：{bad_date}"):
                storage.add_record(valid_record(date=bad_date))

    def test_amount_bool_rejected(self):
        """True 是 int 子类，必须显式拒绝"""
        with self.assertRaises(ValueError):
            storage.add_record(valid_record(amount=True))

    def test_amount_nan_inf_rejected(self):
        """NaN/Infinity 绝不能进文件（allow_nan=False 兜底 + isfinite 校验）"""
        for bad in [float("nan"), float("inf"), float("-inf")]:
            with self.assertRaises(ValueError, msg=f"应拒绝：{bad}"):
                storage.add_record(valid_record(amount=bad))

    def test_amount_non_positive(self):
        for bad in [0, 0.0, -1, -0.01]:
            with self.assertRaises(ValueError, msg=f"应拒绝金额：{bad}"):
                storage.add_record(valid_record(amount=bad))

    def test_amount_three_decimals_rejected(self):
        with self.assertRaises(ValueError):
            storage.add_record(valid_record(amount=12.345))

    def test_amount_two_decimals_ok(self):
        r = storage.add_record(valid_record(amount=12.34))
        self.assertEqual(r["amount"], 12.34)

    def test_amount_string_rejected(self):
        """数字字符串 '25' 不能被静默转成数字"""
        with self.assertRaises(ValueError):
            storage.add_record(valid_record(amount="25"))

    def test_empty_category_rejected(self):
        with self.assertRaises(ValueError):
            storage.add_record(valid_record(category="  "))

    def test_optional_fields_defaults(self):
        r = storage.add_record(
            {"type": "income", "date": "2026-11-07", "amount": 100, "category": "工资"})
        self.assertEqual(r["note"], "")
        self.assertEqual(r["account"], "默认账户")


class TestEdgeBehaviors(StorageTestBase):
    def test_get_missing_returns_none(self):
        """接口注释承诺：查不到返回 None"""
        self.assertIsNone(storage.get_record("no-such-id"))

    def test_update_missing_returns_none(self):
        self.assertIsNone(storage.update_record("no-such-id", {"note": "x"}))

    def test_delete_missing_returns_false(self):
        self.assertFalse(storage.delete_record("no-such-id"))

    def test_update_partial_and_id_immutable(self):
        r = storage.add_record(valid_record())
        with self.assertRaises(ValueError):
            storage.update_record(r["id"], {"id": "new-id"})
        with self.assertRaises(ValueError):
            storage.update_record(r["id"], {"hacker_field": 1})
        updated = storage.update_record(r["id"], {"note": "改过的备注"})
        self.assertEqual(updated["note"], "改过的备注")
        self.assertEqual(updated["category"], "饮食")  # 未更新字段保持原样

    def test_update_invalid_value_keeps_original(self):
        """更新校验失败时，原记录必须原封不动"""
        r = storage.add_record(valid_record())
        with self.assertRaises(ValueError):
            storage.update_record(r["id"], {"amount": -5})
        self.assertAlmostEqual(storage.get_record(r["id"])["amount"], 25.5)

    def test_load_returns_copies(self):
        """load 返回副本，调用方乱改不影响真实数据"""
        storage.add_record(valid_record())
        snap = storage.load_records()
        snap[0]["amount"] = 99999
        self.assertAlmostEqual(storage.load_records()[0]["amount"], 25.5)

    def test_b06_corrupted_file_raises_storageerror(self):
        """B-06 文件损坏：抛 StorageError，绝不静默返回空"""
        storage.add_record(valid_record())
        with open(storage.DATA_FILE, "w", encoding="utf-8") as f:
            f.write("{ corruption!!")
        with self.assertRaises(storage.StorageError):
            storage.load_records()
        with self.assertRaises(storage.StorageError):
            storage.add_record(valid_record())  # 损坏时也不允许写入覆盖

    def test_corrupted_element_rejected(self):
        """文件里混入非对象/重复id：明确报错（fail-fast，与F策略一致）"""
        import json
        storage.add_record(valid_record())
        records = json.loads(storage.DATA_FILE.read_text(encoding="utf-8"))
        records.append(None)
        storage.DATA_FILE.write_text(
            json.dumps(records, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(storage.StorageError):
            storage.load_records()


class TestConcurrency(StorageTestBase):
    def test_b05_concurrent_writes(self):
        """B-05 多线程并发写：无丢失、无损坏"""
        errors = []

        def worker(n):
            try:
                for i in range(n):
                    storage.add_record(valid_record(date=f"2026-10-{i+1:02d}"))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(8,)) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(errors, [])
        records = storage.load_records()
        self.assertEqual(len(records), 48)
        ids = [r["id"] for r in records]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
