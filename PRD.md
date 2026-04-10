# TestPilot - 自然语言驱动的 Web 测试平台 产品需求文档 (PRD)

> 版本：v1.0  
> 日期：2026-04-10  
> 状态：初稿  

---

## 目录

1. [产品概述](#1-产品概述)
2. [目标用户与使用场景](#2-目标用户与使用场景)
3. [核心功能需求](#3-核心功能需求)
4. [用户流程图](#4-用户流程图)
5. [非功能性需求](#5-非功能性需求)
6. [数据模型说明](#6-数据模型说明)
7. [API 接口清单](#7-api-接口清单)
8. [未来规划](#8-未来规划)

---

## 1. 产品概述

### 1.1 背景

在当前的软件开发流程中，Web 端的端到端（E2E）测试往往是质量保障的关键环节，但同时也是技术门槛最高的部分之一。传统的 E2E 测试要求测试人员具备编程能力，能够使用 Selenium、Playwright 等框架手动编写测试脚本。这导致了以下问题：

- **人才瓶颈**：大量具备丰富测试经验和业务知识的 QA 人员因为缺乏编程技能而无法直接编写自动化测试
- **效率低下**：即使有自动化测试经验的工程师，编写和维护 E2E 测试脚本也非常耗时
- **知识断层**：懂业务的测试人员和懂代码的开发人员之间存在沟通成本，测试用例的业务意图常在代码化过程中失真
- **维护成本高**：随着项目迭代，测试脚本的维护成本呈线性增长，常常出现"写了不跑、跑了不过"的窘境

随着大语言模型（LLM）技术的成熟，我们有机会通过 AI 能力来弥合"测试知识"与"编程技能"之间的鸿沟。

### 1.2 产品目标

**TestPilot** 是一个自然语言驱动的 Web 端自动化测试平台，其核心目标是：

1. **降低自动化测试门槛**：让不会写代码但懂测试概念的人员能够创建、修改和管理 E2E 测试用例
2. **提高测试效率**：通过分析被测项目源码自动生成测试用例，大幅减少从零编写测试的工作量
3. **保持专业性**：底层输出标准的 Python Playwright 测试脚本，可被专业测试工程师审查、二次编辑，也可纳入 CI/CD 流程
4. **闭环管理**：提供从用例生成 → 人工审查 → 执行 → 报告的完整测试管理闭环

### 1.3 产品定位

TestPilot 定位为 **"AI 辅助测试的中间层工具"**，它不是取代专业测试框架，而是在用户（非编码 QA）和底层测试框架（Playwright）之间搭建桥梁：

```
┌─────────────────────────────────────────────────────┐
│  用户层（QA / 测试人员）                              │
│  自然语言描述 → 查看用例卡片 → 一键执行 → 查看报告     │
├─────────────────────────────────────────────────────┤
│  TestPilot 平台（AI 中间层）                          │
│  代码分析 → LLM 生成/修改 → 执行调度 → 报告聚合       │
├─────────────────────────────────────────────────────┤
│  底层引擎                                             │
│  Playwright + pytest + Python                         │
└─────────────────────────────────────────────────────┘
```

### 1.4 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 前端 | Vue 3 + TypeScript + Ant Design Vue + Vite | 现代化 SPA 架构，组件库提供开箱即用的企业级 UI |
| 后端 | Python FastAPI + SQLAlchemy (异步) + Pydantic v2 | 高性能异步框架，原生支持 WebSocket |
| 数据库 | SQLite (开发) → PostgreSQL (生产) | aiosqlite 异步驱动，Alembic 管理迁移 |
| 测试引擎 | Playwright + pytest-playwright | 业界主流浏览器自动化框架 |
| AI 引擎 | OpenAI 兼容接口 | 可配置 endpoint/key/model，支持 GPT、Claude、DeepSeek、通义千问等 |
| 实时通信 | WebSocket | 测试执行过程实时推送状态 |
| 版本控制 | GitPython | 用于拉取被测项目源码 |

---

## 2. 目标用户与使用场景

### 2.1 目标用户画像

#### 主要用户：非编码 QA / 测试人员

| 特征 | 描述 |
|------|------|
| **角色** | QA 工程师、测试主管、测试专员 |
| **技能** | 熟悉测试理论（等价类、边界值、场景法等），了解 Web 应用交互逻辑 |
| **短板** | 不会编写代码，不熟悉命令行操作，不了解测试框架的具体语法 |
| **诉求** | 希望能用自然语言描述测试步骤，并自动生成可执行的测试脚本 |
| **日常工具** | Excel 管理用例、Jira 跟踪缺陷、浏览器手动测试 |

#### 次要用户：测试开发工程师

| 特征 | 描述 |
|------|------|
| **角色** | SDET（Software Development Engineer in Test） |
| **技能** | 具备 Python/Playwright 编程能力 |
| **诉求** | 使用 TestPilot 加速用例编写，利用自动生成功能快速覆盖基础场景，然后在代码层面做精细化调整 |

#### 潜在用户：项目经理 / 产品经理

| 特征 | 描述 |
|------|------|
| **角色** | PM、PO |
| **诉求** | 查看测试覆盖情况和执行报告，了解项目质量状态 |

### 2.2 核心使用场景

#### 场景一：新项目快速建立测试覆盖

> **角色**：QA 工程师小李  
> **背景**：团队新开发了一个电商后台管理系统，需要建立 E2E 测试覆盖  
> **操作流程**：
> 1. 小李在 TestPilot 创建项目，填写 Git 仓库地址和被测站点 URL
> 2. 点击"拉取代码"，系统 clone 项目源码
> 3. 点击"自动生成用例"，系统分析代码结构后，LLM 生成一批测试用例
> 4. 小李逐条审查用例卡片，用自然语言描述确认或修改（如"登录后检查左侧菜单是否展开"）
> 5. 选中所有用例，一键执行
> 6. 查看执行报告，确认通过率

#### 场景二：迭代中补充测试用例

> **角色**：QA 工程师小王  
> **背景**：开发新增了"优惠券领取"功能，需要补充对应的测试用例  
> **操作流程**：
> 1. 小王在已有项目中点击"新增用例"
> 2. 用自然语言描述测试步骤：*"打开优惠券列表页，点击第一张可用优惠券的领取按钮，验证弹出领取成功的提示，刷新页面后该优惠券状态变为已领取"*
> 3. LLM 自动生成对应的 Playwright 测试代码
> 4. 小王展开代码确认无误后保存
> 5. 执行该用例验证功能是否正常

#### 场景三：修改已有测试用例

> **角色**：QA 工程师小张  
> **背景**：某个登录测试用例之前只验证了跳转，现在需要增加验证用户名是否显示  
> **操作流程**：
> 1. 小张进入用例编辑页
> 2. 在"自然语言修改"输入框中输入：*"登录成功后增加一步：验证页面右上角显示当前登录的用户名"*
> 3. 点击"应用修改"，LLM 更新自然语言描述和测试代码
> 4. 小张确认修改后保存

#### 场景四：回归测试执行

> **角色**：测试主管老陈  
> **背景**：版本发布前需要跑一轮全量回归测试  
> **操作流程**：
> 1. 老陈进入项目详情页，勾选所有启用的用例
> 2. 点击"执行全部"
> 3. 实时查看执行进度（WebSocket 推送）
> 4. 执行完成后查看报告：通过率、失败详情、截图、耗时
> 5. 将报告截图发送给团队评审

---

## 3. 核心功能需求

### 3.1 功能模块总览

| 模块 | 功能 | 优先级 | 当前状态 |
|------|------|--------|---------|
| 项目管理 | 创建/编辑/删除项目、Git clone/pull | P0 | ✅ 已实现 |
| 代码分析 | 分析项目源码结构（路由、页面、组件、API） | P0 | ✅ 已实现 |
| 用例自动生成 | 基于代码分析结果，LLM 批量生成测试用例 | P0 | ✅ 已实现 |
| 用例管理 | CRUD、搜索/筛选、启用/禁用、分组 | P0 | ✅ 已实现 |
| 自然语言编辑 | 用自然语言修改用例，LLM 同步修改代码 | P0 | ✅ 已实现 |
| 测试执行 | 单条/批量/全部执行，后台 subprocess 运行 | P0 | ✅ 已实现 |
| 实时状态推送 | WebSocket 推送执行进度，前端实时更新 | P0 | ✅ 已实现 |
| 执行报告 | 通过率、失败详情、截图、耗时统计 | P0 | ✅ 已实现 |
| 执行历史 | 历史执行记录查看 | P1 | ✅ 已实现 |
| LLM 配置 | 可配置 endpoint/key/model | P0 | ✅ 已实现 |
| 用例录制模式 | 浏览器操作录制转测试用例 | P2 | 🔜 未来规划 |
| 数据驱动测试 | 参数化测试支持 | P2 | 🔜 未来规划 |
| CI/CD 集成 | Jenkins/GitHub Actions 等集成 | P2 | 🔜 未来规划 |
| 多用户协作 | 用户认证、权限管理 | P3 | 🔜 未来规划 |

### 3.2 模块详述

#### 3.2.1 项目管理模块

**功能描述**：管理被测试的 Web 项目，每个项目关联一个 Git 仓库和一个被测站点 URL。

**功能清单**：

| 功能点 | 描述 | 优先级 |
|--------|------|--------|
| 创建项目 | 填写项目名称、Git 仓库地址、分支、被测站点 URL | P0 |
| 项目列表 | 卡片式展示所有项目，显示名称、仓库地址、站点 URL、创建时间 | P0 |
| 编辑项目 | 修改项目基本信息 | P0 |
| 删除项目 | 删除项目及其关联的所有用例和执行记录（级联删除） | P0 |
| 拉取代码 | Clone 远程 Git 仓库到本地 workspace，shallow clone (depth=1) 节省空间 | P0 |
| 更新代码 | Pull 最新代码 | P0 |
| 代码状态 | 显示代码是否已拉取（已拉取/未拉取标签） | P0 |

**业务规则**：
- 创建项目时，项目名称、Git 仓库地址、被测站点 URL 为必填
- 分支默认为 `main`
- 代码拉取使用 `git clone --depth 1`，仅获取最新版本
- 重复拉取时先删除旧目录再重新 clone
- 删除项目时级联删除关联的用例、执行记录

**前端交互**：
- 项目列表页采用卡片布局（响应式 3 列 → 2 列 → 1 列）
- 创建项目通过 Modal 对话框
- 删除操作需二次确认（Popconfirm）

---

#### 3.2.2 代码分析引擎

**功能描述**：扫描被测项目的源码结构，提取路由、页面文件、API 接口、表单等关键信息，生成结构化分析报告供 LLM 消费。

**分析能力**：

| 分析维度 | 支持范围 | 说明 |
|----------|---------|------|
| 框架检测 | Next.js, Nuxt, React, Vue, Angular, Svelte, Python Web | 基于 package.json / pyproject.toml 判断 |
| 路由扫描 | Next.js App Router, Pages Router, React Router, Vue Router | 文件系统路由 + 代码内路由定义 |
| 页面文件 | src/pages, src/views, app/**/page.* 等常见目录 | 提取组件名称和页面摘要 |
| API 接口 | Next.js API Routes, Express/Fastify/Koa 路由 | 提取 HTTP 方法和路径 |
| 表单元素 | HTML `<form>`, `<input>` | 提取表单字段名 |
| 登录/注册 | 关键词匹配 (login, signin, register, signup, 登录, 注册) | 标识认证相关页面 |

**分析流程**：
1. 检测项目框架类型
2. 扫描路由定义（文件系统 + 代码声明）
3. 查找页面/视图文件并提取摘要
4. 查找 API 接口定义
5. 查找表单和交互元素
6. 如以上均无结果，回退到列出所有源文件

**过滤规则**：
- 跳过 `node_modules`, `.git`, `dist`, `build`, `.next`, `__pycache__`, `.nuxt` 目录
- 仅扫描 `.tsx`, `.ts`, `.jsx`, `.js`, `.vue`, `.svelte`, `.py` 文件
- 页面摘要提取每个文件前 50 行

---

#### 3.2.3 用例自动生成

**功能描述**：基于代码分析结果，通过 LLM 批量生成测试用例。每条用例包含自然语言描述和完整的 Python Playwright 测试脚本。

**生成流程**：
1. 用户点击"自动生成用例"按钮
2. 后端调用代码分析引擎，获取项目结构分析结果
3. 构造 prompt，将分析结果发送给 LLM
4. LLM 返回 JSON 格式的测试用例数组
5. 解析 JSON，批量入库

**LLM Prompt 设计要点**：
- 角色：资深 QA 工程师 + Playwright Python 测试专家
- 每条用例包含：title, description, script_content, group_name
- 代码要求：pytest + playwright sync_api，参数为 `page: Page`，使用 `expect()` 断言
- 代码注释使用中文
- 被测站点 base_url 作为上下文参数传入
- 返回格式：`{"test_cases": [...]}`
- temperature 设为 0.3（偏确定性），max_tokens 设为 8192

**业务规则**：
- 必须先拉取代码才能生成用例
- 每次生成会追加新用例（不覆盖已有用例）
- 生成失败时返回 LLM 格式错误提示

---

#### 3.2.4 用例管理

**功能描述**：对测试用例进行全生命周期管理，包括查看、搜索、筛选、创建、编辑、删除、启用/禁用。

**功能清单**：

| 功能点 | 描述 | 优先级 |
|--------|------|--------|
| 用例列表 | 表格展示，含标题、描述、分组、启用状态、操作列 | P0 |
| 搜索 | 按标题和描述的关键词搜索 | P0 |
| 筛选 | 按分组名（group_name）和启用状态筛选 | P1 |
| 批量选中 | 复选框批量选中用例 | P0 |
| 启用/禁用 | Switch 开关控制用例是否参与执行 | P0 |
| 创建用例 | 手动创建用例（标题 + 自然语言描述） | P0 |
| 编辑用例 | 编辑标题、自然语言描述、测试代码 | P0 |
| 删除用例 | 删除用例（二次确认） | P0 |
| 查看代码 | 可展开/折叠查看底层 Playwright 测试代码 | P0 |

**用例数据结构**：
- `title`：用例标题（简短，如"用户登录功能测试"）
- `description`：自然语言描述（详细的步骤说明）
- `script_content`：Python Playwright 测试脚本代码
- `group_name`：分组名（如"登录模块"、"订单模块"）
- `tags`：标签（逗号分隔）
- `enabled`：是否启用

**前端交互**：
- 列表页分页展示（默认 20 条/页，可切换）
- 搜索框支持即时搜索
- 新增用例通过 Modal 对话框
- 编辑页面为独立路由页面

---

#### 3.2.5 自然语言编辑

**功能描述**：用户通过自然语言描述修改意图，LLM 同步更新测试用例的自然语言描述和测试代码。

**交互流程**：
1. 用户在用例编辑页的"自然语言修改"输入框中输入修改指令
2. 如：*"在登录后增加一步验证用户头像是否显示"*
3. 点击"应用修改"或按 Enter
4. 后端将当前用例上下文（标题、描述、代码）+ 修改指令组装成 prompt 发送给 LLM
5. LLM 返回更新后的 description 和 script_content
6. 前端自动展开代码区域，让用户确认修改结果
7. 用户确认后手动保存

**LLM Prompt 设计**：
- 角色：Playwright Python 测试脚本专家
- 输入：当前用例标题、自然语言描述、现有测试代码、用户修改指令
- 输出：JSON 格式 `{"description": "...", "script_content": "..."}`
- temperature 设为 0.2（高确定性）

**业务规则**：
- 修改后自动展开代码供用户检查
- 修改不会自动保存，需用户确认后手动保存
- LLM 返回格式错误时给出友好提示
- 支持处理 markdown code block 包裹的 JSON 响应

---

#### 3.2.6 测试执行引擎

**功能描述**：将用户选中的测试用例通过 pytest + Playwright 在后台执行，实时推送执行状态。

**执行流程**：

```
用户选择用例 → 创建 Execution 记录 → 后台 asyncio.create_task
  │
  ├─ 创建临时测试目录 workspace/tests/{execution_id}/
  ├─ 生成 conftest.py（注入 base_url）
  ├─ 将每条用例的 script_content 写入独立 .py 文件
  ├─ 构造 pytest 命令并 subprocess 执行
  │    └─ pytest {dir} --tb=short -v --screenshot on --json-report
  ├─ 解析 json-report 获取每条用例结果
  ├─ 逐条创建 ExecutionDetail 并通过 WebSocket 推送进度
  └─ 更新 Execution 最终状态（passed/failed/error）
```

**pytest 命令参数**：

| 参数 | 说明 |
|------|------|
| `--tb=short` | 简短的 traceback 输出 |
| `-v` | 详细模式 |
| `--screenshot on` | 开启截图（失败时自动截图） |
| `--output {results_dir}` | 输出目录 |
| `--json-report` | 生成 JSON 格式报告 |
| `--json-report-file={path}` | 报告文件路径 |
| `--headed`（可选） | 非 headless 模式运行 |

**执行模式**：
- **单条执行**：选中单条用例执行
- **批量执行**：勾选多条用例执行
- **全部执行**：不勾选时默认执行所有启用的用例

**WebSocket 消息类型**：

| 消息类型 | 字段 | 触发时机 |
|----------|------|---------|
| `execution:start` | execution_id, total | 执行开始 |
| `execution:progress` | execution_id, case_id, status, error | 每条用例完成 |
| `execution:complete` | execution_id, status, passed, failed | 全部执行完成 |

**错误处理**：
- pytest 进程异常退出：标记 Execution 状态为 `error`
- json-report 文件不存在：回退到根据 exit code 判断
- 单条用例解析失败：不影响其他用例，该条标记为 `failed`

---

#### 3.2.7 执行报告

**功能描述**：展示测试执行的详细结果，包括整体统计和每条用例的执行详情。

**报告内容**：

| 维度 | 展示内容 |
|------|---------|
| 整体统计 | 总用例数、通过数、失败数、跳过数 |
| 通过率 | 环形进度条可视化展示 |
| 执行状态 | 当前状态标签（PENDING / RUNNING / PASSED / FAILED / ERROR） |
| 用例详情 | 每条用例的状态、耗时、错误信息 |
| 错误详情 | 失败用例的 traceback / crash 信息 |
| 截图 | 失败截图路径（当前已存储路径，展示能力待完善） |

**前端交互**：
- 执行详情页顶部显示整体统计 + 进度环
- 下方表格展示每条用例的状态和详情
- 状态图标区分：✅ 通过 / ❌ 失败 / ⏳ 等待 / 🔄 运行中 / ⏭ 跳过
- 实时刷新：优先 WebSocket，降级为 3 秒轮询

---

#### 3.2.8 执行历史

**功能描述**：查看项目的历史执行记录列表。

**功能清单**：
- 按时间倒序展示执行记录
- 显示：执行时间、状态、总数、通过数、失败数
- 可点击查看执行详情
- 默认展示最近 20 条记录

---

#### 3.2.9 系统设置

**功能描述**：管理 LLM 大模型的 API 配置。

**配置项**：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| API 端点 (Endpoint) | OpenAI 兼容接口地址 | `https://api.openai.com/v1` |
| API Key | 鉴权密钥 | `sk-xxxx` |
| 模型名称 | 使用的模型标识 | `gpt-4o` / `deepseek-chat` / `qwen-plus` |

**安全性**：
- API Key 在返回前端时做脱敏处理（保留前 4 位和后 4 位，中间用 `*` 替代）
- 配置存储在数据库 `app_settings` 表中（key-value 形式）
- 支持通过环境变量 `PTP_LLM_ENDPOINT`、`PTP_LLM_API_KEY`、`PTP_LLM_MODEL` 设置默认值

---

## 4. 用户流程图

### 4.1 主流程：从零到报告

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  配置 LLM │───▶│  创建项目 │───▶│  拉取代码 │───▶│ 自动生成  │───▶│ 审查用例  │
│  (首次)   │    │          │    │          │    │  用例     │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                                     │
                                                          ┌──────────┼──────────┐
                                                          ▼          ▼          ▼
                                                    ┌──────────┐ ┌────────┐ ┌────────┐
                                                    │ NL 修改   │ │  删除   │ │  确认   │
                                                    │ (可选)    │ │  用例   │ │  通过   │
                                                    └────┬─────┘ └────────┘ └────┬───┘
                                                         │                       │
                                                         └───────────┬───────────┘
                                                                     ▼
                                                               ┌──────────┐
                                                               │ 选择执行  │
                                                               │ (单/批/全)│
                                                               └────┬─────┘
                                                                    ▼
                                                               ┌──────────┐
                                                               │ 实时查看  │
                                                               │ 执行进度  │
                                                               └────┬─────┘
                                                                    ▼
                                                               ┌──────────┐
                                                               │ 查看报告  │
                                                               │          │
                                                               └──────────┘
```

### 4.2 子流程：用例自然语言修改

```
用户进入用例编辑页
  │
  ├─ 查看当前自然语言描述
  ├─ (可选) 展开查看当前测试代码
  │
  ▼
输入自然语言修改指令
  │  例："在提交表单后增加验证弹出成功提示"
  ▼
点击"应用修改"
  │
  ▼
后端组装 prompt（当前用例上下文 + 修改指令）
  │
  ▼
LLM 返回更新后的 description + script_content
  │
  ▼
前端自动展开代码区域供用户检查
  │
  ├─ 满意 → 点击"保存"
  └─ 不满意 → 继续输入新的修改指令 / 手动编辑描述或代码
```

### 4.3 子流程：测试执行

```
用户选择要执行的用例
  │
  ├─ 勾选特定用例 → 执行选中
  └─ 不勾选 → 执行所有启用的用例
  │
  ▼
点击"执行"按钮
  │
  ▼
前端发送 POST /api/execute（case_ids, headless）
  │
  ▼
后端创建 Execution 记录，返回 execution_id
  │
  ▼
前端跳转到执行详情页，建立 WebSocket 连接
  │
  ▼
后端 asyncio.create_task 异步执行:
  │
  ├─ 创建临时目录，写入 conftest.py 和测试文件
  ├─ 启动 pytest subprocess
  ├─ 逐条完成时通过 WS 推送 execution:progress
  └─ 全部完成时推送 execution:complete
  │
  ▼
前端实时更新执行状态、统计数据、进度环
  │
  ▼
执行完成，展示最终报告
```

### 4.4 页面导航结构

```
TestPilot
  │
  ├─ /projects              → 项目列表页
  │   └─ /project/:id       → 项目详情页
  │       ├─ (default)       → 用例列表 Tab
  │       └─ /executions     → 执行历史 Tab
  │
  ├─ /testcase/:id          → 用例编辑页
  │
  ├─ /execution/:id         → 执行详情页
  │
  └─ /settings              → 系统设置页
```

---

## 5. 非功能性需求

### 5.1 性能要求

| 维度 | 指标 | 说明 |
|------|------|------|
| 页面加载 | 首屏 < 2s | Vite 构建 + 路由懒加载 |
| API 响应 | 常规 CRUD < 200ms | FastAPI 异步处理 |
| LLM 生成 | 用例生成 < 60s | 取决于 LLM 服务响应速度 |
| LLM 编辑 | 单条修改 < 30s | 取决于 LLM 服务响应速度 |
| 测试执行 | 不设上限 | 取决于用例数量和复杂度 |
| 并发用户 | 支持 10+ 并发 | 当前单机部署架构 |
| WebSocket | 消息延迟 < 1s | 实时推送执行进度 |

### 5.2 安全性要求

| 维度 | 要求 | 当前状态 |
|------|------|---------|
| API Key 安全 | 前端展示脱敏，服务端存储原文 | ✅ 已实现 |
| CORS | 仅允许配置的 origin | ✅ 已实现（localhost:5173/3000） |
| 输入校验 | Pydantic 模型校验所有输入 | ✅ 已实现 |
| SQL 注入防护 | SQLAlchemy ORM 参数化查询 | ✅ 已实现 |
| 认证授权 | 用户登录 + 权限管理 | ❌ 待实现（当前无认证） |
| Git 仓库安全 | 支持 SSH key / token 认证 | ❌ 待实现（当前仅支持公开仓库或 URL 内嵌 token） |
| LLM 数据安全 | 代码发送给 LLM 的隐私风险需用户知悉 | ⚠️ 需文档告知 |

### 5.3 可扩展性

| 维度 | 设计 | 说明 |
|------|------|------|
| 数据库 | SQLite → PostgreSQL | 当前使用 SQLAlchemy 异步 ORM，切换数据库仅需改连接字符串 |
| LLM 适配 | OpenAI 兼容接口 | 所有支持 OpenAI API 格式的模型均可无缝切换 |
| 框架分析 | 可扩展分析规则 | analyzer.py 中各分析函数独立，易于新增框架支持 |
| 前端组件 | Ant Design Vue 组件库 | 企业级组件，可快速扩展新功能页面 |
| 部署形态 | 独立 Web 应用 → CI/CD 插件 | 当前独立运行，未来可集成到 CI/CD 流水线 |

### 5.4 可靠性

| 维度 | 设计 |
|------|------|
| 执行容错 | 单条用例失败不影响其他用例继续执行 |
| WebSocket 降级 | WebSocket 连接失败时自动降级为 3 秒轮询 |
| LLM 容错 | LLM 返回格式异常时给出友好错误提示 |
| 进程隔离 | 测试执行在独立 subprocess 中，不影响主进程 |
| JSON 解析容错 | 支持处理 LLM 返回中包裹 markdown code block 的情况 |

### 5.5 可维护性

| 维度 | 设计 |
|------|------|
| 代码规范 | 前端 TypeScript 强类型，后端 Pydantic 模型校验 |
| 模块划分 | 前后端分离；后端按 routers / services / models / schemas 分层 |
| 配置管理 | 环境变量 + .env 文件 + 数据库动态配置，三级优先级 |
| 日志记录 | Python logging 模块记录执行日志 |

---

## 6. 数据模型说明

### 6.1 ER 关系图

```
┌─────────────┐      1:N      ┌───────────────┐
│   Project    │──────────────▶│   TestCase    │
│             │              │               │
│ id (PK)     │              │ id (PK)       │
│ name        │              │ project_id(FK)│
│ git_url     │              │ title         │
│ branch      │              │ description   │
│ base_url    │              │ script_path   │
│ repo_path   │              │ script_content│
│ created_at  │              │ group_name    │
│ updated_at  │              │ tags          │
│             │              │ enabled       │
└──────┬──────┘              │ created_at    │
       │                     │ updated_at    │
       │ 1:N                 └───────┬───────┘
       │                             │ 1:N
       ▼                             ▼
┌─────────────┐      1:N     ┌────────────────────┐
│  Execution  │─────────────▶│  ExecutionDetail   │
│             │              │                    │
│ id (PK)     │              │ id (PK)            │
│ project_id  │◀─FK──────────│ execution_id (FK)  │
│ status      │              │ test_case_id (FK)  │──FK──▶ TestCase
│ total_cases │              │ status             │
│ passed_count│              │ error_message      │
│ failed_count│              │ screenshot_path    │
│ skipped_cnt │              │ duration_ms        │
│ start_time  │              └────────────────────┘
│ end_time    │
│ report_path │
│ created_at  │
└─────────────┘

┌────────────────┐
│  AppSettings   │
│                │
│ id (PK, auto)  │
│ key (unique)   │
│ value          │
└────────────────┘
```

### 6.2 表结构详述

#### 6.2.1 projects - 项目表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK, UUID | 主键，自动生成 UUID |
| name | String(200) | NOT NULL | 项目名称 |
| git_url | String(500) | NOT NULL | Git 仓库地址 |
| branch | String(100) | DEFAULT 'main' | 分支名 |
| base_url | String(500) | NOT NULL | 被测站点 URL |
| repo_path | String(500) | NULLABLE | 本地代码存储路径 |
| created_at | DateTime | DEFAULT now() | 创建时间 (UTC) |
| updated_at | DateTime | DEFAULT now(), ON UPDATE | 更新时间 (UTC) |

#### 6.2.2 test_cases - 测试用例表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK, UUID | 主键 |
| project_id | String(36) | FK → projects.id, NOT NULL | 所属项目 |
| title | String(300) | NOT NULL | 用例标题 |
| description | Text | NOT NULL | 自然语言描述 |
| script_path | String(500) | NULLABLE | 测试脚本文件路径 |
| script_content | Text | NULLABLE | 测试脚本代码内容 |
| group_name | String(100) | DEFAULT 'default' | 分组名 |
| tags | String(500) | DEFAULT '' | 标签（逗号分隔） |
| enabled | Boolean | DEFAULT true | 是否启用 |
| created_at | DateTime | DEFAULT now() | 创建时间 |
| updated_at | DateTime | DEFAULT now(), ON UPDATE | 更新时间 |

#### 6.2.3 executions - 执行记录表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK, UUID | 主键 |
| project_id | String(36) | FK → projects.id, NOT NULL | 所属项目 |
| status | String(20) | DEFAULT 'pending' | 状态：pending/running/passed/failed/error |
| total_cases | Integer | DEFAULT 0 | 总用例数 |
| passed_count | Integer | DEFAULT 0 | 通过数 |
| failed_count | Integer | DEFAULT 0 | 失败数 |
| skipped_count | Integer | DEFAULT 0 | 跳过数 |
| start_time | DateTime | NULLABLE | 开始时间 |
| end_time | DateTime | NULLABLE | 结束时间 |
| report_path | String(500) | NULLABLE | 报告文件路径 |
| created_at | DateTime | DEFAULT now() | 创建时间 |

#### 6.2.4 execution_details - 执行详情表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK, UUID | 主键 |
| execution_id | String(36) | FK → executions.id, NOT NULL | 所属执行记录 |
| test_case_id | String(36) | FK → test_cases.id, NOT NULL | 关联用例 |
| status | String(20) | DEFAULT 'pending' | 状态：pending/running/passed/failed/skipped |
| error_message | Text | NULLABLE | 错误信息 |
| screenshot_path | String(500) | NULLABLE | 截图路径 |
| duration_ms | Float | DEFAULT 0 | 执行耗时（毫秒） |

#### 6.2.5 app_settings - 应用配置表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, 自增 | 主键 |
| key | String(100) | UNIQUE, NOT NULL | 配置键名 |
| value | Text | DEFAULT '' | 配置值 |

**当前使用的配置键**：
- `llm_endpoint`：LLM API 端点
- `llm_api_key`：LLM API 密钥
- `llm_model`：LLM 模型名称

### 6.3 级联关系

| 父表 | 子表 | 关系 | 级联策略 |
|------|------|------|---------|
| Project | TestCase | 1:N | CASCADE DELETE |
| Project | Execution | 1:N | CASCADE DELETE |
| Execution | ExecutionDetail | 1:N | CASCADE DELETE |
| TestCase | ExecutionDetail | 1:N | CASCADE DELETE |

---

## 7. API 接口清单

### 7.1 项目管理 API

| 方法 | 路径 | 描述 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/project` | 创建项目 | `ProjectCreate` | `ProjectOut` |
| GET | `/api/project` | 获取项目列表 | - | `ProjectOut[]` |
| GET | `/api/project/{id}` | 获取项目详情 | - | `ProjectOut` |
| PUT | `/api/project/{id}` | 更新项目 | `ProjectUpdate` | `ProjectOut` |
| DELETE | `/api/project/{id}` | 删除项目 | - | `{message}` |
| POST | `/api/project/{id}/clone` | 拉取代码 | - | `{message, repo_path}` |
| POST | `/api/project/{id}/pull` | 更新代码 | - | `{message}` |

**Schema 定义**：

```
ProjectCreate {
  name: string          (必填)
  git_url: string       (必填)
  branch: string        (默认 "main")
  base_url: string      (必填)
}

ProjectUpdate {
  name?: string
  git_url?: string
  branch?: string
  base_url?: string
}

ProjectOut {
  id: string
  name: string
  git_url: string
  branch: string
  base_url: string
  repo_path: string | null
  created_at: datetime
  updated_at: datetime
}
```

### 7.2 用例管理 API

| 方法 | 路径 | 描述 | 请求参数/体 | 响应 |
|------|------|------|------------|------|
| GET | `/api/testcase` | 获取用例列表 | Query: project_id(必填), group_name?, enabled?, search? | `TestCaseOut[]` |
| GET | `/api/testcase/{id}` | 获取用例详情 | - | `TestCaseOut` |
| POST | `/api/testcase` | 创建用例 | `TestCaseCreate` | `TestCaseOut` |
| PUT | `/api/testcase/{id}` | 更新用例 | `TestCaseUpdate` | `TestCaseOut` |
| DELETE | `/api/testcase/{id}` | 删除用例 | - | `{message}` |
| POST | `/api/testcase/{id}/edit` | 自然语言编辑 | `NLEditRequest` | `NLEditResponse` |

**Schema 定义**：

```
TestCaseCreate {
  project_id: string    (必填)
  title: string         (必填)
  description: string   (必填)
  script_content?: string
  group_name: string    (默认 "default")
  tags: string          (默认 "")
}

TestCaseUpdate {
  title?: string
  description?: string
  script_content?: string
  group_name?: string
  tags?: string
  enabled?: boolean
}

NLEditRequest {
  instruction: string   (用户的自然语言修改指令)
}

NLEditResponse {
  description: string   (更新后的描述)
  script_content: string (更新后的代码)
}
```

### 7.3 用例生成 API

| 方法 | 路径 | 描述 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/generate` | 自动生成测试用例 | `GenerateRequest` | `TestCaseOut[]` |

**Schema 定义**：

```
GenerateRequest {
  project_id: string    (必填)
}
```

### 7.4 测试执行 API

| 方法 | 路径 | 描述 | 请求参数/体 | 响应 |
|------|------|------|------------|------|
| POST | `/api/execute` | 启动测试执行 | `ExecuteRequest` | `ExecutionOut` |
| GET | `/api/execute/history` | 获取执行历史 | Query: project_id, limit(默认20) | `ExecutionOut[]` |
| GET | `/api/execute/{id}` | 获取执行详情 | - | `ExecutionOut` |
| GET | `/api/execute/{id}/details` | 获取执行用例详情 | - | `ExecutionDetailOut[]` |

**Schema 定义**：

```
ExecuteRequest {
  case_ids: string[]    (必填，要执行的用例 ID)
  headless: boolean     (默认 true)
}

ExecutionOut {
  id: string
  project_id: string
  status: string        ("pending" | "running" | "passed" | "failed" | "error")
  total_cases: number
  passed_count: number
  failed_count: number
  skipped_count: number
  start_time: datetime | null
  end_time: datetime | null
  created_at: datetime
}

ExecutionDetailOut {
  id: string
  execution_id: string
  test_case_id: string
  status: string        ("pending" | "running" | "passed" | "failed" | "skipped")
  error_message: string | null
  screenshot_path: string | null
  duration_ms: number
}
```

### 7.5 系统设置 API

| 方法 | 路径 | 描述 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/api/settings/llm` | 获取 LLM 配置 | - | `LLMSettingsOut` |
| PUT | `/api/settings/llm` | 更新 LLM 配置 | `LLMSettingsUpdate` | `LLMSettingsOut` |

**Schema 定义**：

```
LLMSettingsUpdate {
  llm_endpoint: string  (必填)
  llm_api_key: string   (必填)
  llm_model: string     (必填)
}

LLMSettingsOut {
  llm_endpoint: string
  llm_api_key: string   (脱敏显示)
  llm_model: string
}
```

### 7.6 WebSocket 接口

| 路径 | 描述 |
|------|------|
| `ws://host/ws/execution/{execution_id}` | 订阅特定执行记录的实时状态 |

### 7.7 健康检查

| 方法 | 路径 | 描述 | 响应 |
|------|------|------|------|
| GET | `/api/health` | 健康检查 | `{status: "ok", app: "Playwright Test Platform"}` |

---

## 8. 未来规划

### 8.1 短期（v1.1 - v1.2）

#### 8.1.1 用例录制模式 [P2]

**目标**：用户在浏览器中手动操作，系统自动录制操作步骤并转化为测试用例。

**实现思路**：
- 集成 Playwright 的 codegen 录制能力
- 提供"开始录制"按钮，在新浏览器窗口中打开被测站点
- 用户操作结束后，录制脚本自动转化为用例（自然语言描述 + 代码）
- LLM 优化录制生成的代码（添加合理的断言、等待、注释等）

#### 8.1.2 数据驱动测试 [P2]

**目标**：支持参数化测试，同一个用例模板配合不同测试数据集执行。

**实现思路**：
- 用例支持定义参数变量（如 `{{username}}`, `{{password}}`）
- 提供数据集管理界面（表格编辑或 CSV 导入）
- 执行时自动展开为多条实际测试

#### 8.1.3 截图展示优化 [P1]

**目标**：在执行报告中直接展示失败截图。

**实现思路**：
- 后端提供静态文件服务（mount workspace/tests 目录）
- 前端在执行详情中内嵌截图图片
- 支持点击放大查看

#### 8.1.4 用例导入/导出 [P1]

**目标**：支持测试用例的批量导入和导出。

**实现思路**：
- 导出为 JSON / Excel 格式
- 导入支持 JSON / Excel，自动关联到项目
- 支持导出为标准 Playwright 测试项目目录结构

### 8.2 中期（v2.0）

#### 8.2.1 CI/CD 集成 [P2]

**目标**：将 TestPilot 集成到 CI/CD 流水线中，实现自动化回归测试。

**实现思路**：
- 提供 CLI 工具或 REST API 供 CI 系统调用
- 支持 Jenkins Plugin / GitHub Actions / GitLab CI 集成
- 测试结果回写到 PR / MR 评论
- 失败时阻塞合并

#### 8.2.2 多浏览器测试 [P2]

**目标**：支持在 Chromium、Firefox、WebKit 多浏览器上并行执行测试。

**实现思路**：
- pytest-playwright 原生支持 `--browser` 参数
- 执行配置增加浏览器选择项
- 报告中按浏览器维度聚合结果

#### 8.2.3 智能用例维护 [P2]

**目标**：当被测应用发生变更时，自动检测并建议更新受影响的测试用例。

**实现思路**：
- 对比 Git diff，识别变更的路由/页面/组件
- 标记可能受影响的测试用例
- LLM 辅助生成修改建议

#### 8.2.4 执行环境管理 [P2]

**目标**：支持配置多套执行环境（开发、测试、预发布等）。

**实现思路**：
- 项目支持多个 base_url 配置
- 执行时选择目标环境
- 环境变量注入

### 8.3 长期（v3.0）

#### 8.3.1 多用户协作 [P3]

**目标**：支持团队协作，包括用户认证、角色权限、操作日志。

**实现思路**：
- 用户管理（注册/登录/JWT 认证）
- 角色权限（管理员 / 测试主管 / 普通测试人员）
- 操作日志审计
- 项目级权限控制

#### 8.3.2 测试覆盖率分析 [P3]

**目标**：分析测试用例对被测应用的覆盖程度。

**实现思路**：
- 基于代码分析结果，计算路由/页面/API 的测试覆盖率
- 识别未被覆盖的功能点
- LLM 建议补充用例

#### 8.3.3 API 测试支持 [P3]

**目标**：除 E2E UI 测试外，支持纯 API 接口测试。

**实现思路**：
- 分析后端 API 接口定义
- 自动生成 API 测试用例（requests / httpx）
- 独立的 API 测试执行引擎

#### 8.3.4 移动端测试 [P3]

**目标**：扩展到移动端 Web 测试（响应式测试）。

**实现思路**：
- 利用 Playwright 的设备模拟能力
- 配置常用移动设备尺寸
- 移动端特有的交互测试（滑动、长按等）

#### 8.3.5 SaaS 化部署 [P3]

**目标**：提供云托管版本，用户无需自行部署。

**实现思路**：
- 多租户架构
- 基于 Kubernetes 的弹性执行节点
- 按用例执行量计费

---

## 附录

### A. 目录结构

```
playWright/
├── server/                          # 后端服务
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py            # 全局配置（Settings）
│   │   │   └── websocket.py         # WebSocket 连接管理器
│   │   ├── models/
│   │   │   └── database.py          # SQLAlchemy 数据模型 + 引擎
│   │   ├── routers/
│   │   │   ├── project.py           # 项目管理路由
│   │   │   ├── testcase.py          # 用例管理路由（含 NL 编辑）
│   │   │   ├── generate.py          # 用例自动生成路由
│   │   │   ├── execute.py           # 测试执行路由
│   │   │   └── settings.py          # 系统设置路由
│   │   ├── schemas/
│   │   │   └── schemas.py           # Pydantic 请求/响应模型
│   │   ├── services/
│   │   │   ├── analyzer.py          # 代码分析引擎
│   │   │   ├── executor.py          # 测试执行服务
│   │   │   ├── git_service.py       # Git 操作服务
│   │   │   └── llm_service.py       # LLM 调用服务
│   │   └── main.py                  # FastAPI 应用入口
│   └── pyproject.toml               # Python 项目配置
│
├── client/                          # 前端应用
│   ├── src/
│   │   ├── views/
│   │   │   ├── ProjectList.vue      # 项目列表页
│   │   │   ├── ProjectDetail.vue    # 项目详情页
│   │   │   ├── TestCaseList.vue     # 用例列表页
│   │   │   ├── TestCaseEdit.vue     # 用例编辑页
│   │   │   ├── ExecutionView.vue    # 执行详情页
│   │   │   ├── ExecutionHistory.vue # 执行历史页
│   │   │   └── SettingsView.vue     # 系统设置页
│   │   ├── services/
│   │   │   └── api.ts               # API 调用封装
│   │   ├── types/
│   │   │   └── index.ts             # TypeScript 类型定义
│   │   ├── router/
│   │   │   └── index.ts             # 路由配置
│   │   ├── stores/
│   │   │   └── project.ts           # Pinia 状态管理
│   │   ├── App.vue                  # 根组件（侧边栏布局）
│   │   └── main.ts                  # 应用入口
│   └── index.html
│
└── workspace/                       # 运行时工作目录（自动创建）
    ├── repos/                       # Git 克隆的项目代码
    │   └── {project_id}/
    ├── tests/                       # 测试执行临时目录
    │   └── {execution_id}/
    │       ├── conftest.py
    │       ├── test_xxx.py
    │       └── results/
    │           └── report.json
    └── data.db                      # SQLite 数据库文件
```

### B. 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `PTP_DEBUG` | `true` | 调试模式 |
| `PTP_DATABASE_URL` | `sqlite+aiosqlite:///workspace/data.db` | 数据库连接字符串 |
| `PTP_LLM_ENDPOINT` | `https://api.openai.com/v1` | LLM API 端点 |
| `PTP_LLM_API_KEY` | (空) | LLM API 密钥 |
| `PTP_LLM_MODEL` | `gpt-4o` | LLM 模型名称 |
| `PTP_HOST` | `0.0.0.0` | 服务监听地址 |
| `PTP_PORT` | `8000` | 服务监听端口 |
| `PTP_CORS_ORIGINS` | `["http://localhost:5173", "http://localhost:3000"]` | CORS 允许源 |

### C. 术语表

| 术语 | 说明 |
|------|------|
| E2E 测试 | End-to-End 测试，端到端测试，模拟真实用户操作验证完整业务流程 |
| Playwright | 微软开源的浏览器自动化框架，支持 Chromium、Firefox、WebKit |
| pytest | Python 标准测试框架 |
| LLM | Large Language Model，大语言模型 |
| NL Edit | Natural Language Edit，自然语言编辑 |
| headless | 无头模式，浏览器在后台运行不显示 UI |
| base_url | 被测站点的根 URL |
| conftest.py | pytest 的共享配置文件 |
