# -*- coding: utf-8 -*-
"""
test_record_list.py — 记录查看模块单元测试（成员D 自测）
============================================================
运行：
    python -m unittest discover -s tests -v
    （或 python tests/test_record_list.py）

说明：
  * 只用标准库 unittest，不依赖 pytest；
  * 每个用例把 record_list.DATA_FILE 指向临时文件，不会碰到仓库里的 data/records.json；
  * 覆盖两条数据路径：storage 不可用时的兜底读写、storage 可用时的委托调用，
    两者行为一致，联调前后都能自测。
"""

import json
import os
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import record_list  # noqa: E402


def sample_records():
    """9 条样例：跨 7 个日期、含收入/支出、金额跨度大，便于验证排序与筛选。"""
    return [
        {"id": "r001", "type": "expense", "date": "2026-11-01", "amount": 200.0, "category": "购物", "note": "外套", "account": "默认账户"},
        {"id": "r002", "type": "income", "date": "2026-11-02", "amount": 50.0, "category": "红包", "note": "抢红包", "account": "默认账户"},
        {"id": "r003", "type": "expense", "date": "2026-11-03", "amount": 88.0, "category": "饮食", "note": "聚餐", "account": "默认账户"},
        {"id": "r004", "type": "income", "date": "2026-11-04", "amount": 1200.0, "category": "工资", "note": "生活费", "account": "默认账户"},
        {"id": "r005", "type": "expense", "date": "2026-11-05", "amount": 36.8, "category": "饮食", "note": "麻辣烫", "account": "默认账户"},
        {"id": "r006", "type": "expense", "date": "2026-11-06", "amount": 4.0, "category": "交通", "note": "公交", "account": "默认账户"},
        {"id": "r007", "type": "expense", "date": "2026-11-07", "amount": 25.5, "category": "饮食", "note": "午饭", "account": "默认账户"},
        {"id": "r008", "type": "income", "date": "2026-11-07", "amount": 300.0, "category": "兼职", "note": "家教", "account": "默认账户"},
        {"id": "r009", "type": "expense", "date": "2026-11-07", "amount": 15.0, "category": "交通", "note": "打车", "account": "默认账户"},
    ]


class FakeStorage(object):
    """
    模拟成员B 的 storage.py 接口（load_records / update_record / delete_record），
    用来验证"storage 可用时本模块正确委托"这条路径。
    """

    def __init__(self, path):
        self.path = path
        if not os.path.exists(path):
            self._write(sample_records())

    def _read(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, records):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def load_records(self):
        return [r.copy() for r in self._read()]

    def update_record(self, record_id, updates):
        records = self._read()
        for index, record in enumerate(records):
            if record["id"] == record_id:
                merged = record.copy()
                merged.update(updates)
                # 模拟 storage 的多位小数校验：19.999 这类值会被它拒收
                if str(merged.get("note", "")).startswith("[blocked]"):
                    raise ValueError("storage 拒绝该内容")
                if float(merged["amount"]) <= 0:
                    raise ValueError("amount 必须大于 0")
                records[index] = merged
                self._write(records)
                return merged
        return None

    def delete_record(self, record_id):
        records = self._read()
        for index, record in enumerate(records):
            if record["id"] == record_id:
                records.pop(index)
                self._write(records)
                return True
        return False


class BaseCase(unittest.TestCase):
    """每个用例独立临时数据文件，并把 storage 置空以测试兜底路径。"""

    use_storage = False

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "records.json")
        self._origin_storage = record_list.storage
        record_list.DATA_FILE = self.path
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(sample_records(), f, ensure_ascii=False)
        if self.use_storage:
            record_list.storage = FakeStorage(self.path)
        else:
            record_list.storage = None

    def tearDown(self):
        record_list.storage = self._origin_storage
        record_list.DATA_FILE = os.path.join(BASE_DIR, "data", "records.json")
        self.tmpdir.cleanup()


