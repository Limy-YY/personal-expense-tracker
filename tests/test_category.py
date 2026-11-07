# -*- coding: utf-8 -*-
"""
tests/test_category.py —— 分类管理模块单元测试（成员J 独立负责）
被测模块：category.py（成员F）
运行方式：在仓库根目录执行  python tests/test_category.py  或  python -m unittest discover tests
说明：全部用例使用临时目录，绝不触碰真实 data.json
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import category  # noqa: E402


class CategoryTestBase(unittest.TestCase):
    """公共夹具：每个用例独立临时目录 + 独立 data.json"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ledger_test_")
        self._orig_cats = category.CATEGORIES_FILE
        self._orig_recs = category.RECORDS_FILE
        category.CATEGORIES_FILE = os.path.join(self.tmp, "categories.json")
        category.RECORDS_FILE = os.path.join(self.tmp, "records.json")
        try:
            import storage
            from pathlib import Path
            self._orig_storage_file = storage.DATA_FILE
            storage.DATA_FILE = Path(self.tmp) / "records.json"   # F 联动经 storage，必须同步隔离
            self._patched_storage = True
        except ImportError:
            self._patched_storage = False

    def tearDown(self):
        category.CATEGORIES_FILE = self._orig_cats
        category.RECORDS_FILE = self._orig_recs
        if getattr(self, "_patched_storage", False):
            import storage
            storage.DATA_FILE = self._orig_storage_file
        shutil.rmtree(self.tmp, ignore_errors=True)

    # 便捷方法：造一个已有默认分类的数据文件
    def seed_defaults(self):
        category.init_categories()

    # 便捷方法：塞一条引用某分类的账单记录
    def seed_record(self, cat_name, rid=1):
        import storage
        recs = storage.load_records()
        recs.append({"id": str(rid), "type": "expense",
                     "amount": 25.0, "category": cat_name,
                     "date": "2026-11-07", "note": "测试数据"})
        storage._save_records(recs)   # 夹具直写，绕过 add_record 校验


class TestDefaultInit(CategoryTestBase):
    def test_first_init_creates_defaults(self):
        category.init_categories()
        cats = category.list_categories()
        self.assertEqual(len(cats), len(category.DEFAULT_CATEGORIES))

    def test_init_is_idempotent(self):
        """重复调用不产生重复分类"""
        category.init_categories()
        category.init_categories()
        names = [c["name"] for c in category.list_categories()]
        self.assertEqual(len(names), len(set(names)))

    def test_missing_file_returns_empty(self):
        """data.json 不存在时应返回空结构而不是崩溃"""
        data = {"records": category._load_records(),
                "categories": category._load_categories()}
        self.assertEqual(data, {"records": [], "categories": []})


class TestAddCategory(CategoryTestBase):
    def test_add_expense_with_budget_and_icon(self):
        cat = category.add_category("宠物", "expense", "#8d6e63", budget=300, icon="🐱")
        self.assertEqual(cat["budget"], 300)
        self.assertEqual(cat["icon"], "🐱")

    def test_duplicate_name_rejected(self):
        self.seed_defaults()
        with self.assertRaises(ValueError):
            category.add_category("饮食", "expense", "#123456")

    def test_invalid_color_rejected(self):
        with self.assertRaises(ValueError):
            category.add_category("测试", "expense", "red")      # 非 #RRGGBB
        with self.assertRaises(ValueError):
            category.add_category("测试", "expense", "#12345")   # 5 位

    def test_bad_type_rejected(self):
        with self.assertRaises(ValueError):
            category.add_category("测试", "food", "#123456")

    def test_name_with_route_char_rejected(self):
        for bad in ["饮/食", "饮?食", "饮#食", "饮&食"]:
            with self.assertRaises(ValueError, msg=f"应拒绝：{bad}"):
                category.add_category(bad, "expense", "#123456")

    def test_income_budget_rejected(self):
        with self.assertRaises(ValueError):
            category.add_category("稿费", "income", "#7e57c2", budget=100)

    def test_budget_not_finite_rejected(self):
        with self.assertRaises(ValueError):
            category.add_category("测试", "expense", "#123456", budget=float("nan"))
        with self.assertRaises(ValueError):
            category.add_category("测试", "expense", "#123456", budget=float("inf"))
        with self.assertRaises(ValueError):
            category.add_category("测试", "expense", "#123456", budget=-1)

    def test_budget_string_rejected(self):
        """数字字符串 '100' 不应被当成预算 100"""
        with self.assertRaises(ValueError):
            category.add_category("测试", "expense", "#123456", budget="100")

    def test_blank_name_rejected(self):
        with self.assertRaises(ValueError):
            category.add_category("   ", "expense", "#123456")


