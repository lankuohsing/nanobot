# nanobot 学习入口

目标：快速掌握 nanobot 的执行链路、状态管理和扩展方式，再构建可验证的金融垂域 Agent。这组材料也用于新同事入门；操作教程可以独立阅读，源码地图供熟悉 Python、大模型和 Agent 基本概念的读者进一步定位实现。

首轮梳理日期：2026-11-17。源码基准：`lgx_local1`，提交 `966ed5e0bd335a2678d0acbca5fc2aa5d21dddf2`，`pyproject.toml` 版本 `0.4.1`。后续修改在此基准上累积，重要行为变化在对应笔记中记录。

日常实验直接查看 [常用命令速查](./05_常用命令速查.md)。

## 先读这几页

| 文件 | 内容 |
| --- | --- |
| [AGENTS.md](./AGENTS.md) | 后续笔记、示例代码、框架修改与验证准则 |
| [01_框架地图.md](./01_框架地图.md) | 执行链路、状态归属、扩展入口和源码/测试索引 |
| [02_首次运行.md](./02_首次运行.md) | 环境选择、源码安装、onboard、home/工作区、首次运行与 Git 忽略 |
| [03_公司模型接口配置.md](./03_公司模型接口配置.md) | 手动填写配置或使用环境变量接入公司接口；协议要求与请求排查 |
| [04_依赖检查与排障.md](./04_依赖检查与排障.md) | 安装输出、pip check、MLflow/Gradio 冲突案例与已验证的修复结果 |
| [05_常用命令速查.md](./05_常用命令速查.md) | 日常准备、WebUI 启停、CLI 实验与常用检查 |
| [06_工作区与会话存储.md](./06_工作区与会话存储.md) | 工作区文件与标识、问答保存位置、CLI 会话与网页侧栏的区别 |
| [07_上下文压缩与模型参数.md](./07_上下文压缩与模型参数.md) | 压缩触发与结果存储、输入/输出预算、模型预设参数与闲置配置 |

第一遍只需理解：`AgentLoop` 编排一个用户回合，`AgentRunner` 执行回合中的模型与工具循环；Session 保存对话，Memory 提供实例共享的长期上下文；金融能力从 Tool、Skill 或 MCP 接入。

## 新同事的第一轮练习

1. 按第 02 章选择并激活一个环境，完成可编辑安装；确认解释器、源码路径和版本正确，`pip check` 通过。遇到依赖冲突时查看第 04 章。
2. 按第 02 章初始化 `tutorials_lgx/.runtime/`，能够说明 home、Agent 工作区、项目工作区和会话数据库的区别。
3. 按第 03 章配置公司接口，先通过 status 的本地检查，再实际发送一条消息并收到回复；记录所用模型和结果。
4. 按第 02 章体验 WebUI；随后阅读第 01 章的执行链路、状态表与自测问题，再开始找源码。

命令默认从读者自己的仓库根目录执行。`py312` 和个人绝对路径属于作者本机示例；新同事使用自己的环境和路径，后续命令统一使用激活环境中的 `python`。运行或管理学习实例时带同一个 `--home`，查看帮助/版本与 pip 环境操作不需要它。接口、模型 ID 和凭据占位符须替换为公司实际提供的值。案例中的个人运行记录与教学步骤分开，不能当作自己的验收结果。

## 学习路线与进度

| 阶段 | 要回答的问题 | 完成标准 | 当前状态 |
| --- | --- | --- | --- |
| 0. 框架地图 | 一条请求经过哪些模块？状态归谁？ | 能解释执行链路并找到对应源码 | 已完成首轮文档与代码梳理 |
| 1. 首次运行 | 当前源码能否用指定模型回复？ | 独立实例完成一条 CLI 请求，再体验 WebUI | 已完成：用户确认 WebUI 问答成功，只读数据库检查确认 CLI 连接测试与网页问答已保存；实际工具调用待验证 |
| 2. SDK 与工具 | 如何从 Python 调用 Agent，并增加确定性能力？ | SDK 调用和一个金融计算工具有可核验结果 | 待开展 |
| 3. 上下文与检索 | Prompt、Skill、历史、长期记忆和业务知识如何配合？ | 能解释上下文来源；一次资料问答能定位原文证据 | 待开展 |
| 4. 金融原型 | 数据接入、计算和生成如何形成完整链路？ | 固定数据样本上回答准确、有来源、有数据时点 | 待开展 |
| 5. 评估与服务化 | 如何衡量质量、管理权限并持续运行？ | 小型评估集、工具失败处理和部署过程可复现 | 待开展 |

建议第一个金融原型选择“财报指标计算与解释”：固定公开或合成数据 → 工具计算 → Agent 解释 → 引用来源。它能同时验证框架接入和数字正确性，后续再添加公告检索或行情接口。具体业务场景尚待选择。

## 上游文档索引

| 学习目的 | 优先阅读 |
| --- | --- |
| 官方入门与本地启动 | [中文 0.4.1 快速开始](https://nanobot.wiki/cn/docs/0.4.1/getting-started/quick-start)、[仓库 Quick Start](../docs/quick-start.md) |
| 概览与文档导航 | [项目 README](../README.md)、[docs 索引](../docs/README.md)、[Concepts](../docs/concepts.md) |
| 当前架构与代码拥有者 | [Architecture](../docs/architecture.md)、[开发导航](../.agent/navigation.md)、[设计边界](../.agent/design.md) |
| SDK 集成 | [Python SDK](../docs/python-sdk.md) |
| 模型与配置 | [Provider Cookbook](../docs/provider-cookbook.md)、[Configuration](../docs/configuration.md)、[CLI Reference](../docs/cli-reference.md) |
| Memory、Skill 与 MCP | [Memory](../docs/memory.md)、[内置 Skills](../nanobot/skills/README.md)、[MCP 配置](../docs/guides/configure-mcp-tools.md) |
| 隔离实例、权限与部署 | [Multiple Instances](../docs/multiple-instances.md)、[安全指南](../docs/guides/secure-local-ai-agent.md)、[Deployment](../docs/deployment.md) |

官方版本化教程适合入门；仓库文档跟随当前源码，同一版本号也不保证教程覆盖当前分支的所有变化。遇到差异，核对源码和实际运行环境。WebUI/TUI 与 Gateway 的受支持组合使用相同版本。

## 快速定位与维护索引

```bash
# 从仓库根目录执行；先查文档，再查拥有该行为的代码
rg -n 'AgentLoop|AgentRunner|ContextBuilder' docs/architecture.md nanobot/agent
rg -n 'class Tool|class ToolLoader|class ToolRegistry' nanobot/agent/tools
rg -n 'SessionState|SqliteSessionStore|MemoryStore' nanobot/session nanobot/agent/memory.py
git diff --check
```

索引保持为可人工维护的 Markdown 链接：新增章节时更新本页，定位具体问题时使用 [01_框架地图.md](./01_框架地图.md) 的源码/测试表，再用 `rg` 查符号与调用方。

首轮梳理已核对入门文档、架构、配置/CLI 入口及核心执行与扩展实现。2026-11-18 用户确认完成安装与 onboard；只读检查确认 py312 的可编辑安装路径正确、pip check 通过，依赖版本见第 04 章。用户已修正接口基础地址并填写 Key，实际配置通过静态检查；后续完成 CLI 连接测试与 WebUI 问答，数据库中的保存结果见第 06 章。教程链接与命令语法已检查；实际工具调用仍待验证。
