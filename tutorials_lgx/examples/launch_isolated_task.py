"""每次使用新的 nanobot 实例；用法见 ../09_独立定时任务与状态隔离.md。

依赖当前源码的可编辑安装。init/--prepare-only 不启动服务或调用模型。
此文件只准备实例、调用原生 CLI；Agent 执行和权限仍由 Python Gateway 负责。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from contextlib import suppress
from datetime import datetime, timezone
from importlib.metadata import entry_points
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

import nanobot
from nanobot.config.schema import Config

RUNTIME = Path(__file__).resolve().parents[1] / ".runtime"
ROLE_FILES = ("AGENTS.md", "SOUL.md", "USER.md")
TASK_RULES = """

## 本次独立任务

只依据本次输入、input/ 内的数据和固定规则完成任务。报告放在 output/，注明数据时点、来源、单位和计算口径；信息不足时明确说明。不要创建定时任务、后台监控或自行安装技能。不要将本次结论写成用户长期偏好，也不要搜索其他任务目录。需要精确计算时使用已授权的计算工具；没有工具时说明限制，不伪造工具执行结果。
"""


def check_config_environment() -> None:
    """拒绝 BaseSettings 深合并额外配置；普通公司 Key 环境变量仍可引用。"""
    roots = {"agents", "channels", "transcription", "providers", "network", "gateway", "tools"}
    blocked = []
    for name in os.environ:
        normalized = name.lower()
        root = normalized.removeprefix("nanobot_").split("__", 1)[0]
        if (normalized.startswith("nanobot_") and root in roots
                or normalized.split("__", 1)[0] in {"modelpresets", "model_presets"}):
            blocked.append(name)
    if blocked:
        raise ValueError("请先取消这些配置覆盖环境变量，再运行独立任务：" + ", ".join(sorted(blocked)))


def read_config(path: Path) -> Config:
    """保留 ${VAR} 引用；错误只报告字段位置，避免输出凭据。"""
    check_config_environment()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("配置的顶层必须是 JSON 对象。")
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        locations = [".".join(map(str, item["loc"])) for item in exc.errors()]
        raise ValueError("配置字段无效：" + ", ".join(locations)) from None


def write_json(path: Path, value: dict) -> None:
    # home 为 0700，配置为 0600；原始 Key 只保存在 Git 忽略的实验区。
    with path.open("x", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def model_seed(source: Config) -> dict:
    """只继承当前生效模型与其连接，丢弃其他账号、通道和运行状态。"""
    preset = source.resolve_preset().model_copy(deep=True)
    provider_name = source.get_provider_name(preset=preset)
    connection = source.get_provider(preset=preset)
    if not provider_name or connection is None:
        raise ValueError("当前配置未能确定模型连接，请先完成公司 API 配置。")
    preset.provider = provider_name  # 固定路由，避免 Auto 选到其他服务。
    name = source.agents.defaults.model_preset or "task"
    if name == "default":
        name = "task"
    return {
        "agents": {"defaults": {
            "modelPreset": name,
            "timezone": source.agents.defaults.timezone,
            "timezoneMode": "manual",
            "maxToolIterations": source.agents.defaults.max_tool_iterations,
            "maxToolResultChars": source.agents.defaults.max_tool_result_chars,
        }},
        "modelPresets": {name: preset.model_dump(by_alias=True, exclude_none=True)},
        "providers": {provider_name: connection.model_dump(by_alias=True, exclude_none=True)},
        "network": source.network.model_dump(by_alias=True, exclude_none=True),
    }


def init_template(source_path: Path, template: Path) -> None:
    seed = model_seed(read_config(source_path))
    template.mkdir(parents=True, mode=0o700, exist_ok=False)
    workspace = template / "workspace"
    workspace.mkdir(mode=0o700)
    (workspace / "skills").mkdir()
    # 从内置静态模板开始，不继承学习实例中可能被 Dream 改过的身份/资料。
    for name in ROLE_FILES:
        content = files("nanobot.templates").joinpath(name).read_text(encoding="utf-8")
        if name == "AGENTS.md":
            content += TASK_RULES
        (workspace / name).write_text(content, encoding="utf-8")
    write_json(template / "config.json", seed)
    print(f"固定模板：{template}")
    print("可修改模板 workspace/ 下的角色文件，skills/ 仅放审核过的固定技能。")


def copy_fixed_tree(source: Path, destination: Path) -> None:
    """实际复制本次数据/技能；拒绝指向旧实验目录的符号链接。"""
    paths = [source, *source.rglob("*")]
    for path in paths:
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError(f"复制源须为普通文件或目录，不支持链接/特殊文件：{path}")
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copyfile(source, destination)


def prepare_task(
    template: Path, runs: Path, mode: str, *, message: str | None = None,
    input_path: Path | None = None, allow_shell: bool = False,
    port: int = 8767, gateway_port: int = 18793,
) -> tuple[Path, str]:
    seed = model_seed(read_config(template / "config.json"))
    if allow_shell and (sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").exists()):
        raise ValueError("--allow-shell 仅支持有 sandbox-exec 的 macOS，不会降级为无沙箱。")
    plugins = list(entry_points(group="nanobot.tools"))
    if plugins:
        raise ValueError("此基线不加载第三方工具插件，请使用无 nanobot.tools 插件的环境。")
    run_id = uuid4().hex
    home = runs.resolve() / run_id
    home.mkdir(parents=True, mode=0o700, exist_ok=False)
    workspace = home / "workspace"
    workspace.mkdir(mode=0o700)
    for name in ROLE_FILES:
        copy_fixed_tree(template / "workspace" / name, workspace / name)
    skills = template / "workspace" / "skills"
    if skills.exists():
        copy_fixed_tree(skills, workspace / "skills")
    if input_path is not None:
        if input_path.is_dir():
            copy_fixed_tree(input_path, workspace / "input")
        else:
            (workspace / "input").mkdir()
            copy_fixed_tree(input_path, workspace / "input" / input_path.name)
    else:
        (workspace / "input").mkdir()
    (workspace / "output").mkdir()
    seed["agents"]["defaults"].update({
        "workspace": str(workspace), "idleCompactAfterMinutes": 0,
        "dream": {"enabled": False}, "fallbackModels": [],
    })
    seed["gateway"] = {
        "host": "127.0.0.1", "port": gateway_port, "heartbeat": {"enabled": False},
    }
    seed["channels"] = {}
    if mode == "webui":
        seed["channels"]["websocket"] = {
            "enabled": True, "host": "127.0.0.1", "port": port,
            "tokenIssueSecret": secrets.token_urlsafe(32), "websocketRequiresToken": True,
        }
    seed["transcription"] = {"enabled": False}
    seed["tools"] = {
        "restrictToWorkspace": True,
        "file": {"enable": True}, "web": {"enable": False},
        "exec": {
            "enable": allow_shell, "sandbox": "seatbelt" if allow_shell else "",
            "pathPrepend": str(Path(sys.prefix) / "bin") if allow_shell else "",
            "sandboxRoBinds": [str(Path(sys.prefix).resolve())] if allow_shell else [],
            "sandboxRwBinds": [], "allowedEnvKeys": [],
        },
        "my": {"enable": False, "allowSet": False}, "cliApps": {"enable": False},
        "imageGeneration": {"enabled": False}, "mcpServers": {}, "ssrfWhitelist": [],
        "webuiAllowLocalServiceAccess": False, "webuiAllowRemotePackageInstall": False,
    }
    Config.model_validate(seed)  # 保存前确认字段与当前源码匹配，不调用模型。
    write_json(home / "config.json", seed)
    hashes = {
        str(path.relative_to(workspace)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in workspace.rglob("*") if path.is_file()
    }
    session = f"lgx:task:{run_id}"
    write_json(home / "task.json", {
        "run_id": run_id, "session_key": session, "mode": mode,
        "created_at": datetime.now(timezone.utc).isoformat(), "nanobot_version": nanobot.__version__,
        "workspace": str(workspace), "message": message, "seed_sha256": hashes,
        "model": next(iter(seed["modelPresets"].values()))["model"],
        "allow_shell": allow_shell,
    })
    print(f"本次 home：{home}")
    print(f"本次输出目录：{workspace / 'output'}")
    return home, session


def cli_command(home: Path, session: str, message: str) -> list[str]:
    return [sys.executable, "-m", "nanobot", "--home", str(home), "agent",
            "--config", str(home / "config.json"), "--workspace", str(home / "workspace"),
            "--session", session, "-m", message]


def check_ports(port: int, gateway_port: int) -> None:
    if port == gateway_port or any(not 1 <= item <= 65535 for item in (port, gateway_port)):
        raise ValueError("两个端口必须不同，且位于 1–65535。")
    for item in (port, gateway_port):
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", item))
        except OSError:
            raise ValueError(f"端口 {item} 不可用；换端口或先停止其所属服务。") from None


def wait_for_gateway(child: subprocess.Popen, home: Path, gateway_port: int):
    # 这里使用当前源码的内部生命周期 API，核对进程身份而非仅探测端口。
    from nanobot.gateway.runtime import GatewayInstance, GatewayRuntime
    from nanobot.installation_lock import installation_state_dir
    from nanobot.update_profiles import ProfileReceipt
    from nanobot.utils.atomic_file import read_atomic_bytes

    instance = GatewayInstance.resolve(config_path=home / "config.json", workspace=str(home / "workspace"))
    runtime = GatewayRuntime(paths=instance.paths)
    state_path = str(instance.paths.state_path.resolve())
    profile_id = hashlib.sha256(os.fsencode(state_path)).hexdigest()
    receipt_path = installation_state_dir(sys.prefix) / "profiles" / f"{profile_id}.json"
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise ValueError(f"独立 Gateway 启动失败；查看 {home / 'gateway.log'}")
        try:
            payload = read_atomic_bytes(receipt_path)
            receipt = ProfileReceipt.model_validate_json(payload)
        except FileNotFoundError:
            time.sleep(0.2)
            continue
        matches = (
            receipt.active and receipt.pid == child.pid and receipt.state_path == state_path
            and receipt.config == str(home / "config.json")
            and receipt.workspace == str(home / "workspace")
            and receipt.home == str(home) and receipt.port == gateway_port
        )
        if matches and runtime.verify_ready(receipt.health_identity, maintenance=False):
            if read_atomic_bytes(receipt_path) == payload and child.poll() is None:
                return runtime
        time.sleep(0.2)
    raise ValueError(f"独立 Gateway 未在 90 秒内就绪；查看 {home / 'gateway.log'}")


def stop_child(child: subprocess.Popen, *, stop_signal: int = signal.SIGTERM) -> None:
    """只清理本启动器创建的进程组，不停止其他学习实例。"""
    if child.poll() is None:
        with suppress(ProcessLookupError):
            child.send_signal(stop_signal)
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
    child.wait()


def request_stop(_signum, _frame) -> None:
    raise KeyboardInterrupt


def run_cli(home: Path, session: str, message: str) -> int:
    previous_term = signal.signal(signal.SIGTERM, request_stop)
    child = None
    try:
        child = subprocess.Popen(cli_command(home, session, message), start_new_session=True)
        return child.wait()
    finally:
        previous_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            if child is not None:
                # one-shot CLI 由 asyncio.run 处理 SIGINT，给工具清理留出时间。
                stop_child(child, stop_signal=signal.SIGINT)
        finally:
            signal.signal(signal.SIGINT, previous_int)
            signal.signal(signal.SIGTERM, previous_term)


def run_webui(home: Path, port: int, gateway_port: int) -> int:
    check_ports(port, gateway_port)  # 准备后重查；真实 bind 仍负责处理竞争。
    selectors = ["--config", str(home / "config.json"), "--workspace", str(home / "workspace")]
    prefix = [sys.executable, "-m", "nanobot", "--home", str(home)]
    print(f"页面：http://127.0.0.1:{port}；本次任务结束后按 Ctrl+C 停止。")
    previous_term = signal.signal(signal.SIGTERM, request_stop)
    child = None
    try:
        with (home / "gateway.log").open("x", encoding="utf-8") as log:
            os.chmod(home / "gateway.log", 0o600)
            child = subprocess.Popen(
                [*prefix, "gateway", "--foreground", *selectors, "--port", str(gateway_port)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                cwd=home / "workspace", start_new_session=True,
            )
            wait_for_gateway(child, home, gateway_port)
            result = subprocess.run(
                [*prefix, "webui", *selectors, "--yes", "--no-dock", "--port", str(port),
                 "--gateway-port", str(gateway_port)], check=False,
            )
            # 某些安装模式会自动 detach；本启动器仍持有 Gateway 直到 Ctrl+C。
            if result.returncode != 0:
                return result.returncode
            if child.poll() is None:
                print("页面启动器已返回；本次 Gateway 仍运行，按 Ctrl+C 结束。")
            return child.wait()
    finally:
        previous_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            if child is not None:
                stop_child(child)
        finally:
            signal.signal(signal.SIGINT, previous_int)
            signal.signal(signal.SIGTERM, previous_term)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    init = commands.add_parser("init", help="一次性生成固定模板，不覆盖已有模板")
    init.add_argument("--source", type=Path, default=RUNTIME / "config.json")
    init.add_argument("--template", type=Path, default=RUNTIME / "task_template")
    for mode in ("cli", "webui"):
        command = commands.add_parser(mode, help="新建本次实例并启动")
        command.add_argument("--template", type=Path, default=RUNTIME / "task_template")
        command.add_argument("--runs-dir", type=Path, default=RUNTIME / "task_runs")
        command.add_argument("--input", type=Path, help="仅复制本次数据文件或目录")
        command.add_argument("--allow-shell", action="store_true", help="开启 macOS Seatbelt shell，允许网络")
        command.add_argument("--prepare-only", action="store_true", help="只准备文件，不启动或调用模型")
        if mode == "cli":
            command.add_argument("-m", "--message", required=True, help="本次模板化任务输入")
        else:
            command.add_argument("--port", type=int, default=8767)
            command.add_argument("--gateway-port", type=int, default=18793)
    args = parser.parse_args()
    try:
        if args.mode == "init":
            init_template(args.source, args.template)
            return 0
        if args.mode == "webui":
            check_ports(args.port, args.gateway_port)
        message = getattr(args, "message", None)
        if args.mode == "cli" and not message.strip():
            raise ValueError("CLI 任务输入不能为空。")
        home, session = prepare_task(
            args.template, args.runs_dir, args.mode, message=message, input_path=args.input,
            allow_shell=args.allow_shell, port=getattr(args, "port", 8767),
            gateway_port=getattr(args, "gateway_port", 18793),
        )
        if args.prepare_only:
            print("仅准备完成，未启动服务或调用模型。正式任务请重新执行不带 --prepare-only 的命令。")
            return 0
        if args.mode == "cli":
            return run_cli(home, session, message)
        return run_webui(home, args.port, args.gateway_port)
    except KeyboardInterrupt:
        print("\n本次启动器已退出，任务目录与记录保留。")
        return 130
    except (OSError, ValueError) as exc:
        # JSON/Pydantic 异常可能包含原始配置，禁止直接打印它们。
        if isinstance(exc, ValidationError):
            detail = "配置或启动身份数据不符合当前版本，请检查文件与运行环境。"
        elif isinstance(exc, json.JSONDecodeError):
            detail = "JSON 格式错误，请检查配置文件。"
        else:
            detail = str(exc)
        print(f"准备或启动失败：{detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
