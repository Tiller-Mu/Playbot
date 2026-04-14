# 发布日志

## v0.1.9 (2026-04-14)

### 新增功能
- ✨ Windows平台Playwright完全兼容
  - 使用同步API + 独立线程方案，彻底解决asyncio子进程问题
  - 消除greenlet跨线程切换错误
  - 每次分析自动创建/关闭浏览器，无需手动管理生命周期
  - 移除`initialize()`和`cleanup()`方法，简化API调用

### 优化改进
- 🔧 测试用例生成流程优化
  - Playwright分析改为独立线程执行，避免事件循环冲突
  - DOM获取失败时立即退出，不继续静态分析
  - 使用`file_path`字段读取完整源代码路径
  - 增强错误提示，指导用户排查问题

- 🎨 MCP日志显示优化
  - 修复横向滚动条问题，实现连续文本显示
  - 添加智能滚动控制，用户手动滚动时暂停自动滚动
  - 优化CSS文本换行策略

- 🎯 项目结构清理
  - 删除30+个临时脚本和测试文件
  - 删除备份文件和已执行的迁移脚本
  - 清理空目录（scripts、alembic、.pytest_cache）
  - 代码库更加整洁，只保留核心功能代码

### 问题修复
- 🐛 修复Playwright在Windows上的NotImplementedError
  - 根本原因：asyncio ProactorEventLoop不支持subprocess_exec
  - 解决方案：使用同步API + threading独立线程
  - 所有Playwright操作在同一线程完成，避免greenlet冲突

- 🐛 修复源代码文件路径错误
  - 数据库新增`file_path`字段存储完整相对路径
  - 前端创建页面时传递file_path
  - 后端使用file_path读取Vue源代码

- 🐛 修复启动脚本Windows兼容性
  - 使用`cmd /c`包装命令，避免shell冲突
  - 修复`CREATE_NEW_CONSOLE`和`shell=True`的兼容性问题

### 技术细节
- PlaywrightMCPService架构重构
  - 从异步API改为同步API + threading
  - 使用`_run_in_thread()`确保线程安全
  - 每次调用自动创建和清理浏览器实例
  - 线程超时保护（60秒）

- 代码清理
  - 删除6个测试脚本（test_*.py）
  - 删除3个迁移脚本（migrate_*.py）
  - 删除1个备份文件（generate_backup.py）
  - 删除5个一次性脚本（install_deps、setup等）
  - 删除2个代码修改脚本（enhance、integrate）

---

## v0.1.8 (2026-04-13)

### 新增功能
- ✨ MCP分析增强：静态注释提取与集成
  - 静态分析时提取页面注释和组件注释
  - 新增 `page_comments` 和 `component_comments` 字段
  - MCP分析时将注释作为LLM上下文，生成更准确的页面描述
  - 页面描述字数从20-50字提升到100-200字

### 优化改进
- 🔧 组件关联准确性提升
  - 静态分析页面文件，提取import的组件列表
  - 新增 `imported_components` 字段存储组件引用
  - 页面树API返回组件数量，前端正确显示
  - 修复MCP分析结果保存到数据库的字段映射问题

- 🎨 页面描述质量优化
  - LLM Prompt增强，要求包含功能、交互、组件说明
  - 提供详细描述示例，引导生成100-200字介绍
  - 支持结合开发者注释理解页面功能

### 问题修复
- 🐛 修复组件数量显示为0的问题
  - 递归遍历所有页面建立双向关联
  - API响应补充components字段
  - 修复detected_components字段名不匹配

- 🐛 修复数据库字段缺失问题
  - 添加imported_components、page_comments、component_comments字段
  - 完善数据库迁移脚本

### 技术细节
- 新增 `comment_extractor.py` 注释提取工具
- 支持JSDoc、HTML注释、单行注释等多种格式
- 组件注释按组件名索引，便于LLM理解
- MCP分析结果自动去重保存

---

## v0.1.7 (2026-04-13)

### 新增功能
- ✨ 后端服务自动重启脚本
  - 新增 `start_server.py` 一键启动后端服务
  - 自动检测并清理端口占用
  - 支持 Uvicorn 热更新监控

### 优化改进
- 🎨 默认UI状态优化
  - 最左侧导航栏默认收起（节省空间）
  - 项目详情页页面列表面板默认展开（提升可用性）
  - 页面树所有层级默认展开（快速浏览）

### 问题修复
- 🐛 修复数据库路径配置错误
  - 修正 `config.py` 中 workspace 路径计算逻辑
  - 确保正确连接到 `workspace/data.db`
- 🐛 修复页面描述未显示问题
  - API 响应中补充 `description` 字段
  - 支持递归查找嵌套页面树节点
  - 优化关联面板显示逻辑

---

## v0.1.6 (2026-04-12)
