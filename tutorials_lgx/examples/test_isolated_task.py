"""独立任务启动器的配置、复制与生命周期合同；不启动服务或请求模型。

从仓库根目录运行：python tutorials_lgx/examples/test_isolated_task.py -v
仅使用标准库 unittest，无需额外安装测试依赖。
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import signal
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


class IndependentTaskTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "lgx_isolated_task_launcher", Path(__file__).with_name("launch_isolated_task.py"),
        )
        self.launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.launcher)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        plugin_patch = patch.object(self.launcher, "entry_points", return_value=[])
        plugin_patch.start()
        self.addCleanup(plugin_patch.stop)
        self.source = self.root / "source.json"
        old_workspace = self.root / "old_workspace"
        old_workspace.mkdir()
        for name in (*self.launcher.ROLE_FILES, "MEMORY.md", "HISTORY.md"):
            (old_workspace / name).write_text("旧任务内容", encoding="utf-8")
        self.source.write_text(json.dumps({
            "agents": {"defaults": {
                "workspace": str(old_workspace), "modelPreset": "company",
                "timezone": "Asia/Shanghai", "maxToolIterations": 12,
            }},
            "modelPresets": {"company": {
                "model": "company-model", "provider": "company", "temperature": 0.2,
                "maxTokens": 4096, "contextWindowTokens": 32000,
            }},
            "providers": {
                "company": {"apiKey": "${LGX_COMPANY_API_KEY}", "apiBase": "https://example.invalid/v1"},
                "openai": {"apiKey": "unrelated-account-secret"},
            },
            "channels": {"websocket": {"enabled": True, "tokenIssueSecret": "old-token-secret"}},
            "tools": {"restrictToWorkspace": False, "cliApps": {"enable": True}},
        }), encoding="utf-8")
        self.template = self.root / "template"
        with redirect_stdout(io.StringIO()):
            self.launcher.init_template(self.source, self.template)

    @staticmethod
    def load_json(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def prepare(self, mode="cli", **kwargs):
        with redirect_stdout(io.StringIO()):
            return self.launcher.prepare_task(self.template, self.root / "runs", mode, **kwargs)

    def test_init_uses_clean_roles_active_connection_and_never_overwrites(self):
        for name in self.launcher.ROLE_FILES:
            expected = files("nanobot.templates").joinpath(name).read_text(encoding="utf-8")
            if name == "AGENTS.md":
                expected += self.launcher.TASK_RULES
            self.assertEqual((self.template / "workspace" / name).read_text(encoding="utf-8"), expected)
        seed = self.load_json(self.template / "config.json")
        self.assertEqual(set(seed), {"agents", "modelPresets", "providers", "network"})
        self.assertEqual(set(seed["providers"]), {"company"})
        self.assertEqual(seed["providers"]["company"]["apiKey"], "${LGX_COMPANY_API_KEY}")
        role = self.template / "workspace" / "SOUL.md"
        role.write_text("人工维护的固定角色", encoding="utf-8")
        original_config = (self.template / "config.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.launcher.init_template(self.source, self.template)
        self.assertEqual(role.read_text(encoding="utf-8"), "人工维护的固定角色")
        self.assertEqual((self.template / "config.json").read_bytes(), original_config)

    def test_each_run_has_fresh_state_and_independent_whitelisted_seed_and_inputs(self):
        workspace = self.template / "workspace"
        (workspace / "USER.md").write_text("固定报告规范", encoding="utf-8")
        (workspace / "MEMORY.md").write_text("旧偏好", encoding="utf-8")
        for name in ("memory", ".nanobot", "cron"):
            (workspace / name).mkdir()
            (workspace / name / "old-state.json").write_text("{}", encoding="utf-8")
        skill = workspace / "skills" / "calculation"
        skill.mkdir()
        (skill / "SKILL.md").write_text("固定计算技能", encoding="utf-8")
        inputs = self.root / "inputs"
        inputs.mkdir()
        (inputs / "data.csv").write_text("value\n123\n", encoding="utf-8")
        first, first_session = self.prepare(message="任务输入", input_path=inputs)
        second, second_session = self.prepare(message="任务输入", input_path=inputs)
        self.assertNotEqual(first, second)
        self.assertNotEqual(first_session, second_session)
        for home, session in ((first, first_session), (second, second_session)):
            task_workspace = home / "workspace"
            config = self.load_json(home / "config.json")
            manifest = self.load_json(home / "task.json")
            self.assertEqual(config["agents"]["defaults"]["workspace"], str(task_workspace))
            self.assertEqual(config["providers"]["company"]["apiKey"], "${LGX_COMPANY_API_KEY}")
            self.assertEqual(config["modelPresets"]["company"]["temperature"], 0.2)
            self.assertEqual(manifest["session_key"], session)
            self.assertEqual(manifest["message"], "任务输入")
            self.assertEqual(set(path.name for path in task_workspace.iterdir()), {
                *self.launcher.ROLE_FILES, "skills", "input", "output",
            })
            self.assertEqual((task_workspace / "USER.md").read_text(encoding="utf-8"), "固定报告规范")
            self.assertTrue((task_workspace / "skills" / "calculation" / "SKILL.md").is_file())
        (inputs / "data.csv").write_text("source changed", encoding="utf-8")
        (first / "workspace" / "input" / "data.csv").write_text("first changed", encoding="utf-8")
        self.assertEqual((second / "workspace" / "input" / "data.csv").read_text(encoding="utf-8"), "value\n123\n")

    def test_input_copy_rejects_symlink_to_other_task(self):
        other = self.root / "other-task.txt"
        other.write_text("其他任务数据", encoding="utf-8")
        inputs = self.root / "inputs"
        inputs.mkdir()
        (inputs / "linked.txt").symlink_to(other)
        with self.assertRaisesRegex(ValueError, "不支持链接"):
            self.prepare(message="任务", input_path=inputs)

    def test_default_capabilities_background_learning_and_webui_auth_are_isolated(self):
        home, _ = self.prepare(message="任务")
        config = self.launcher.read_config(home / "config.json")
        self.assertEqual(config.agents.defaults.session_ttl_minutes, 0)
        self.assertFalse(config.agents.defaults.dream.enabled)
        self.assertFalse(config.gateway.heartbeat.enabled)
        self.assertEqual(config.agents.defaults.fallback_models, [])
        self.assertTrue(config.tools.restrict_to_workspace)
        self.assertTrue(config.tools.file.enable)
        for enabled in (
            config.tools.exec.enable, config.tools.web.enable, config.tools.cli_apps.enable,
            config.tools.my.enable, config.tools.my.allow_set, config.tools.image_generation.enabled,
            config.tools.webui_allow_local_service_access, config.tools.webui_allow_remote_package_install,
            config.transcription.enabled,
        ):
            self.assertFalse(enabled)
        self.assertEqual(config.tools.mcp_servers, {})
        self.assertEqual(self.load_json(home / "config.json")["channels"], {})
        first, _ = self.prepare("webui")
        second, _ = self.prepare("webui")
        first_channel = self.load_json(first / "config.json")["channels"]["websocket"]
        second_channel = self.load_json(second / "config.json")["channels"]["websocket"]
        self.assertTrue(first_channel["enabled"])
        self.assertTrue(first_channel["websocketRequiresToken"])
        self.assertEqual(first_channel["host"], "127.0.0.1")
        self.assertNotEqual(first_channel["tokenIssueSecret"], second_channel["tokenIssueSecret"])

    def test_shell_requires_macos_sandbox_with_readonly_python_environment(self):
        original_exists = Path.exists

        def exists(path):
            return True if path == Path("/usr/bin/sandbox-exec") else original_exists(path)

        with patch.object(self.launcher.sys, "platform", "darwin"), patch.object(Path, "exists", exists):
            home, _ = self.prepare(message="计算", allow_shell=True)
        execution = self.launcher.read_config(home / "config.json").tools.exec
        self.assertTrue(execution.enable)
        self.assertEqual(execution.sandbox, "seatbelt")
        self.assertEqual(execution.sandbox_ro_binds, [str(Path(self.launcher.sys.prefix).resolve())])
        self.assertEqual(execution.sandbox_rw_binds, [])
        self.assertEqual(execution.allowed_env_keys, [])
        with patch.object(self.launcher.sys, "platform", "linux"):
            with self.assertRaisesRegex(ValueError, "不会降级"):
                self.prepare(message="计算", allow_shell=True)

    def test_ports_reject_invalid_pairs_and_occupied_endpoint(self):
        for ports in ((8767, 8767), (0, 18793), (8767, 65536)):
            with self.subTest(ports=ports), self.assertRaisesRegex(ValueError, "端口必须不同"):
                self.launcher.check_ports(*ports)
        # Codex 沙箱不允许 bind，模拟操作系统报告的真实端口占用错误。
        with patch.object(self.launcher.socket, "socket") as socket_factory:
            socket_factory.return_value.__enter__.return_value.bind.side_effect = OSError(48, "Address already in use")
            with self.assertRaisesRegex(ValueError, "端口 8767 不可用"):
                self.launcher.check_ports(8767, 18793)

    def test_cli_selects_all_task_state_and_rejects_blank_message(self):
        home = self.root / "run"
        self.assertEqual(self.launcher.cli_command(home, "lgx:task:123", "固定输入"), [
            self.launcher.sys.executable, "-m", "nanobot", "--home", str(home), "agent",
            "--config", str(home / "config.json"), "--workspace", str(home / "workspace"),
            "--session", "lgx:task:123", "-m", "固定输入",
        ])
        argv = ["launch_isolated_task.py", "cli", "--template", str(self.template),
                "--runs-dir", str(self.root / "blank_runs"), "-m", "   ", "--prepare-only"]
        with patch.object(self.launcher.sys, "argv", argv), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(self.launcher.main(), 1)
        self.assertFalse((self.root / "blank_runs").exists())

    def test_configuration_environment_overrides_are_rejected_without_exposing_secrets(self):
        for variable in ("NANOBOT_AGENTS__DEFAULTS__WORKSPACE", "NANOBOT_TOOLS__EXEC__ENABLE", "MODEL_PRESETS", "modelPresets"):
            with self.subTest(variable=variable), patch.dict(os.environ, {variable: "sensitive-secret"}):
                with self.assertRaises(ValueError) as raised:
                    self.launcher.read_config(self.source)
                self.assertNotIn("sensitive-secret", str(raised.exception))
        with patch.dict(os.environ, {"LGX_COMPANY_API_KEY": "sensitive-secret"}):
            config = self.launcher.read_config(self.source)
            self.assertEqual(config.get_provider().api_key, "${LGX_COMPANY_API_KEY}")

    def test_webui_waits_for_owned_gateway_and_cleans_it_if_startup_fails(self):
        for ready in (True, False):
            with self.subTest(ready=ready):
                home = self.root / str(ready)
                (home / "workspace").mkdir(parents=True)
                events = []

                class Child:
                    pid = 12345

                    def poll(self):
                        return None

                    def send_signal(self, stop_signal):
                        self_outer.assertEqual(stop_signal, signal.SIGTERM)
                        events.append("signal owned child")

                    def wait(self, timeout=None):
                        events.append("wait owned child")
                        return 0

                self_outer = self
                child = Child()

                def popen(argv, **kwargs):
                    self.assertEqual(argv, [
                        self.launcher.sys.executable, "-m", "nanobot", "--home", str(home), "gateway",
                        "--foreground", "--config", str(home / "config.json"),
                        "--workspace", str(home / "workspace"), "--port", "18793",
                    ])
                    self.assertTrue(kwargs["start_new_session"])
                    events.append("start owned gateway")
                    return child

                def wait_for_gateway(actual_child, actual_home, gateway_port):
                    self.assertEqual((actual_child, actual_home, gateway_port), (child, home, 18793))
                    events.append("verify identity and ready")
                    if not ready:
                        raise ValueError("Gateway 启动失败")

                def run(argv, **kwargs):
                    self.assertIn("webui", argv)
                    self.assertEqual(events[-1], "verify identity and ready")
                    events.append("open webui")
                    return SimpleNamespace(returncode=2)

                with patch.object(self.launcher, "check_ports"), \
                        patch.object(self.launcher.subprocess, "Popen", popen), \
                        patch.object(self.launcher, "wait_for_gateway", wait_for_gateway), \
                        patch.object(self.launcher.subprocess, "run", run), \
                        patch.object(self.launcher.os, "killpg") as killpg, redirect_stdout(io.StringIO()):
                    if ready:
                        self.assertEqual(self.launcher.run_webui(home, 8767, 18793), 2)
                        expected = ["start owned gateway", "verify identity and ready", "open webui"]
                    else:
                        with self.assertRaisesRegex(ValueError, "Gateway 启动失败"):
                            self.launcher.run_webui(home, 8767, 18793)
                        expected = ["start owned gateway", "verify identity and ready"]
                    killpg.assert_not_called()
                self.assertEqual(events, [*expected, "signal owned child", "wait owned child", "wait owned child"])

    def test_cli_interrupt_cleans_owned_child_with_sigint(self):
        child = SimpleNamespace(
            poll=lambda: None,
            send_signal=lambda selected: self.assertEqual(selected, signal.SIGINT),
        )
        with patch.object(self.launcher.subprocess, "Popen", return_value=child) as popen:
            with patch.object(child, "wait", create=True, side_effect=[KeyboardInterrupt, 0, 0]):
                with self.assertRaises(KeyboardInterrupt):
                    self.launcher.run_cli(self.root / "run", "lgx:task:123", "任务")
        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_gateway_readiness_requires_stable_receipt_for_owned_process(self):
        from nanobot.gateway.runtime import GatewayInstance, GatewayRuntime
        from nanobot.update_profiles import ProfileReceipt

        home, _ = self.prepare("webui")
        instance = GatewayInstance.resolve(config_path=home / "config.json", workspace=str(home / "workspace"))
        state_path = str(instance.paths.state_path.resolve())
        profile_id = self.launcher.hashlib.sha256(os.fsencode(state_path)).hexdigest()
        receipt = ProfileReceipt(
            id=profile_id, run_id="b" * 32, environment=self.launcher.sys.prefix,
            python=self.launcher.sys.executable, package=str(Path(self.launcher.nanobot.__file__).parent),
            version=self.launcher.nanobot.__version__, home=str(home), data_dir=str(home),
            config=str(home / "config.json"), workspace=str(home / "workspace"),
            state_path=state_path, log_path=str(home / "gateway.log"), port=18793,
            launch_mode="foreground", pid=12345, process_identity=None, active=True,
        )
        good = receipt.model_dump_json().encode()
        mismatches = {
            "home": str(self.root / "other_home"), "pid": 67890, "active": False,
            "config": str(self.root / "other_config.json"), "workspace": str(self.root / "other_workspace"),
            "state_path": str(self.root / "other_state.json"), "port": 18794,
        }
        scenarios = []
        for field, value in mismatches.items():
            bad = receipt.model_copy(update={field: value}).model_dump_json().encode()
            scenarios.append((field, [bad, good, good], [0, 1, 2], [None] * 3, [True], None))
        changed = receipt.model_copy(update={"pid": 67890}).model_dump_json().encode()
        scenarios.extend([
            ("receipt changes after health check", [good, changed], [0, 1, 91], [None], [True], "90 秒"),
            ("owned child exits after health check", [good, good], [0, 1, 2], [None, 1, 1], [True], "启动失败"),
            ("health not yet ready", [good, good, good], [0, 1, 2], [None] * 3, [False, True], None),
        ])
        for label, payloads, times, polls, readiness, error in scenarios:
            with self.subTest(scenario=label):
                child = SimpleNamespace(pid=12345, poll=Mock(side_effect=polls))
                with patch("nanobot.installation_lock.installation_state_dir", return_value=self.root / "installation"), \
                        patch("nanobot.utils.atomic_file.read_atomic_bytes", side_effect=payloads) as read_receipt, \
                        patch.object(GatewayRuntime, "verify_ready", side_effect=readiness) as verify_ready, \
                        patch.object(self.launcher.time, "monotonic", side_effect=times), \
                        patch.object(self.launcher.time, "sleep"):
                    if error:
                        with self.assertRaisesRegex(ValueError, error):
                            self.launcher.wait_for_gateway(child, home, 18793)
                    else:
                        runtime = self.launcher.wait_for_gateway(child, home, 18793)
                        self.assertIsInstance(runtime, GatewayRuntime)
                        self.assertEqual(runtime.paths, instance.paths)
                    self.assertEqual(read_receipt.call_count, len(payloads))
                    self.assertEqual(verify_ready.call_count, len(readiness))
                    for call in verify_ready.call_args_list:
                        self.assertEqual(call.args, (receipt.health_identity,))
                        self.assertEqual(call.kwargs, {"maintenance": False})
                    expected_path = self.root / "installation" / "profiles" / f"{profile_id}.json"
                    self.assertTrue(all(call.args == (expected_path,) for call in read_receipt.call_args_list))


if __name__ == "__main__":
    unittest.main()
