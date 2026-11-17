# 02：从当前源码收到第一条回复

学习目标：确保运行的是 `lgx_local1` 的源码，建立独立学习实例，观察配置、模型调用和会话落盘。以下是后续实验步骤，本轮仅核对命令与源码，尚未安装或运行。

## 1. 准备源码环境

前提：Python 3.11+，可访问依赖仓库，以及一个可用的模型服务。下面命令用于当前 macOS/Linux 环境，从仓库根目录执行；已有可用的项目虚拟环境时复用它。

```bash
git branch --show-current
git rev-parse --short HEAD

# 首次需要时创建环境；可编辑安装让 Python 使用当前检出的源码
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/nanobot --version

# 检查实际导入位置，应该指向当前仓库的 nanobot/__init__.py
.venv/bin/python -c 'import nanobot; print(nanobot.__file__)'
```

版本应与当前 `pyproject.toml` 一致；版本号之外，导入路径也要正确。后续修改 Python 源码通常不需要重新安装，但已运行的进程需要重启。源码 WebUI/TUI 会按需使用 Bun 并构建/运行匹配当前检出的客户端，首次启动可能下载资源。

## 2. 初始化学习实例并配置模型

使用单独的实例 home 保存学习状态。`--home` 是全局参数，放在子命令前；后续命令始终带同一个 home。该目录已通过本目录 `.gitignore` 排除。

```bash
# 从仓库根目录执行；每个新终端重新设置这个变量
export LGX_NANOBOT_HOME="$PWD/tutorials_lgx/.runtime"
.venv/bin/nanobot --home "$LGX_NANOBOT_HOME" onboard --wizard
```

向导中选择你实际可用的 Provider、端点、凭据和模型。也可先运行不带 `--wizard` 的 `onboard`，再通过下方 WebUI 的 `Settings → Models` 配置。首次先使用一个明确选择的模型；需要工具实验时，确认该模型支持工具调用。

学习配置位于 `.runtime/config.json`，Agent 工作区默认为 `.runtime/workspace/`。重复初始化已有配置时注意向导/命令的提示，保留已配置值。

提交的配置示例只保存占位符；例如 Provider 的 `apiKey` 可写为 `${FINANCE_MODEL_API_KEY}`，并在启动进程的环境中提供该变量。`${VAR}` 是 nanobot 配置解析语法，变量缺失会报错，不支持 shell 的默认值写法。具体字段见 [Configuration](../docs/configuration.md#environment-variables-for-secrets)。

## 3. 检查本地配置，再发起请求

```bash
# status 检查本地配置和模型就绪状态，不发送模型请求
.venv/bin/nanobot --home "$LGX_NANOBOT_HOME" status

# 该命令会调用已配置模型；固定 session 便于后续查看历史
.venv/bin/nanobot --home "$LGX_NANOBOT_HOME" agent \
  --session lgx:first-run -m "用一句中文说明你的作用。"
```

完成标准：status 能识别学习实例的配置、工作区与所选模型，第二条命令收到正常助手回复。它证明基础模型链路可用；工具调用能力需要下一步实验单独验证。

## 4. 体验 WebUI，观察状态归属

```bash
# 使用独立端口，便于与已有默认实例同时运行
.venv/bin/nanobot --home "$LGX_NANOBOT_HOME" webui \
  --port 8766 --gateway-port 18791
```

浏览器入口为 [http://127.0.0.1:8766](http://127.0.0.1:8766)，健康端点为 [http://127.0.0.1:18791/health](http://127.0.0.1:18791/health)。健康响应检查进程/WebSocket 就绪情况，不验证模型连接。`--gateway-port 18791` 覆盖本次启动的健康端口，不写回配置中的 `gateway.port`。

在 WebUI 新建一条对话，使用相同模型发送一条消息。CLI 的 `lgx:first-run` 与 WebUI 新对话有不同的会话历史，但共享这个实例的 Agent 工作区与长期记忆。观察以下文件即可，不必手动编辑数据库：

| 路径 | 应观察到什么 |
| --- | --- |
| `.runtime/config.json` | Provider、模型与工作区设置；启动参数可覆盖配置端口 |
| `.runtime/workspace/` | `AGENTS.md`、`SOUL.md`、`USER.md` 等工作区资料 |
| `.runtime/sessions/<workspace-id>/sessions.sqlite3` | 会话持久化；普通聊天历史在 SQLite 中 |
| `.runtime/workspace/memory/` | 长期资料与归档日志；一条回复不保证形成新记忆 |

## 5. 下一步实验与记录

下一步用 `from nanobot import Nanobot` 和 `Nanobot.from_config(config_path=..., workspace=...)` 复用学习配置，执行一个 SDK 请求，再接入一个确定性的金融计算工具。使用 `async with` 管理生命周期，观察 `RunResult.content`、`tools_used`、`usage` 和 `stop_reason`。接口与完整样例见 [Python SDK](../docs/python-sdk.md)。

实验笔记记录：源码提交、Python/模型信息、关键配置、输入、实际输出、工具调用及失败原因。只复制脱敏的必要内容到笔记，运行状态留在 `.runtime/`。本章当前状态为“命令与接口已静态核对，模型/CLI/WebUI 实验待运行”。