class TestUpdateCategory(CategoryTestBase):
    def test_rename_syncs_records(self):
        """改名后，历史账单里的旧分类名必须被联动替换（F 注释承诺的行为）"""
        self.seed_defaults()
        self.seed_record("饮食", rid=1)
        self.seed_record("饮食", rid=2)
        category.update_category("饮食", new_name="吃喝")
        data = {"records": category._load_records(),
                "categories": category._load_categories()}
        used = [r["category"] for r in data["records"]]
        self.assertEqual(used, ["吃喝", "吃喝"])

    def test_rename_to_existing_rejected(self):
        self.seed_defaults()
        with self.assertRaises(ValueError):
            category.update_category("饮食", new_name="交通")

    def test_rename_to_blank_rejected(self):
        self.seed_defaults()
        with self.assertRaises(ValueError):
            category.update_category("饮食", new_name="")

    def test_update_budget_on_expense_ok(self):
        self.seed_defaults()
        cat = category.update_category("饮食", budget=999.5)
        self.assertEqual(cat["budget"], 999.5)

    def test_update_budget_on_income_rejected(self):
        self.seed_defaults()
        with self.assertRaises(ValueError):
            category.update_category("工资", budget=100)

    def test_nonexistent_target_rejected(self):
        self.seed_defaults()
        with self.assertRaises(ValueError):
            category.update_category("不存在的分类", new_name="x")


class TestDeleteCategory(CategoryTestBase):
    def test_delete_unused_ok(self):
        self.seed_defaults()
        category.delete_category("医疗")
        names = [c["name"] for c in category.list_categories()]
        self.assertNotIn("医疗", names)

    def test_delete_referenced_migrates_to_fallback(self):
        """F 方案②契约（29dcdd7 起）：兜底分类改为「其他」（支出）/「其他收入」（收入），
        删除被引用分类时历史记录自动迁移到同类型兜底"""
        self.seed_defaults()
        self.seed_record("饮食", rid=1)
        category.delete_category("饮食")
        used = [r["category"] for r in category._load_records()]
        self.assertEqual(used, ["其他"])
        names = [c["name"] for c in category.list_categories()]
        self.assertNotIn("饮食", names)

    def test_delete_nonexistent_rejected(self):
        self.seed_defaults()
        with self.assertRaises(ValueError):
            category.delete_category("不存在的分类")


class TestDataIntegrity(CategoryTestBase):
    """data.json 损坏时的行为——F 注释承诺抛 RuntimeError，承诺了就必须验"""

    def _write_raw(self, content, target="categories"):
        path = category.CATEGORIES_FILE if target == "categories" else category.RECORDS_FILE
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_corrupted_json_raises(self):
        """categories.json 非法 JSON -> RuntimeError，不静默清空"""
        self._write_raw("{这不是合法JSON")
        with self.assertRaises(RuntimeError):
            category._load_categories()

    def test_top_level_not_list_raises(self):
        """categories.json 顶层不是数组 -> RuntimeError"""
        self._write_raw('{"a": 1}')
        with self.assertRaises(RuntimeError):
            category._load_categories()

    def test_records_not_list_raises(self):
        """records.json 顶层不是数组 -> StorageError（B 的 storage 契约）"""
        import storage
        self._write_raw(json.dumps({"records": "oops"}, ensure_ascii=False), target="records")
        with self.assertRaises(storage.StorageError):
            category._load_records()

    def test_record_element_not_dict_raises(self):
        """records.json 元素不是对象 -> StorageError"""
        import storage
        self._write_raw(json.dumps([None], ensure_ascii=False), target="records")
        with self.assertRaises(storage.StorageError):
            category._load_records()

    def test_categories_not_list_raises(self):
        """categories.json 内容是 null/字典 -> RuntimeError"""
        self._write_raw(json.dumps(None, ensure_ascii=False))
        with self.assertRaises(RuntimeError):
            category._load_categories()

    def test_save_then_load_roundtrip(self):
        """写入后读回应保持中文原样（ensure_ascii=False）"""
        category.add_category("宠物", "expense", "#8d6e63", budget=300)
        with open(category.CATEGORIES_FILE, encoding="utf-8") as f:
            raw = f.read()
        self.assertIn("宠物", raw)  # 不应被转义成 \uXXXX


if __name__ == "__main__":
    unittest.main(verbosity=2)