class TestPagination(BaseCase):
    def test_default_page(self):
        result = record_list.list_records()
        self.assertEqual(result["total"], 9)
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["size"], 10)
        self.assertEqual(len(result["records"]), 9)
        self.assertFalse(result["has_prev"])
        self.assertFalse(result["has_next"])

    def test_page_and_size(self):
        result = record_list.list_records(page=2, size=4)
        self.assertEqual(result["pages"], 3)
        self.assertEqual(len(result["records"]), 4)
        self.assertEqual(result["offset"], 4)
        self.assertTrue(result["has_prev"])
        self.assertTrue(result["has_next"])

    def test_out_of_range_page_is_clamped(self):
        """删掉当前页最后一条后页码可能越界，应夹到最后一页而不是显示空白。"""
        result = record_list.list_records(page=99, size=4)
        self.assertEqual(result["page"], 3)
        self.assertEqual(len(result["records"]), 1)

    def test_empty_result_still_one_page(self):
        result = record_list.list_records(keyword="不存在的关键字")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["pages"], 1)
        self.assertEqual(result["records"], [])

    def test_bad_paging_args(self):
        for kwargs in ({"page": 0}, {"page": "abc"}, {"size": 0}, {"size": 999}, {"size": "x"}):
            with self.assertRaises(record_list.RecordListError):
                record_list.list_records(**kwargs)

    def test_size_upper_bound_is_100(self):
        result = record_list.list_records(size=100, records=sample_records() * 20)
        self.assertEqual(result["size"], 100)
        self.assertEqual(len(result["records"]), 100)


class TestSort(BaseCase):
    def test_default_sort_is_date_desc(self):
        items = record_list.list_records()["records"]
        self.assertEqual(items[0]["id"], "r009")   # 11-07 内按 id 倒序
        self.assertEqual(items[-1]["id"], "r001")

    def test_date_asc(self):
        items = record_list.list_records(sort="date_asc")["records"]
        self.assertEqual(items[0]["id"], "r001")

    def test_amount_desc_and_asc(self):
        desc = record_list.list_records(sort="amount_desc")["records"]
        self.assertEqual(desc[0]["id"], "r004")
        self.assertEqual(desc[-1]["id"], "r006")
        asc = record_list.list_records(sort="amount_asc")["records"]
        self.assertEqual(asc[0]["id"], "r006")

    def test_unknown_sort_rejected(self):
        with self.assertRaises(record_list.RecordListError):
            record_list.list_records(sort="weight_desc")


class TestFilter(BaseCase):
    def test_by_type(self):
        result = record_list.list_records(type="income")
        self.assertEqual(result["total"], 3)

    def test_by_category_and_date_range(self):
        result = record_list.list_records(category="饮食", start="2026-11-03", end="2026-11-05")
        self.assertEqual([r["id"] for r in result["records"]], ["r005", "r003"])

    def test_by_keyword_hits_note_and_category(self):
        self.assertEqual(record_list.list_records(keyword="打车")["total"], 1)
        self.assertEqual(record_list.list_records(keyword="交通")["total"], 2)

    def test_by_amount_range(self):
        result = record_list.list_records(min_amount="20", max_amount="100")
        self.assertEqual(result["total"], 4)   # 25.5 / 36.8 / 50 / 88

    def test_reversed_date_range_rejected(self):
        with self.assertRaises(record_list.RecordListError):
            record_list.list_records(start="2026-11-07", end="2026-11-01")

    def test_non_numeric_amount_rejected(self):
        with self.assertRaises(record_list.RecordListError):
            record_list.list_records(min_amount="abc")

    def test_filters_echoed_back(self):
        result = record_list.list_records(type="expense", category="饮食")
        self.assertEqual(result["filters"], {"type": "expense", "category": "饮食"})


