"""Fail a repo scan when tracked files contain live-looking keys or hard-coded secrets."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_LIVE_KEY = re.compile(
    r"sk-[A-Za-z0-9]{20,}"
    r"|sk_(?:live|test)_[A-Za-z0-9]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[0-9A-Za-z\-_]{20,}"
)

_QUOTED_SECRET = re.compile(
    r"""(?ix)
    (?:ASR_API_KEY|LLM_API_KEY|TTS_API_KEY|ELEVENLABS_API_KEY|api_key|apikey|secret|password)
    \s*=\s*
    (?P<q>['"])
    (?P<value>.*?)
    (?P=q)
    |
    ['"]
    (?:ASR_API_KEY|LLM_API_KEY|TTS_API_KEY|ELEVENLABS_API_KEY|api_key|apikey)
    ['"]
    \s*[:=]\s*
    (?P<q2>['"])
    (?P<value2>.*?)
    (?P=q2)
    """
)

_ENV_ASSIGNMENT = re.compile(
    r"""(?im)
    ^\s*(?:export\s+)?
    (?:ASR_API_KEY|LLM_API_KEY|TTS_API_KEY|ELEVENLABS_API_KEY)
    \s*=\s*
    (?P<value>.*?)\s*$
    """
)


@dataclass(frozen=True)
class SecretFinding:
    path: str
    line: int
    kind: str


def scan_text(path: str, text: str) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if _LIVE_KEY.search(line):
            findings.append(SecretFinding(path, line_number, "live_key"))
            continue
        quoted = _QUOTED_SECRET.search(line)
        if quoted:
            value = quoted.group("value") if quoted.group("value") is not None else quoted.group("value2")
            if value is not None and value.strip() != "":
                findings.append(SecretFinding(path, line_number, "hardcoded_assignment"))
                continue
        env = _ENV_ASSIGNMENT.search(line)
        if env and env.group("value").strip() != "":
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
