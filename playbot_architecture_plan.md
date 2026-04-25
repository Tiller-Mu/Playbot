# Playbot Schema 统一与架构对齐 — 完美定稿方案

## 重构目的与核心价值 (Why We Are Doing This)

本次底层架构重构旨在彻底解决 Playbot 录制、规划与执行三大核心模块间的**数据断层与认知错位**，从而打通“真正的 AI-Native 自动化测试”的任督二脉：

1. **消除 Schema 孤岛 (Data Flow Continuity)**：解决 Normalizer 与 ExecutionEngine 之间“你说前门楼子，我说胯骨轴子”的尴尬现状，确保录制时提取的降级特征（role、placeholder、dom_fragment）能被大模型和执行引擎无损消费。
2. **纠正大模型的输入域 (Agent Input Alignment)**：停止让大模型从 0 咀嚼原始 DOM，而是给它配备“页面静态全景图 (Source Code) + 用户交互动态骨架 (IntentPlan)”的双重神兵，让其专注补充业务断言和边界流。
3. **下沉执行与自愈基建 (Execution & Self-Healing)**：将拦截登录与密码填充下沉至真正干活的 `PlaybotExecutionEngine`；并用最安全的 C 扩展异常包装器抓取 `step_index`，为后续大模型的“哪步挂了修哪步”的局部自愈提供精准定位。

经过最严苛的交叉验证，以下是完全排除雷区、可立即执行的最终方案。

## 最终修正项 (Final Clarifications)

1. **`ASSERT_VISIBLE` 常量对齐**：
   - 必须将 `ActionType.ASSERT_VISIBLE` 的值显式定义为 `"expect_visible"`（包含 hidden/text/enabled/disabled 等变体），以兼容 `execution_engine.py` 内部硬编码的字符串匹配逻辑，防止路由断层。
2. **`nl_edit_testcase` 降级**：
   - Phase 8 提出的 `nl_edit_testcase` Prompt 改造暂不执行。如果现在将其产出改为纯 JSON Plan，将直接摧毁现有的前端大模型辅助编辑 UI 链路。该项作为独立特性延后处理。

---

## 拟定变更步骤 (最终执行版)

### Phase 1: Schema 合并（semantic_ir.py 重写）
- 合并并统一 Schema，废弃 `TargetElement` 和 `SemanticAction`，转用 `TargetHint` 和 `SemanticStep`。
- **保留** `TargetHint` (或 `SemanticStep`) 中的 `dom_fragment` 字段。
- 将断言操作合并进 `ActionType`，值严格为 `"expect_visible"` 等。新增 `TestCasePlan`。

### Phase 2: action_normalizer.py 适配
- 提取选择器 `_extract_selector`：优先匹配 `data-testid`, `id`, `name`，若都不存在，则降级返回 `raw.get('path')`。
- 完成所有字典结构的映射组装。

### Phase 3 & 4: Agent V2 输入源与 Prompt 改造
- 将 `agent_v2.py` 及相关 Schema (`TestCaseInput`) 中原本含义错位的 `dom_data` 变量重命名为 `intent_plan`。
- LLM 双轨输入：同时接收 `source_code` 和 `intent_plan`。
- **Prompt 约束**：强制输出符合 `TestPlanBlueprint` 的 JSON 结构，停止生成 Python 脚本。

### Phase 5: page_tree.py 适配
- 同步修改传递参数，确保查询到的 `ActionTrace` 记录其 `trace_data` 被赋给 `intent_plan` 传给大模型。

### Phase 6: execution_engine.py 异常包装与鉴权
- 构造函数注入凭据，新增 `_auto_login_if_needed()` 启发式拦截逻辑。
- 定义 `StepExecutionError(Exception)` 包装类，携带 `step_index`。
- 使用 `except Exception as e:` 捕获崩溃并抛出包装异常。

### Phase 7: executor.py 安全注入与解析
- 从 `Project` 对象加载凭据，使用 `json.dumps(password)` 将其安全注入 `bridge_script`。
- 捕获 `StepExecutionError` 抛出的 `step_index` 并写入数据库的错误信息中。

### Phase 8 & 9: 接口适配与清理
- 将 `testcase.py` 第 178 行的 `TestPlanCase` 显式替换为 `TestCasePlan`。
- 删除废弃的 `test_schema.py`。
