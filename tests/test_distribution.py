"""Static host-package checks against current Claude and OpenAI plugin specs."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "distribution"
HOOK_EVENTS = {"SessionStart", "SessionEnd", "PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop"}


def frontmatter(path):
    lines = path.read_text().splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    return {l.split(":", 1)[0]: l.split(":", 1)[1].strip() for l in lines[1:end] if ":" in l and not l.startswith(" ")}


class PackageTests(unittest.TestCase):
    def check_skill(self, pkg):
        fm = frontmatter(pkg / "skills" / "ross" / "SKILL.md")
        self.assertEqual(fm["name"], "ross")
        self.assertTrue(0 < len(fm["description"]) <= 1024)
        self.assertTrue(set(fm) <= {"name", "description", "license", "compatibility", "metadata", "allowed-tools"})

    def check_hooks(self, pkg):
        hooks = json.loads((pkg / "hooks" / "hooks.json").read_text())["hooks"]
        self.assertTrue(set(hooks) <= HOOK_EVENTS)
        for entries in hooks.values():
            for e in entries:
                for h in e["hooks"]:
                    self.assertEqual(h["type"], "command")
                    self.assertRegex(h["command"], r'^python3 "\$\{CLAUDE_PLUGIN_ROOT\}/skills/ross/runtime/ross\.py" hook \w+$')
                    self.assertTrue((pkg / "skills/ross/runtime/ross.py").is_file())

    def test_claude_package(self):
        pkg = DIST / "claude" / "ross"
        m = json.loads((pkg / ".claude-plugin" / "plugin.json").read_text())
        self.assertRegex(m["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertEqual(m["license"], "Apache-2.0")
        self.check_skill(pkg)
        self.check_hooks(pkg)

    def test_openai_package(self):
        # developers.openai.com/plugins/build/plugins: plugin.json at root with name, version, description;
        # skills/<name>/SKILL.md; hooks/hooks.json; CLAUDE_PLUGIN_ROOT set for compatibility.
        pkg = DIST / "openai" / "ross"
        m = json.loads((pkg / "plugin.json").read_text())
        self.assertRegex(m["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertRegex(m["version"], r"^\d+\.\d+\.\d+")
        self.assertTrue(m["description"])
        self.check_skill(pkg)
        self.check_hooks(pkg)

    def test_kernel_is_small(self):
        body = (ROOT / "SKILL.md").read_text().split("---", 2)[2]
        self.assertLess(len(body) / 3.8, 800, "kernel body exceeds ~800 tokens")

    def test_kernel_references_resolve(self):
        text = (ROOT / "SKILL.md").read_text()
        for target in re.findall(r"\]\((references/[^)]+)\)", text):
            self.assertTrue((ROOT / target).is_file(), target)


if __name__ == "__main__":
    unittest.main()
