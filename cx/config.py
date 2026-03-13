from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_PATH = Path.home() / ".cx.yaml"


@dataclass
class Rule:
    pattern: re.Pattern
    key: str
    command: str
    description: str = ""
    exit: bool = False


def load_config(path: Path = CONFIG_PATH) -> list[Rule]:
    if not path.exists():
        return []

    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        print(f"cx: config parse error in {path}: {e}", file=sys.stderr)
        sys.exit(1)

    rules: list[Rule] = []
    for i, item in enumerate(raw.get("rules", [])):
        try:
            pattern = re.compile(item["pattern"])
        except re.error as e:
            print(
                f"cx: bad regex in rule {i} ({item.get('description', item.get('command', '?'))}): {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        key = str(item["key"])
        if len(key) != 1:
            print(f"cx: rule {i}: key must be a single character, got {key!r}", file=sys.stderr)
            sys.exit(1)

        rules.append(
            Rule(
                pattern=pattern,
                key=key,
                command=item["command"],
                description=item.get("description", item["command"]),
                exit=bool(item.get("exit", False)),
            )
        )

    return rules
