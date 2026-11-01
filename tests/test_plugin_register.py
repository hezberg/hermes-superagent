import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))


class FakeCtx:
    def __init__(self):
        self.tools = {}
        self.hooks = {}
        self.commands = {}
        self.cli_commands = {}
        self.skills = {}

    def register_tool(self, name=None, toolset=None, schema=None, handler=None, **kw):
        self.tools[name] = handler

    def register_hook(self, name, callback, **kw):
        self.hooks[name] = callback

    def register_command(self, name, handler, description="", **kw):
        self.commands[name] = handler

    def register_cli_command(self, name, help, setup_fn, handler_fn, **kw):
        self.cli_commands[name] = handler_fn

    def register_skill(self, name, path, **kw):
        self.skills[name] = path

    def dispatch_tool(self, name, args):
        raise RuntimeError("no board tools in test")


class TestPluginRegister(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HERMES_HOME"] = self.tmp.name
        import superagent

        self.plugin = superagent
        self.ctx = FakeCtx()
        self.plugin.register(self.ctx)

    def tearDown(self):
        self.tmp.cleanup()

    def test_registers_everything(self):
        self.assertIn("sa_status", self.ctx.tools)
        self.assertIn("tasks", self.ctx.commands)
        self.assertIn("stop", self.ctx.commands)
        self.assertIn("superagent", self.ctx.cli_commands)
        for hook in ("on_session_start", "on_session_end", "post_tool_call"):
            self.assertIn(hook, self.ctx.hooks)
        self.assertIn("router-superagent", self.ctx.skills)
        self.assertIn("worker-superagent", self.ctx.skills)

    def test_status_tool_returns_json(self):
        payload = json.loads(self.ctx.tools["sa_status"]({}))
        self.assertEqual(payload["plugin_version"], "0.11.1")
        self.assertEqual(payload["accept_mode"], "observe")
        self.assertFalse(payload["config_loaded"])  # nothing installed in tmp home
        self.assertIsNone(payload["board"])  # no kanban.db yet

    def test_hooks_never_raise_and_log_activity(self):
        self.ctx.hooks["on_session_start"]()
        self.ctx.hooks["post_tool_call"](tool_name="terminal")
        log = os.path.join(self.tmp.name, "superagent", "activity.jsonl")
        with open(log, encoding="utf-8") as fh:
            lines = fh.read().strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[1])["tool"], "terminal")


if __name__ == "__main__":
    unittest.main()
