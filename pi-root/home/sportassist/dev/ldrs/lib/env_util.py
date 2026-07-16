"""Read/write /etc/sportassist/*.env files."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Dict

SPORTASSIST_ETC = Path("/etc/sportassist")


def load_env(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip("'\"")
    return out


def save_env(path: Path, values: Dict[str, str], header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        shutil.copy2(path, f"{path}.bak")
    lines: list[str] = []
    if header:
        lines.append(header.rstrip())
        lines.append("")
    for key, val in values.items():
        if val is None:
            continue
        if re.search(r"[\s#'\"]", str(val)):
            lines.append(f'{key}="{val}"')
        else:
            lines.append(f"{key}={val}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_env_keys(path: Path, updates: Dict[str, str]) -> None:
    current = load_env(path)
    current.update({k: v for k, v in updates.items() if v is not None})
    header = ""
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                header += line + "\n"
            else:
                break
    save_env(path, current, header=header.strip())
