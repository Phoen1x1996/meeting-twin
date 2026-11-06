import subprocess
from pathlib import Path

from meeting_twin.secret_scan import scan_repo, scan_text

ROOT = Path(__file__).resolve().parents[1]


def test_repo_scan_finds_no_secrets():
    assert scan_repo(ROOT) == []


def test_scanner_flags_live_key_and_assignment(tmp_path):
    key_name = "ASR_" + "API_KEY"
    live = "sk-" + ("a" * 24)
    planted = tmp_path / "planted.py"
    planted.write_text(f'{key_name} = "planted-value"\nvalue = "{live}"\n', encoding="utf-8")
    findings = scan_text(str(planted), planted.read_text(encoding="utf-8"))
    kinds = {finding.kind for finding in findings}
    assert kinds == {"hardcoded_assignment", "live_key"}


def test_scanner_allows_empty_env_and_name_mentions():
    text = "\n".join(
        [
            "ASR_API_KEY=",
            "LLM_API_KEY=",
            "TTS_API_KEY=",
            "ELEVENLABS_API_KEY=",
            'require_env("ASR_API_KEY")',
            'api_key = require_env("LLM_API_KEY")',
        ]
    )
    assert scan_text(".env.example", text) == []


def test_env_example_lists_names_only():
    names = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, separator, value = stripped.partition("=")
        assert separator == "="
        assert value == ""
        names.append(name)
    assert names == [
        "ASR_API_KEY",
        "LLM_API_KEY",
        "TTS_API_KEY",
        "ELEVENLABS_API_KEY",
    ]


def test_private_paths_are_gitignored_and_untracked():
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    banned_prefixes = ("recordings/", "data/", "transcripts/", "style-profile/", "voice-clones/")
    banned_suffixes = (".wav", ".mp3", ".flac", ".m4a", ".ogg", ".webm", ".aac")
    for path in tracked:
        assert not path.startswith(banned_prefixes)
        assert not path.endswith(banned_suffixes)
        assert path != ".env" and not path.startswith(".env.") or path == ".env.example"

    ignored = (
        ".env",
        "recordings/owner.wav",
        "data/style_profile.json",
        "data/manifest.json",
        "transcripts/owner.txt",
        "style-profile/profile.json",
        "voice-clones/clone.json",
    )
    for path in ignored:
        result = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=ROOT)
        assert result.returncode == 0, path

    example = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", ".env.example"],
        cwd=ROOT,
    )
    assert example.returncode != 0
