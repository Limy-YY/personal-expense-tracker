# -*- coding: utf-8 -*-
"""
tests/test_record_add.py —— 记账录入模块接口测试（成员J 独立负责）
被测模块：record_add.py（成员C，main 分支）
运行方式：仓库根目录执行  python tests/test_record_add.py
说明：通过 Flask test client 走真实 POST 流程；storage.DATA_FILE 重定向到临时目录
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import storage  # noqa: E402  （需 storage.py 存在于仓库根目录，B 合入后自动满足）
from flask import Flask  # noqa: E402
import record_add  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RecordAddTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="record_add_test_")
        self._orig = storage.DATA_FILE
        storage.DATA_FILE = Path(self.tmp) / "records.json"

        self.app = Flask(__name__, template_folder=os.path.join(REPO_ROOT, "templates"))
        self.app.secret_key = "unit-test"
        self.app.register_blueprint(record_add.record_add_bp)
        self.client = self.app.test_client()

    def tearDown(self):
        storage.DATA_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def post(self, **overrides):
        data = {"type": "expense", "date": "2026-11-07", "amount": "25.5",
                "category": "饮食", "account": "微信", "note": "午餐"}
        data.update(overrides)
        return self.client.post("/add", data=data, follow_redirects=True)


class TestRecordAdd(RecordAddTestBase):
    def test_get_page_ok(self):
        resp = self.client.get("/add")
        self.assertEqual(resp.status_code, 200)

    def test_c01_valid_post_actually_saves(self):
        """C-01 正常新增：必须真的写入存储（不能假成功）"""
        resp = self.post()
        self.assertIn("记账成功", resp.data.decode("utf-8"))
        self.assertNotIn("[独立测试]", resp.data.decode("utf-8"))  # 不允许走模拟分支
        records = storage.load_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["category"], "饮食")
        self.assertTrue(records[0].get("id"))

    def test_c02_amount_zero_negative_nonnum(self):
        """C-02 金额 0 / 负数 / 非数字：全部拒绝"""
        for bad, expect in [("0", "大于 0"), ("-5", "大于 0"), ("abc", "数字")]:
            resp = self.post(amount=bad)
            self.assertIn(expect, resp.data.decode("utf-8"), msg=f"amount={bad}")
            self.assertEqual(storage.load_records(), [])

    def test_c02_nan_bypasses_validation(self):
        """C-07 bug：float('nan') 绕过 C 的校验（nan<=0 为 False），
        最终由 B 兜底拒绝，但用户看到的是『系统错误』而非『金额无效』"""
        resp = self.post(amount="nan")
        text = resp.data.decode("utf-8")
        self.assertIn("系统错误", text)          # 当前实际行为
        self.assertEqual(storage.load_records(), [])  # 幸好没写进去

    def test_c03_huge_amount_no_upper_limit(self):
        """C-03 超大金额：C 与 B 均未设上限，按实现接受（已与约定对齐）"""
        resp = self.post(amount="9999999999")
        self.assertIn("记账成功", resp.data.decode("utf-8"))
        self.assertEqual(len(storage.load_records()), 1)

    def test_c04_empty_and_invalid_dates(self):
        """C-04 日期为空 / 日历上不存在的日期：拒绝"""
        resp = self.post(date="")
        self.assertIn("必填", resp.data.decode("utf-8"))
        resp = self.post(date="2026-02-30")
        self.assertIn("日期格式错误", resp.data.decode("utf-8"))
        self.assertEqual(storage.load_records(), [])

    def test_c04_non_padded_date_inconsistent_with_b(self):
        """观察项：C 的 strptime 接受 '2026-11-7'，B 的校验拒绝它——
        结果是用户看到『系统错误』而非明确的日期格式提示（前后端校验规则不一致）"""
        resp = self.post(date="2026-11-7")
        text = resp.data.decode("utf-8")
        self.assertIn("系统错误", text)
        self.assertEqual(storage.load_records(), [])

    def test_c05_unknown_category_saved_without_check(self):
        """C-05 bug：类别不在分类列表中也照存不误——C 未对接 F 的分类校验"""
        resp = self.post(category="不存在的分类")
        self.assertIn("记账成功", resp.data.decode("utf-8"))
        self.assertEqual(len(storage.load_records()), 1)  # 脏分类名进了库

    def test_c06_missing_type_rejected(self):
        """C-06 类型缺省：拒绝，不允许默认值混入"""
        resp = self.post(type="")
        self.assertIn("必填", resp.data.decode("utf-8"))
        self.assertEqual(storage.load_records(), [])

    def test_missing_account_rejected(self):
        """C 把 account 也列为必填（与 B 的默认值策略不同，行为以前端表单为准）"""
        resp = self.post(account="")
        self.assertIn("必填", resp.data.decode("utf-8"))
        self.assertEqual(storage.load_records(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
