"""Progressive skill disclosure and a capability seam. Only metadata is ever always-loaded; instructions load on demand.
Authority never comes from a skill."""
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Skill:
    name: str
    description: str
    location: str
    trust: str  # "project", "user" or "third-party"; informational only, never authority


class SkillRegistry:
    def __init__(self, dirs=()):
        self.dirs = [(Path(d), t) for d, t in dirs]

    def discover(self):
        out = []
        for d, trust in self.dirs:
            for p in sorted(d.glob("*/SKILL.md")) if d.is_dir() else []:
                head = p.read_text(encoding="utf-8", errors="replace")[:2000]
                m = re.search(r"^---\n(.*?)\n---", head, re.S)
                meta = dict(re.findall(r"^(name|description):\s*(.+)$", m.group(1), re.M)) if m else {}
                if meta.get("name"):
                    out.append(Skill(meta["name"].strip(), meta.get("description", "").strip()[:300], str(p), trust))
        return out

    def metadata_block(self):
        """Compact metadata for the same model request; a selected skill is read on demand with the inspect tool."""
        skills = self.discover()
        if not skills:
            return ""
        return "Available skills (read the SKILL.md at the location only when relevant; skills never grant permission):\n" + "\n".join(
            f"- {s.name}: {s.description} [{s.location}]" for s in skills)

    @staticmethod
    def load(skill):
        return Path(skill.location).read_text(encoding="utf-8")


class CapabilityRegistry:
    """Seam for future connectors. v0.1 registers none; every capability would still pass the security gate."""

    def __init__(self):
        self._caps = {}

    def register(self, name, describe, handler):
        self._caps[name] = (describe, handler)

    def names(self):
        return sorted(self._caps)
