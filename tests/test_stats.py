# -*- coding: utf-8 -*-
"""
tests/test_stats.py —— 统计模块单元测试（成员J 独立负责）
被测模块：stats.py（成员E），2026-11-07 重构后契约：
  summarize()  -> {income, expense, balance, count}
  get_stats()  -> {summary, category_rows, chart_data, chart_category_type,
                   categories, total, filters}（filters 键为 type，非 rtype）
  月度聚合已移除，趋势图由前端 charts.js 自算
运行方式：在仓库根目录执行  python tests/test_stats.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stats  # noqa: E402


def rec(rid, rtype, date, amount, category, note=""):
    return {"id": rid, "type": rtype, "date": date,
            "amount": amount, "category": category, "note": note}


DEMO = [
    rec("1", "expense", "2026-11-05", 28.5,  "饮食", "午餐"),
    rec("2", "expense", "2026-11-06", 6.0,   "交通", "地铁"),
    rec("3", "income",  "2026-11-05", 6500.0, "工资", "工资"),
    rec("4", "expense", "2026-10-18", 1800.0, "居住", "房租"),
    rec("5", "income",  "2026-10-20", 400.0, "兼职", "家教"),
]


class TestSummarize(unittest.TestCase):
    def test_empty_records_all_zero(self):
        """E-01 空数据：全 0 且不崩溃"""
        s = stats.summarize([])
        self.assertEqual(s["income"], 0.0)
        self.assertEqual(s["expense"], 0.0)
        self.assertEqual(s["balance"], 0.0)
        self.assertEqual(s["count"], 0)

    def test_totals_and_balance(self):
        s = stats.summarize(DEMO)
        self.assertAlmostEqual(s["income"], 6900.0)
        self.assertAlmostEqual(s["expense"], 1834.5)
        self.assertAlmostEqual(s["balance"], 5065.5)
        self.assertEqual(s["count"], 5)

    def test_float_precision(self):
        """E-06 浮点精度：0.1 + 0.2 必须严格等于 0.3（Decimal 处理）"""
        s = stats.summarize([
            rec("1", "expense", "2026-11-01", 0.1, "饮食"),
            rec("2", "expense", "2026-11-01", 0.2, "饮食"),
        ])
        self.assertEqual(s["expense"], 0.3)  # 严格相等，不允许 0.30000000000000004

    def test_dirty_amount_treated_as_zero(self):
        """脏数据（amount 缺失/乱码）按 0 计，不崩"""
        s = stats.summarize([
            {"id": "1", "type": "expense", "date": "2026-11-01", "category": "饮食"},
            {"id": "2", "type": "expense", "date": "2026-11-01", "amount": "abc", "category": "饮食"},
        ])
        self.assertEqual(s["expense"], 0.0)
        self.assertEqual(s["count"], 2)

    def test_unknown_type_counts_as_expense(self):
        """观察项：type 非法的记录会被计入支出（模块选择不崩溃）——行为需全组知晓"""
        s = stats.summarize([rec("1", "TRANSFER", "2026-11-01", 100, "其他")])
        self.assertEqual(s["expense"], 100.0)


class TestFilter(unittest.TestCase):
    def test_date_range_inclusive_both_ends(self):
        """E-02 起止日期都含（开头=结尾也算当天）"""
        out = stats.filter_records(DEMO, date_from="2026-11-05", date_to="2026-11-05")
        self.assertEqual(len(out), 2)  # id=1, id=3

    def test_date_from_after_date_to_returns_empty(self):
        """E-03 起始晚于结束：返回空，不报错"""
        out = stats.filter_records(DEMO, date_from="2026-12-01", date_to="2026-11-01")
        self.assertEqual(out, [])

    def test_category_exact_match(self):
        out = stats.filter_records(DEMO, category="饮食")
        self.assertEqual([r["id"] for r in out], ["1"])

    def test_category_partial_should_not_match(self):
        """类别是精确匹配，不是模糊搜索"""
        out = stats.filter_records(DEMO, category="饮")
        self.assertEqual(out, [])

    def test_amount_boundary_inclusive(self):
        """E-05 金额边界值：min/max 都是含（>= 和 <=）"""
        out = stats.filter_records(DEMO, amount_min=28.5)
        self.assertIn("1", [r["id"] for r in out])
        out = stats.filter_records(DEMO, amount_max=1800.0)
        self.assertIn("4", [r["id"] for r in out])

    def test_combined_conditions(self):
        out = stats.filter_records(DEMO, date_from="2026-11-01", rtype="expense")
        self.assertEqual([r["id"] for r in out], ["1", "2"])

    def test_empty_conditions_return_all(self):
        self.assertEqual(len(stats.filter_records(DEMO)), 5)

    def test_does_not_mutate_input(self):
        """过滤不得修改原列表"""
        snapshot = [dict(r) for r in DEMO]
        stats.filter_records(DEMO, category="饮食")
        self.assertEqual(DEMO, snapshot)


class TestAggregate(unittest.TestCase):
    def test_by_category_sum_equals_total(self):
        """E-04 各类别小计之和 = 总支出"""
        cats = stats.aggregate_by_category(DEMO, "expense")
        self.assertAlmostEqual(sum(c["amount"] for c in cats), 1834.5)
        self.assertEqual(sum(c["count"] for c in cats), 3)

    def test_by_category_sorted_desc(self):
        cats = stats.aggregate_by_category(DEMO, "expense")
        amounts = [c["amount"] for c in cats]
        self.assertEqual(amounts, sorted(amounts, reverse=True))

    def test_missing_category_goes_to_other(self):
        """category 为空的记录归入「其他」，不丢数据"""
        cats = stats.aggregate_by_category(
            [rec("1", "expense", "2026-11-01", 10, "")], "expense")
        self.assertEqual(cats[0]["category"], "其他")
        self.assertEqual(cats[0]["amount"], 10.0)

    def test_month_aggregation_moved_to_frontend(self):
        """E 重构后月度聚合由前端 charts.js 自算，后端不再保留 aggregate_by_month"""
        self.assertFalse(hasattr(stats, "aggregate_by_month"),
                         "月度聚合已迁到前端，后端不应再保留该接口")


class TestGetStats(unittest.TestCase):
    def test_main_entry_structure(self):
        r = stats.get_stats(records=DEMO)
        for key in ("summary", "category_rows", "chart_data",
                    "chart_category_type", "categories", "total", "filters"):
            self.assertIn(key, r)
        self.assertEqual(r["total"], 5)
        self.assertEqual(r["chart_category_type"], "expense")

    def test_filtered_count_and_summary(self):
        r = stats.get_stats(rtype="expense", records=DEMO)
        self.assertEqual(r["total"], 3)
        self.assertAlmostEqual(r["summary"]["expense"], 34.5)

    def test_filters_echoed_with_type_key(self):
        """filters 回显：键名为 type（重构后不再是 rtype）"""
        r = stats.get_stats(date_from="2026-11-01", rtype="income", records=DEMO)
        self.assertEqual(r["filters"]["date_from"], "2026-11-01")
        self.assertEqual(r["filters"]["type"], "income")

    @unittest.expectedFailure
    def test_all_records_missing_fields(self):
        """回归用例（issue #18）：records 混入 None 应跳过不崩。
        演示前 #3 已修复，重构时丢失；E 修复后移除 @unittest.expectedFailure。"""
        r = stats.get_stats(records=[{"id": "x"}, {}, None])
        self.assertEqual(r["total"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
