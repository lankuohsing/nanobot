# nanobot 学习入口

目标：快速掌握 nanobot 的执行链路、状态管理和扩展方式，再构建可验证的金融垂域 Agent。默认读者懂大模型与 Agent 概念，直接从工程实现进入。

首轮梳理日期：2026-11-17。源码基准：`lgx_local1`，提交 `966ed5e0bd335a2678d0acbca5fc2aa5d21dddf2`，`pyproject.toml` 版本 `0.4.1`。后续修改在此基准上累积，重要行为变化在对应笔记中记录。

## 先读这几页

| 文件 | 内容 |
| --- | --- |
| [AGENTS.md](./AGENTS.md) | 后续笔记、示例代码、框架修改与验证准则 |
| [01_framework_map.md](./01_framework_map.md) | 执行链路、状态归属、扩展入口和源码/测试索引 |
| [02_first_run.md](./02_first_run.md) | 从当前源码启动独立学习实例的命令与观察点 |

第一遍只需理解：`AgentLoop` 编排一个用户回合，`AgentRunner` 执行回合中的模型与工具循环；Session 保存对话，Memory 提供实例共享的长期上下文；金融能力从 Tool、Skill 或 MCP 接入。

## 学习路线与进度

| 阶段 | 要回答的问题 | 完成标准 | 当前状态 |
| --- | --- | --- | --- |
| 0. 框架地图 | 一条请求经过哪些模块？状态归谁？ | 能解释执行链路并找到对应源码 | 已完成首轮文档与代码梳理 |
| 1. 首次运行 | 当前源码能否用指定模型回复？ | 独立实例完成一条 CLI 请求，再体验 WebUI | 命令已整理，尚未运行 |
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

索引保持为可人工维护的 Markdown 链接：新增章节时更新本页，定位具体问题时使用 [01_framework_map.md](./01_framework_map.md) 的源码/测试表，再用 `rg` 查符号与调用方。

本次验证范围：已核对入门文档、架构、配置/CLI 入口及核心执行与扩展实现；尚未安装项目依赖、配置模型或发起模型请求。运行实验的结果在后续章节单独记录。
