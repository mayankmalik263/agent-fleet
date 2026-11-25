"""Load the project subagent definitions from .claude/agents/*.md (official Claude Code format) and turn
them into the JSON object that `claude --agents <file>` accepts. One source of truth for both modes:
interactive Claude Code in this repository reads the .md files; the runner passes the same definitions."""

import json
from dataclasses import dataclass
from pathlib import Path

from ..core.config import REPO_ROOT

AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
_LIST_FIELDS = {"tools", "disallowedTools"}
# permissionMode is never passed: the run's permission policy decides, and bypass must stay impossible.
_PASS_FIELDS = ("description", "tools", "disallowedTools", "model", "maxTurns", "effort")


@dataclass
class AgentDefinition:
    name: str
    description: str
    model: str
    prompt: str
    fields: dict[str, object]


def parse_markdown(text: str) -> AgentDefinition:
    if not text.startswith("---"):
        raise ValueError("agent file must start with YAML frontmatter")
    _, front, body = text.split("---", 2)
    fields: dict[str, object] = {}
    for raw in front.strip().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        key, _, value = raw.partition(":")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key in _LIST_FIELDS:
            fields[key] = [v.strip() for v in value.split(",") if v.strip()]
        elif key == "maxTurns" and value.isdigit():
            fields[key] = int(value)
        else:
            fields[key] = value
    name = str(fields.get("name") or "")
    if not name or not fields.get("description"):
        raise ValueError("agent frontmatter needs name and description")
    return AgentDefinition(
        name=name,
        description=str(fields["description"]),
        model=str(fields.get("model", "inherit")),
        prompt=body.strip(),
        fields=fields,
    )


def load_definitions(directory: Path = AGENTS_DIR) -> dict[str, AgentDefinition]:
    defs: dict[str, AgentDefinition] = {}
    for path in sorted(directory.glob("*.md")):
        definition = parse_markdown(path.read_text(encoding="utf-8"))
        defs[definition.name] = definition
    return defs


def agents_json(defs: dict[str, AgentDefinition]) -> str:
    payload = {
        name: {"prompt": d.prompt, **{k: d.fields[k] for k in _PASS_FIELDS if k in d.fields}}
        for name, d in defs.items()
    }
    return json.dumps(payload, indent=2)
