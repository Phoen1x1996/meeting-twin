"""Fail a repo scan when tracked files contain live-looking keys or hard-coded secrets."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Hyphens belong in the token so sk-proj-... and sk-ant-... match. The pattern
# text itself does not, because "[" follows the sk- prefix in this source.
_LIVE_KEY = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}"
    r"|sk_(?:live|test)_[A-Za-z0-9]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[0-9A-Za-z\-_]{20,}"
)

_ENV_NAMES = r"ASR_API_KEY|LLM_API_KEY|TTS_API_KEY|ELEVENLABS_API_KEY"
_ASSIGN_NAMES = _ENV_NAMES + r"|api_key|apikey|secret|password"

# (?x) is required: the pattern is wrapped across lines for readability.
_ENV_ASSIGNMENT = re.compile(
    rf"""(?imx)
    ^\s*(?:export\s+)?
    (?:{_ENV_NAMES})
    \s*=\s*
    (?P<value>.*?)\s*$
    """
)

# Covers `name = "value"` and `name: annotation = "value"`.
_QUOTED_ASSIGNMENT = re.compile(
    rf"""(?ix)
    \b(?:{_ASSIGN_NAMES})
    \s*(?::[^=\n]*)?
    =\s*
    (?P<q>['"])
    (?P<value>.*?)
    (?P=q)
    """
)

_SUBSCRIPT_ASSIGNMENT = re.compile(
    rf"""(?ix)
    \[\s*['"](?:{_ENV_NAMES})['"]\s*\]
    \s*=\s*
    (?P<q>['"])
    (?P<value>.*?)
    (?P=q)
    """
)

_GET_DEFAULT = re.compile(
    rf"""(?ix)
    \.get\(\s*['"](?:{_ENV_NAMES}|api_key|apikey)['"]\s*,\s*
    (?P<q>['"])
    (?P<value>.*?)
    (?P=q)
    """
)


@dataclass(frozen=True)
class SecretFinding:
    path: str
    line: int
    kind: str


def _has_secret_value(value: str | None) -> bool:
    if value is None:
        return False
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text != ""


def scan_text(path: str, text: str) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if _LIVE_KEY.search(line):
            findings.append(SecretFinding(path, line_number, "live_key"))
            continue
        assignment = (
            _QUOTED_ASSIGNMENT.search(line)
            or _SUBSCRIPT_ASSIGNMENT.search(line)
            or _GET_DEFAULT.search(line)
            or _ENV_ASSIGNMENT.search(line)
        )
        if assignment and _has_secret_value(assignment.group("value")):
            findings.append(SecretFinding(path, line_number, "hardcoded_assignment"))
    return findings


def scan_path(path: Path, root: Path | None = None) -> list[SecretFinding]:
    display = str(path if root is None else path.relative_to(root))
    data = path.read_bytes()
    if b"\0" in data:
        return []
    return scan_text(display, data.decode("utf-8", "replace"))


def tracked_files(root: Path) -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    files: list[Path] = []
    for rel in output.split(b"\0"):
        if rel:
            files.append(root / rel.decode())
    return files


def scan_repo(root: Path) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for path in tracked_files(root):
        if path.is_file():
            findings.extend(scan_path(path, root))
    return findings