class TestDetail(BaseCase):
    def test_neighbors(self):
        payload = record_list.record_detail("r005")
        self.assertEqual(payload["record"]["note"], "麻辣烫")
        # 默认日期倒序：r009,r008,r007,r006,r005,r004… → r005 的上一笔是 r006，下一笔是 r004
        self.assertEqual(payload["neighbors"]["prev"]["id"], "r006")
        self.assertEqual(payload["neighbors"]["next"]["id"], "r004")
        self.assertEqual(payload["neighbors"]["total"], 9)

    def test_first_and_last(self):
        first = record_list.record_detail("r009")["neighbors"]
        self.assertIsNone(first["prev"])
        self.assertEqual(first["index"], 1)
        last = record_list.record_detail("r001")["neighbors"]
        self.assertIsNone(last["next"])

    def test_neighbors_follow_sort(self):
        """改排序后"上一笔"应随之变化，否则详情页翻阅顺序会和列表不一致。"""
        payload = record_list.record_detail("r005", sort="date_asc")
        self.assertEqual(payload["neighbors"]["prev"]["id"], "r004")

    def test_missing_record(self):
        with self.assertRaises(record_list.RecordListError):
            record_list.record_detail("nope")


class TestUpdate(BaseCase):
    def test_partial_update_keeps_other_fields(self):
        result = record_list.update_record("r003", {"note": "改过的备注"})
        self.assertEqual(result["record"]["note"], "改过的备注")
        self.assertEqual(result["record"]["amount"], 88.0)      # 未提交的字段保持原值
        self.assertEqual(result["changed"], ["note"])
        self.assertEqual(record_list.record_detail("r003")["record"]["note"], "改过的备注")

    def test_amount_rounded_to_cent(self):
        record = record_list.update_record("r005", {"amount": "19.999"})["record"]
        self.assertEqual(record["amount"], 20.0)

    def test_invalid_amount_keeps_data(self):
        for bad in ("0", "-3", "abc", "", "nan"):
            with self.assertRaises(record_list.RecordListError):
                record_list.update_record("r005", {"amount": bad})
        self.assertEqual(record_list.record_detail("r005")["record"]["amount"], 36.8)

    def test_bad_date_rejected(self):
        with self.assertRaises(record_list.RecordListError):
            record_list.update_record("r005", {"date": "2026/11/5"})

    def test_bad_type_rejected(self):
        with self.assertRaises(record_list.RecordListError):
            record_list.update_record("r005", {"type": "收入"})

    def test_unknown_or_empty_field_rejected(self):
        with self.assertRaises(record_list.RecordListError):
            record_list.update_record("r005", {"mood": "开心"})
        with self.assertRaises(record_list.RecordListError):
            record_list.update_record("r005", {})
        with self.assertRaises(record_list.RecordListError):
            record_list.update_record("r005", {"id": "r777"})

    def test_missing_record(self):
        with self.assertRaises(record_list.RecordListError):
            record_list.update_record("nope", {"note": "x"})


class TestDelete(BaseCase):
    def test_delete(self):
        result = record_list.delete_record("r002")
        self.assertEqual(result["id"], "r002")
        self.assertEqual(result["total"], 8)
        with self.assertRaises(record_list.RecordListError):
            record_list.record_detail("r002")

    def test_delete_missing(self):
        with self.assertRaises(record_list.RecordListError):
            record_list.delete_record("nope")

    def test_delete_then_list_total_drops(self):
        record_list.delete_record("r009")
        self.assertEqual(record_list.list_records()["total"], 8)


class TestWithStorage(BaseCase):
    """storage 可用时，编辑/删除必须委托给它（而不是自己写文件）。"""

    use_storage = True

    def test_update_delegates_and_persists(self):
        result = record_list.update_record("r003", {"note": "走 storage 的备注"})
        self.assertEqual(result["record"]["note"], "走 storage 的备注")
        self.assertEqual(record_list.record_detail("r003")["record"]["note"], "走 storage 的备注")

    def test_storage_error_becomes_business_error(self):
        """storage 抛 ValueError 时应转成 RecordListError，页面拿到提示而不是 500。"""
        with self.assertRaises(record_list.RecordListError):
            record_list.update_record("r005", {"note": "[blocked] 触发存储层校验"})

    def test_delete_delegates(self):
        result = record_list.delete_record("r006")
        self.assertEqual(result["total"], 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
