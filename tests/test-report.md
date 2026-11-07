# 测试报告（成员J）

> 报告周期：2026-11-07 14:45 — 15:30
> 测试人：J（本报告由 J 维护，随测试进度更新）
> 测试环境：Windows 11 · Python 3.13.14 · 仓库 commit `3948ec6`（main）
> 运行方式：仓库根目录下执行 `python tests/test_category.py` / `python tests/test_stats.py`

## 一、总体结论

| 模块 | 被测人 | 用例数 | 通过 | 失败 | 结论 |
|---|---|---|---|---|---|
| category.py 分类管理 | F | 26 | 26 | 0 | ✅ 质量过硬，可放行 |
| stats.py 统计 | E | 22 | 21 | 1 | ⚠️ BUG-1 待修（issue #3） |
| storage.py 数据存储 | B | 26 | 26 | 0 | ✅ 全组质量标杆：NaN/bool/日期/原子写入/并发锁全防住了 |
| record_add.py 录入 | C | 10 | 8 | 2 | ⚠️ BUG-2/3 待修（均有兜底，不损坏数据） |
| ui（H）| H | 静态检查 | — | 1 | ⚠️ 模板契约不一致（issue #8），A 二选一裁决 |
| query.py 筛选搜索 | G | 26 | 26 | 0 | ✅ 标杆级：容错、稳定分页、防误设计全做了 |
| record_list.py 查看 | D | 34（D 自写） | 34 | 0 | ✅ J 抽查用例质量合格：边界/非法输入/排序覆盖完整 |
| 集成联调 | A | — | — | — | ❌ **缺口：main 缺 storage.py，录入页当前为"假成功"** |

## 二、发现的问题

### BUG-2（编号 C-07，issue #5）：NaN 金额绕过 C 的校验，用户看到"系统错误" —— 待 C 修复

- **严重级别**：低（数据不会损坏——B 兜底拒绝了，但报错误导用户）
- **位置**：`record_add.py` 第 41-48 行金额校验
- **根因**：`float("nan")` 是合法 float，且 `nan <= 0` 为 False，两个 if 都拦不住
- **复现**：录入页金额填 `nan` 提交 → 提示"系统错误：数据保存失败"，实际是 B 的 ValueError 被兜底 except 吃掉
- **建议修法**：金额校验改为 `if not math.isfinite(amount) or amount <= 0:`（需 `import math`），给用户"金额无效"的明确提示

### BUG-3（编号 C-05，issue #6）：类别不校验存在性，脏分类名照存 —— 待 C 修复（或 A 定策略）

- **严重级别**：中（脏数据入库后，统计页按类别聚合会出现孤立类别，饼图错乱）
- **复现**：录入页 category 填"不存在的分类"（或前端篡改表单）→ 记账成功，脏分类入库
- **建议修法**：C 在 POST 校验段调 `category.list_categories()` 取名字集合，`category not in 名字集合` 即 flash 拒绝（GET 已经调了 F 的接口，顺手的事）

### 集成缺口（A 处理，issue #7 —— 已确认：storage 于 PR #9 合入）：main 上录入页是"假成功"

`record_add.py` POST 成功路径 `from storage import add_record`，但 **main 分支还没有 storage.py**（B 的代码在 feature/storage 未合）。当前 main 上提交表单会走 `except ImportError` 分支，显示"[独立测试] 记账成功"——**用户以为记上了，数据实际没存**。B 的模块 26/26 全过、随时可合，建议 A 立即合并 `feature/storage`。

### 观察项

1. **前后端日期校验规则不一致**：C 的 strptime 接受 `2026-11-7`（非补零），B 的严格校验拒绝 → 用户看到"系统错误"而非格式提示。建议 C 改用与 B 相同的 `date.fromisoformat` + 往返比较。
2. **type 非法的记录会被 stats 计入支出**：B/C 校验后正常流程不会产生，行为需全组知晓。
3. **数据层统一进展（当前最大集成风险）**：F 已重构 category.py 为 `data/categories.json` + `data/records.json`，与 B 的存储层对齐，早期冲突解除。**但 main 上的 stats.py（E）和 query.py（G）仍读根目录 `data.json`**——同一 main 里现存两套读法，A 必须让 E/G 改到 `data/` 目录，否则统计页和搜索页永远查不到新记的账。另外 main 仍缺 storage.py（issue #7）与 app.py。
4. **stats.py 的 `records` 注入参数与 storage.py 的副本返回设计好评**，模块边界清晰。

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
