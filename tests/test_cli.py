import pytest

from meeting_twin.cli import main
from test_ingest import FakeAsr, FakeLlm, FakeVoice
from wavutil import RATE, pcm_constant, pcm_of, pcm_sine, write_wav

KEY_NAMES = ("ASR_API_KEY", "LLM_API_KEY", "TTS_API_KEY", "ELEVENLABS_API_KEY")


def _clear(monkeypatch):
    for name in KEY_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_cli_refuses_without_timing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    clip = tmp_path / "clip.wav"
    write_wav(clip, pcm_sine(RATE, 440))
    code = main(["import", str(clip)])
    captured = capsys.readouterr()
    assert code == 1
    assert "timing file is required" in captured.err
    assert not (tmp_path / "recordings").exists()
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize(
    ("present", "missing"),
    [
        ([], "ASR_API_KEY"),
        (["ASR_API_KEY"], "LLM_API_KEY"),
        (["ASR_API_KEY", "LLM_API_KEY"], "ELEVENLABS_API_KEY"),
    ],
)
def test_cli_missing_key_names_variable(tmp_path, monkeypatch, capsys, present, missing):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    for name in present:
        monkeypatch.setenv(name, "present-for-test")
    clip = tmp_path / "clip.wav"
    clip.write_bytes(b"not-used")
    timing = tmp_path / "clip.timing"
    timing.write_text("0.0 1.0\n", encoding="utf-8")
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    code = main(
        [
            "import",
            str(clip),
            "--timing",
            str(timing),
            "--recordings-dir",
            str(recordings),
            "--data-dir",
            str(data),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert missing in captured.err
    assert not recordings.exists()
    assert not data.exists()


@pytest.mark.parametrize(
    "timing_text",
    ["nan 1.0", "inf 2.0", "-inf 1", "-1 1", "2 1", "1 nan", "0.0 inf"],
)
def test_cli_rejects_bad_ranges_without_traceback(tmp_path, monkeypatch, capsys, timing_text):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    clip = tmp_path / "clip.wav"
    write_wav(clip, pcm_sine(RATE, 440))
    timing = tmp_path / "clip.timing"
    timing.write_text(timing_text + "\n", encoding="utf-8")
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    code = main(
        [
            "import",
            str(clip),
            "--timing",
            str(timing),
            "--recordings-dir",
            str(recordings),
            "--data-dir",
            str(data),
        ],
        asr=FakeAsr(["owner-line-1"]),
        llm=FakeLlm(),
        voice=FakeVoice(),
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in captured.err
    assert "refusing to store clip" in captured.err
    assert not recordings.exists()
    assert not data.exists()


def test_cli_import_writes_owner_ranges(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _clear(monkeypatch)
    owner = pcm_sine(RATE, 440)
    other = pcm_constant(RATE, 0x1337)
    clip = tmp_path / "clip.wav"
    write_wav(clip, owner + other)
    timing = tmp_path / "clip.timing"
    timing.write_text("0.0 1.0\n", encoding="utf-8")
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    code = main(
        [
            "import",
            str(clip),
            "--timing",
            str(timing),
            "--recordings-dir",
            str(recordings),
            "--data-dir",
            str(data),
        ],
        asr=FakeAsr(["owner-line-1"]),
        llm=FakeLlm(),
        voice=FakeVoice(),
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "imported 1 owner range" in captured.out
    wavs = list(recordings.rglob("*.wav"))
    assert len(wavs) == 1
    assert pcm_of(wavs[0].read_bytes()) == owner
    assert other not in wavs[0].read_bytes()
    assert (data / "style_profile.json").is_file()
    assert (data / "transcripts").is_dir()
