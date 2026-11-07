# -*- coding: utf-8 -*-
"""
tests/test_query.py —— 筛选与搜索模块单元测试（成员J 独立负责）
被测模块：query.py（成员G，main 分支）
运行方式：仓库根目录执行  python tests/test_query.py
说明：纯函数走 apply_filters(records, ...) 注入；文件型接口重定向 DATA_FILE 到临时目录
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import query  # noqa: E402


def rec(rid, rtype="expense", date="2026-11-05", amount=25.0,
        category="饮食", note="", account="微信"):
    return {"id": rid, "type": rtype, "date": date, "amount": amount,
            "category": category, "note": note, "account": account}


DEMO = [
    rec("a1", "expense", "2026-11-05", 25.0,  "饮食", "午餐",      "微信"),
    rec("a2", "expense", "2026-11-06", 6.0,   "交通", "地铁通勤",  "现金"),
    rec("a3", "income",  "2026-11-05", 6500.0, "工资", "实习工资",  "银行卡"),
    rec("a4", "expense", "2026-10-18", 1800.0, "居住", "房租",      "银行卡"),
    rec("a5", "income",  "2026-10-20", 400.0,  "兼职", "家教费",    "现金"),
]


class TestQueryBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="query_test_")
        self._orig = query.DATA_FILE
        query.DATA_FILE = os.path.join(self.tmp, "data.json")
        with open(query.DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"records": DEMO, "categories": []}, f, ensure_ascii=False)

    def tearDown(self):
        query.DATA_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ids(self, records):
        return [r["id"] for r in records]


class TestKeyword(TestQueryBase):
    def test_g01_keyword_hits_note_category_account(self):
        self.assertEqual(self.ids(query.apply_filters(DEMO, keyword="午餐")), ["a1"])
        self.assertEqual(self.ids(query.apply_filters(DEMO, keyword="交通")), ["a2"])
        self.assertEqual(self.ids(query.apply_filters(DEMO, keyword="银行卡")), ["a3", "a4"])

    def test_g01_multi_token_is_and(self):
        """多关键词之间是『且』"""
        self.assertEqual(self.ids(query.apply_filters(DEMO, keyword="工资 实习")), ["a3"])
        self.assertEqual(query.apply_filters(DEMO, keyword="工资 午餐"), [])

    def test_keyword_case_insensitive(self):
        demo = [rec("x1", note="Milk Tea")]
        self.assertEqual(len(query.apply_filters(demo, keyword="milk")), 1)

    def test_g04_special_chars_no_crash_no_inject(self):
        """G-04 特殊字符按字面匹配，不崩溃不注入"""
        demo = [rec("x1", note="50% off_折扣"), rec("x2", note="普通")]
        self.assertEqual(self.ids(query.apply_filters(demo, keyword="%")), ["x1"])
        self.assertEqual(self.ids(query.apply_filters(demo, keyword="_")), ["x1"])
        self.assertEqual(self.ids(query.apply_filters(demo, keyword="' or 1=1--")), [])

    def test_keyword_does_not_search_amount(self):
        """金额不参与关键字检索（G 的注释明确此设计，防止搜 2 命中一片）"""
        self.assertEqual(query.apply_filters(DEMO, keyword="6500"), [])


class TestFilters(TestQueryBase):
    def test_g02_combined_conditions(self):
        """G-02 日期区间 + 类别 + 类型 组合"""
        out = query.apply_filters(DEMO, start_date="2026-11-01",
                                  end_date="2026-11-30", category="饮食", rtype="expense")
        self.assertEqual(self.ids(out), ["a1"])

    def test_g03_empty_conditions_return_all(self):
        self.assertEqual(len(query.apply_filters(DEMO)), 5)

    def test_multi_values_same_condition_is_or(self):
        out = query.apply_filters(DEMO, category="饮食,交通")
        self.assertEqual(sorted(self.ids(out)), ["a1", "a2"])
        out = query.apply_filters(DEMO, category=["饮食", "交通"])
        self.assertEqual(sorted(self.ids(out)), ["a1", "a2"])

    def test_type_chinese_aliases(self):
        self.assertEqual(len(query.apply_filters(DEMO, rtype="收入")), 2)
        self.assertEqual(len(query.apply_filters(DEMO, rtype="支出")), 3)
        self.assertEqual(len(query.apply_filters(DEMO, rtype="全部")), 5)

    def test_invalid_type_rejected(self):
        with self.assertRaises(ValueError):
            query.apply_filters(DEMO, rtype="转账")

    def test_money_formats_tolerated(self):
        """金额条件容忍 ￥ / 逗号 / 空格写法"""
        out = query.apply_filters(DEMO, min_amount="￥1,000")
        self.assertEqual(self.ids(out), ["a3", "a4"])

    def test_date_crossed_rejected(self):
        with self.assertRaises(ValueError):
            query.apply_filters(DEMO, start_date="2026-12-01", end_date="2026-11-01")

    def test_amount_crossed_rejected(self):
        with self.assertRaises(ValueError):
            query.apply_filters(DEMO, min_amount=500, max_amount=100)

    def test_boundary_dates_inclusive(self):
        out = query.apply_filters(DEMO, start_date="2026-11-05", end_date="2026-11-05")
        self.assertEqual(sorted(self.ids(out)), ["a1", "a3"])

    def test_unknown_param_rejected(self):
        """拼错字段名直接报错，不被静默忽略（G 的明确设计）"""
        with self.assertRaises(TypeError):
            query.apply_filters(DEMO, catgory="饮食")

    def test_dirty_record_missing_date_excluded_from_date_filter(self):
        """日期缺失的记录：无条件查询保留，日期过滤中被排除，不崩溃"""
        demo = [rec("ok1", date="2026-11-05"), rec("bad1", date="")]
        self.assertEqual(len(query.apply_filters(demo)), 2)
        self.assertEqual(self.ids(query.apply_filters(demo, start_date="2026-11-01")), ["ok1"])


class TestSortPaging(TestQueryBase):
    def test_sort_by_amount(self):
        out = query.apply_filters(DEMO, sort_by="amount", order="asc")
        amounts = [r["amount"] for r in out]
        self.assertEqual(amounts, sorted(amounts))
        out = query.apply_filters(DEMO, sort_by="amount", order="降序")
        amounts = [r["amount"] for r in out]
        self.assertEqual(amounts, sorted(amounts, reverse=True))

    def test_invalid_sort_field_rejected(self):
        with self.assertRaises(ValueError):
            query.apply_filters(DEMO, sort_by="note")

    def test_paging_math(self):
        page = query.query_page(page=1, page_size=2)
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(page["total"], 5)
        self.assertEqual(page["total_pages"], 3)
        self.assertFalse(page["has_prev"])
        self.assertTrue(page["has_next"])

        last = query.query_page(page=3, page_size=2)
        self.assertEqual(len(last["items"]), 1)
        self.assertTrue(last["has_prev"])
        self.assertFalse(last["has_next"])

    def test_paging_beyond_returns_empty_not_error(self):
        page = query.query_page(page=99, page_size=2)
        self.assertEqual(page["items"], [])
        self.assertEqual(page["total"], 5)  # 总数不受页码影响

    def test_paging_stable_no_skip(self):
        """同值记录靠 id 次键稳定排序，翻页不跳条/不重复"""
        demo = [rec(f"z{i}", amount=10.0, date="2026-11-01") for i in range(5)]
        with open(query.DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"records": demo, "categories": []}, f, ensure_ascii=False)
        all_ids = []
        for p in (1, 2, 3):
            pg = query.query_page(page=p, page_size=2)
            all_ids.extend(r["id"] for r in pg["items"])
        self.assertEqual(sorted(all_ids), [f"z{i}" for i in range(5)])

    def test_latest_records(self):
        out = query.latest_records(2)
        # 日期倒序取前2；同日期(11-05)按 id 次键倒序 → a3 在 a1 前
        self.assertEqual(self.ids(out), ["a2", "a3"])
        with_f = query.latest_records(1, rtype="income")
        self.assertEqual(self.ids(with_f), ["a3"])

    def test_count_records(self):
        self.assertEqual(query.count_records(rtype="expense"), 3)

    def test_input_not_mutated(self):
        snapshot = json.loads(json.dumps(DEMO))
        query.apply_filters(DEMO, keyword="午餐", sort_by="amount")
        self.assertEqual(DEMO, snapshot)


class TestFileLayer(TestQueryBase):
    def test_records_file_roundtrip(self):
        self.assertEqual(len(query.query_records()), 5)

    def test_corrupted_file_raises(self):
        with open(query.DATA_FILE, "w", encoding="utf-8") as f:
            f.write("{bad json")
        with self.assertRaises(RuntimeError):
            query.query_records()


if __name__ == "__main__":
    unittest.main(verbosity=2)
