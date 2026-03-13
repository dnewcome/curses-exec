from __future__ import annotations

import re
import shlex


def interpolate(template: str, line: str, match: re.Match) -> str:
    """Substitute {line}, {0}, {1}, {2}, ... and named groups into template."""
    subs: dict[str, str] = {
        "line": line,
        "0": match.group(0),
    }
    for i, g in enumerate(match.groups(), 1):
        subs[str(i)] = g or ""
    for name, val in match.groupdict().items():
        subs[name] = val or ""

    def replacer(m: re.Match) -> str:
        key = m.group(1)
        return subs.get(key, m.group(0))

    return re.sub(r"\{(\w+)\}", replacer, template)
