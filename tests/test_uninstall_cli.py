# -*- coding: utf-8 -*-
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cli  # noqa: E402


class UninstallCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.home = Path(self.temp_dir.name)

    def _args(self, **overrides):
        values = {
            "yes": True,
            "keep_data": False,
            "agents_only": False,
            "runtime_only": False,
            "skip_sidecar": True,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_uninstall_removes_runtime_cli_and_agent_registrations(self):
        entroflow = self.home / ".entroflow"
        entroflow.mkdir()
        (entroflow / "config.json").write_text("{}", encoding="utf-8")
        cli_shim = self.home / ".local" / "bin" / "entroflow"
        cli_shim.parent.mkdir(parents=True)
        cli_shim.write_text("#!/bin/bash\n", encoding="utf-8")
        windows_shim = self.home / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "entroflow.cmd"
        windows_shim.parent.mkdir(parents=True)
        windows_shim.write_text("@echo off\n", encoding="utf-8")

        cursor_config = self.home / ".cursor" / "mcp.json"
        cursor_config.parent.mkdir(parents=True)
        cursor_config.write_text(
            json.dumps({"mcpServers": {"entroflow": {"command": "python"}, "other": {"command": "x"}}}),
            encoding="utf-8",
        )
        codex_config = self.home / ".codex" / "config.toml"
        codex_config.parent.mkdir(parents=True)
        codex_config.write_text(
            "setting = true\n\n[mcp_servers.entroflow]\ncommand = \"python\"\nargs = [\"server.py\"]\n\n[other]\nvalue = 1\n",
            encoding="utf-8",
        )
        openclaw_agents = self.home / ".openclaw" / "AGENTS.md"
        openclaw_agents.parent.mkdir(parents=True)
        openclaw_agents.write_text(
            "before\n<!-- ENTROFLOW START -->\nremove me\n<!-- ENTROFLOW END -->\nafter\n",
            encoding="utf-8",
        )
        skill_dir = self.home / ".openclaw" / "skills" / "entroflow"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("skill", encoding="utf-8")

        with patch.object(cli.Path, "home", return_value=self.home):
            rc = cli.cmd_uninstall(self._args())

        self.assertEqual(rc, 0)
        self.assertFalse(entroflow.exists())
        self.assertFalse(cli_shim.exists())
        self.assertFalse(windows_shim.exists())
        self.assertFalse(skill_dir.exists())
        cursor_data = json.loads(cursor_config.read_text(encoding="utf-8"))
        self.assertNotIn("entroflow", cursor_data["mcpServers"])
        self.assertIn("other", cursor_data["mcpServers"])
        self.assertNotIn("mcp_servers.entroflow", codex_config.read_text(encoding="utf-8"))
        self.assertIn("[other]", codex_config.read_text(encoding="utf-8"))
        agents_content = openclaw_agents.read_text(encoding="utf-8")
        self.assertIn("before", agents_content)
        self.assertIn("after", agents_content)
        self.assertNotIn("ENTROFLOW START", agents_content)

    def test_keep_data_removes_code_but_keeps_user_data(self):
        entroflow = self.home / ".entroflow"
        (entroflow / "core").mkdir(parents=True)
        (entroflow / "runtime").mkdir()
        (entroflow / "assets").mkdir()
        (entroflow / "config.json").write_text("{}", encoding="utf-8")
        (entroflow / "cli.py").write_text("print('x')", encoding="utf-8")
        (entroflow / ".venv").mkdir()

        with patch.object(cli.Path, "home", return_value=self.home):
            rc = cli.cmd_uninstall(self._args(keep_data=True))

        self.assertEqual(rc, 0)
        self.assertTrue((entroflow / "config.json").exists())
        self.assertTrue((entroflow / "runtime").exists())
        self.assertTrue((entroflow / "assets").exists())
        self.assertFalse((entroflow / "cli.py").exists())
        self.assertFalse((entroflow / "core").exists())
        self.assertFalse((entroflow / ".venv").exists())

    def test_uninstall_removes_openclaw_sidecar_data_by_default(self):
        sidecar_data = self.home / ".openclaw" / "entroflow"
        (sidecar_data / "runtime").mkdir(parents=True)
        (sidecar_data / "runtime" / "mihome_auth.json").write_text("{}", encoding="utf-8")

        with (
            patch.object(cli.Path, "home", return_value=self.home),
            patch.object(cli, "_run_command", return_value=(0, "removed")),
        ):
            rc = cli.cmd_uninstall(self._args(skip_sidecar=False))

        self.assertEqual(rc, 0)
        self.assertFalse(sidecar_data.exists())

    def test_keep_data_preserves_openclaw_sidecar_data(self):
        sidecar_data = self.home / ".openclaw" / "entroflow"
        (sidecar_data / "runtime").mkdir(parents=True)
        (sidecar_data / "runtime" / "mihome_auth.json").write_text("{}", encoding="utf-8")

        with (
            patch.object(cli.Path, "home", return_value=self.home),
            patch.object(cli, "_run_command", return_value=(0, "removed")),
        ):
            rc = cli.cmd_uninstall(self._args(skip_sidecar=False, keep_data=True))

        self.assertEqual(rc, 0)
        self.assertTrue((sidecar_data / "runtime" / "mihome_auth.json").exists())

    def test_non_interactive_uninstall_requires_yes(self):
        class NonInteractive:
            def isatty(self):
                return False

        with patch.object(sys, "stdin", NonInteractive()):
            rc = cli.cmd_uninstall(self._args(yes=False))

        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
