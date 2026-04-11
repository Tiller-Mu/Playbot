# MCP 页面用例自动生成功能说明

## 功能概述

MCP（Model Context Protocol）页面用例自动生成是 TestPilot 的核心功能，通过 Playwright 浏览器自动化技术，智能探索 Web 应用的所有页面，并为每个页面生成测试用例。

## 核心流程

```
1. 静态分析 → 发现组件（页面组件 + 普通组件）
   ↓
2. MCP 探索 → 访问入口点，自动点击链接发现所有页面
   ↓
3. 写入页面树 → 将发现的页面保存到数据库
   ↓
4. 生成用例 → 为每个页面生成多个测试用例
```

## 使用方法

### 1. 前置条件

- 项目已配置 `base_url`（被测站点地址）
- 项目代码已拉取（点击"拉取代码"按钮）
- Playwright 浏览器已安装（执行 `python -m playwright install chromium`）

### 2. 选择探索模式

在项目详情页左侧页面树底部，有两种 MCP 探索模式：

- **无头模式（快速执行）**：不显示浏览器窗口，执行速度快，适合生产环境
- **有头模式（人工检验）**：显示浏览器窗口，可以实时观察 MCP 探索过程，便于人工验证

### 3. 执行 MCP 生成

1. 点击页面右上角的 **"MCP 生成用例"** 按钮
2. 确认弹窗中会显示当前选择的模式
3. 点击"开始生成"按钮
4. 等待 MCP 探索完成（有头模式可以看到浏览器自动操作过程）
5. 生成成功后会显示生成的测试用例数量

### 4. 查看结果

- 左侧页面树会自动刷新，显示 MCP 发现的所有页面
- 右侧用例列表会显示为每个页面生成的测试用例
- 可以点击页面树中的具体页面，查看该页面的专属用例

## MCP 规则文件

### 规则文件位置

```
workspace/rules/{project_id}/
├── _global.md          # 全局规则（适用于所有页面）
├── login.md            # 登录页规则（对应 /login 路由）
├── index.md            # 首页规则（对应 / 路由）
└── user-settings.md    # 用户设置页规则（对应 /user/settings 路由）
```

### 规则文件命名规则

| 路由路径 | 规则文件名 |
|---------|----------|
| `/` | `index.md` |
| `/login` | `login.md` |
| `/user/settings` | `user-settings.md` |
| 全局规则 | `_global.md` |

### 规则文件内容示例

```markdown
## 探索约束
- 不要点击"退出登录"按钮
- 不要修改用户数据
- 只读操作，不要提交表单

## 重点关注
- 验证页面加载速度
- 检查所有链接是否有效
- 验证表单验证逻辑

## 测试用例要求
- 为每个输入字段生成边界测试
- 测试错误提示是否正确显示
- 验证页面响应式设计
```

## API 接口

### MCP 生成用例

**接口**: `POST /api/generate/mcp`

**请求体**:
```json
{
  "project_id": "项目ID",
  "headless": true  // true=无头模式, false=有头模式
}
```

**响应**:
```json
[
  {
    "id": "用例ID",
    "project_id": "项目ID",
    "page_id": "页面ID",
    "title": "测试用例标题",
    "description": "用例描述",
    "script_content": "Playwright Python 测试代码",
    "group_name": "页面路径",
    "enabled": true,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00"
  }
]
```

## 技术实现

### 服务层

1. **component_analyzer.py** - 静态组件分析
   - 扫描项目源码（Vue/React/Next.js）
   - 提取页面组件和普通组件
   - 分析组件 import 关系
   - 生成入口点列表

2. **mcp_explorer.py** - MCP 页面探索
   - 启动 Playwright 浏览器（支持有头/无头模式）
   - BFS 广度优先搜索策略
   - 从入口点开始自动探索
   - 检测页面使用的组件
   - 提取 DOM 信息和链接
   - 自动排除站外链接

3. **mcp_rules.py** - 规则文件管理
   - 加载全局规则和页面规则
   - 规则的保存、删除、列表查询
   - 路由路径与文件名转换

### 探索策略

```
初始化:
  discovered_pages = {}  # 已发现的页面
  pages_to_explore = [入口点列表]  # 待探索队列

循环探索:
  while pages_to_explore 不为空:
    current_page = pages_to_explore.pop(0)
    
    1. 访问 current_page
    2. 提取页面信息（标题、DOM、组件、链接）
    3. 将 current_page 加入 discovered_pages
    4. 提取所有站内链接
    5. 对于每个未发现的站内链接:
       加入 pages_to_explore 队列
    
    直到所有页面探索完成
```

## 注意事项

1. **首次使用**：需要先安装 Playwright 浏览器
   ```bash
   cd server
   python -m playwright install chromium
   ```

2. **有头模式**：执行时会自动打开浏览器窗口，可以看到 MCP 自动点击链接、探索页面的过程

3. **探索时间**：根据网站规模，探索时间从几分钟到几十分钟不等

4. **站点登录**：如果网站需要登录，建议：
   - 在 `_global.md` 中说明登录凭据
   - 或者先手动登录，MCP 会继承浏览器状态

5. **排除站外链接**：MCP 会自动识别并排除站外链接，只探索同一域名下的页面

## 故障排查

### 问题：浏览器下载失败

**解决方案**：
```bash
# 设置国内镜像（如果在中国）
export PLAYWRIGHT_CHROMIUM_DOWNLOAD_BASE_URL=https://npmmirror.com/mirrors/playwright/
python -m playwright install chromium
```

### 问题：MCP 探索卡住

**解决方案**：
1. 使用有头模式观察探索过程
2. 检查 `base_url` 是否正确
3. 查看后端日志（`server` 目录下的控制台输出）

### 问题：生成的用例数量少

**解决方案**：
1. 编写更详细的全局规则（`_global.md`）
2. 为特定页面编写规则文件
3. 确保 `base_url` 指向的是完整的 Web 应用

## 版本历史

- **v0.1.3** - 初始版本，实现核心 MCP 探索功能
  - 静态组件分析
  - BFS 页面发现策略
  - 有头/无头模式切换
  - 页面级规则文件支持
