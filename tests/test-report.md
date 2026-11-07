# 测试报告（成员J）

> 报告周期：2026-11-07 14:45 — 15:30
> 测试人：J（本报告由 J 维护，随测试进度更新）
> 测试环境：Windows 11 · Python 3.13.14 · 仓库 commit `3948ec6`（main）
> 运行方式：仓库根目录下执行 `python tests/test_category.py` / `python tests/test_stats.py`

## 一、总体结论

| 模块 | 被测人 | 用例数 | 通过 | 失败 | 结论 |
|---|---|---|---|---|---|
| category.py 分类管理 | F | 26 | 26 | 0 | ✅ 质量过硬，可放行 |
| stats.py 统计 | E | 22 | 21 | 1 | ⚠️ 有 1 个 bug 待修（E-07），其余可放行 |
| storage.py / record_add / record_list / query | B/C/D/G | — | — | — | ⬜ 待合入 |

## 二、发现的问题

### BUG-1（编号 E-07）：filter_records 遇脏元素崩溃 —— 待 E 修复

- **严重级别**：中（触发条件为数据文件被手动编辑或上游写入异常，但一旦触发整个统计页白屏）
- **位置**：`stats.py` 第 99 行，`filter_records` 函数的 for 循环内
- **违反契约**：模块注释明确承诺"脏数据不让统计崩"（见 `_to_decimal` 的 docstring），金额脏数据防了，记录级脏数据没防
- **根因**：`for rec in records:` 循环内直接调用 `rec.get(...)`，未校验 `rec` 是否为 dict

**复现命令**（任何人可在仓库根目录执行验证）：

```bash
python -c "import stats; stats.filter_records([None], date_from='2026-11-01')"
```

当前实际输出：

```
AttributeError: 'NoneType' object has no attribute 'get'
```

**建议修法**（一行，第 97 行 for 循环下加）：

```python
for rec in records:
    if not isinstance(rec, dict):   # 脏元素跳过，与"不让统计崩"契约对齐
        continue
```

**回归验证**：修复后由 J 执行 `python tests/test_stats.py`，用例 `test_all_records_missing_fields` 通过即关闭此 bug。

### 观察项（非 bug，建议全组知晓）

1. **type 非法的记录会被计入支出**：`summarize` 中 `else` 分支兜底。由于 B 的录入模块会校验 type，正常流程不会产生此类记录，行为可接受，但需全组知晓。
2. **两个模块对"数据文件损坏"的处理策略不一致**：category.py 抛 `RuntimeError` 拒绝服务（防好数据被覆盖），stats.py 静默回退空数据（统计页显示全 0）。用户看到"全 0"可能误以为真的没花钱。建议 A 在联调时统一策略——本测试不判定对错，只提请决策。
3. **stats.py 的 `records` 参数设计好评**：支持注入测试数据，不依赖真实文件，这让单元测试完全无副作用，值得其他模块效仿。

## 三、已验证的亮点行为（F 模块）

- 改名分类后，历史账单中的旧分类名**确实被联动替换**（records 同步）
- 删除被账单引用的分类**确实被拒绝**，且提示引用条数
- 预算校验覆盖 NaN / inf / 负数 / 数字字符串，无静默转换
- `data.json` 损坏（非法 JSON / 顶层非对象 / 字段类型错误）均按承诺抛 `RuntimeError`

## 四、下一步计划

| 时间 | 动作 |
|---|---|
| 随时 | B/C/D/G 模块合入即测（用例清单见 test-cases.md） |
| E 修复后 | 复验 BUG-1，关闭 E-07 |
| 16:25 前 | 全量回归：重跑全部用例 + 集成用例 I-01~05 |
| 16:45 前 | 向全组报测试结论（全绿 / 剩余 ❌ 清单），作为 release 把关 |
