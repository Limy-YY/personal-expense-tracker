# -*- coding: utf-8 -*-
"""
tests/test_record_add.py —— 记账录入链路集成测试（成员J 独立负责）
被测对象：views.py 的页面路由层（29dcdd7 起 /add 由 views.py 接管，
record_add.py 旧模块不再注册，其用例随之废弃）
运行方式：仓库根目录执行  python tests/test_record_add.py
说明：走真实 app 的 Flask test client；storage.DATA_FILE 重定向到临时目录
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import storage  # noqa: E402
import unittest  # noqa: E402,F401  (保持显式引用)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from app import app as real_app  # noqa: E402  （真实入口：含 views.init_app 全部路由）


class RecordAddTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="record_add_test_")
        self._orig = storage.DATA_FILE
        storage.DATA_FILE = Path(self.tmp) / "records.json"

        real_app.config["TESTING"] = True
        self.client = real_app.test_client()

    def tearDown(self):
        storage.DATA_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def post(self, **overrides):
        data = {"type": "expense", "date": "2026-11-07", "amount": "25.5",
                "category": "饮食", "account": "微信", "note": "午餐"}
        data.update(overrides)
        return self.client.post("/add", data=data, follow_redirects=True)

    def records(self):
        return storage.load_records()


class TestRecordAdd(RecordAddTestBase):
    def test_list_page_ok(self):
        """明细页（新账簿式界面）正常渲染"""
        resp = self.client.get("/list")
        self.assertEqual(resp.status_code, 200)

    def test_c01_valid_post_actually_saves(self):
        """C-01 正常新增：必须真的写入存储（不能假成功）"""
        resp = self.post()
        self.assertEqual(resp.status_code, 200)
        records = self.records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["category"], "饮食")
        self.assertEqual(records[0]["type"], "expense")
        self.assertTrue(records[0].get("id"))

    def test_c02_amount_zero_negative_nonnum(self):
        """C-02 金额 0 / 负数 / 非数字：全部拒绝"""
        for bad in ["0", "-5", "abc"]:
            self.post(amount=bad)
            self.assertEqual(self.records(), [], msg=f"amount={bad}")

    def test_c02_nan_rejected_friendly(self):
        """C-07 bug 防回归：float('nan') 不得绕过校验（nan<=0 为 False）"""
        self.post(amount="nan")
        self.assertEqual(self.records(), [])

    def test_c03_huge_amount_no_upper_limit(self):
        """C-03 超大金额：未设上限，按实现接受"""
        self.post(amount="9999999999")
        self.assertEqual(len(self.records()), 1)

    def test_c04_empty_date_rejected(self):
        """C-04 日期为空：拒绝"""
        self.post(date="")
        self.assertEqual(self.records(), [])

    def test_c04_invalid_calendar_date_rejected(self):
        """C-04 日历上不存在的日期：B 的 storage 层拦截，页面给保存失败提示"""
        self.post(date="2026-02-30")
        self.assertEqual(self.records(), [])

    def test_c04_non_padded_date_rejected(self):
        """观察项：非补零日期 '2026-11-7' 由 B 的严格校验拒绝"""
        self.post(date="2026-11-7")
        self.assertEqual(self.records(), [])

    @unittest.expectedFailure
    def test_c05_unknown_category_rejected(self):
        """C-05 回归（issue #21）：新视图层丢失类别存在性校验，脏分类名照存入库。
        views._read_form 只查非空；A 补上校验后移除此装饰器。"""
        self.post(category="不存在的分类")
        self.assertEqual(self.records(), [])

    def test_c06_missing_type_defaults_expense(self):
        """C-06 新契约（29dcdd7）：类型缺省时默认 expense（前端表单恒提交 type，
        服务端做软兜底）——与旧契约「拒绝」不同，此处按现实现固化"""
        self.post(type="")
        self.assertEqual(self.records()[0]["type"], "expense")

    def test_missing_account_defaults(self):
        """新契约：account 缺省时落到 ACCOUNTS[0]（微信），不再是必填"""
        self.post(account="")
        self.assertEqual(self.records()[0]["account"], "微信")


if __name__ == "__main__":
    unittest.main(verbosity=2)
