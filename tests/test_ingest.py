import atexit
import hashlib
import json
import os
from pathlib import Path

import pytest

from meeting_twin.ingest import IngestRefused, import_clip
from wavutil import MARKER, RATE, pcm_constant, pcm_of, pcm_sine, wav_bytes, write_wav

OTHER_SAMPLE = 0x1337


class FakeAsr:
    def __init__(self, lines: list[str]):
        self.lines = lines
        self.seen: list[bytes] = []

    def transcribe(self, wav_payload: bytes) -> str:
        self.seen.append(bytes(wav_payload))
        if MARKER in wav_payload:
            return "other-speaker-line"
        return self.lines[len(self.seen) - 1]


class FakeLlm:
    def __init__(self, description: str = "Short and direct."):
        self.description = description
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.description


class FakeVoice:
    def __init__(self):
        self.segments: list[list[bytes]] = []

    def register(self, segments: list[bytes]) -> str:
        self.segments.append([bytes(segment) for segment in segments])
        return "clone-registered"


class BoomVoice(FakeVoice):
    def register(self, segments: list[bytes]) -> str:
        super().register(segments)
        raise RuntimeError("voice down")


def _mixed_clip(tmp_path: Path):
    owner_a = pcm_sine(RATE, 440)
    other = pcm_constant(RATE, OTHER_SAMPLE)
    owner_b = pcm_sine(RATE, 660)
    clip = tmp_path / "clip.wav"
    write_wav(clip, owner_a + other + owner_b)
    timing = tmp_path / "clip.timing"
    timing.write_text("# start end, seconds\n0.0 1.0\n2.0 3.0\n", encoding="utf-8")
    return clip, timing, owner_a, other, owner_b


def _run(tmp_path: Path, *, asr=None, llm=None, voice=None):
    clip, timing, owner_a, other, owner_b = _mixed_clip(tmp_path)
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    result = import_clip(
        clip,
        timing,
        recordings_dir=recordings,
        data_dir=data,
        asr=asr or FakeAsr(["owner-line-1", "owner-line-2"]),
        llm=llm or FakeLlm(),
        voice=voice or FakeVoice(),
    )
    return result, recordings, data, owner_a, other, owner_b, clip


def _snapshot(path: Path) -> dict[str, bytes | None]:
    if not path.exists():
        return {"__missing__": b""}
    state: dict[str, bytes | None] = {}
    for child in sorted(path.rglob("*")):
        relative = str(child.relative_to(path))
        state[relative] = child.read_bytes() if child.is_file() else None
    return state


def test_writes_only_owner_ranges(tmp_path):
    result, recordings, _data, owner_a, other, owner_b, _clip = _run(tmp_path)
    files = sorted(path for path in recordings.rglob("*") if path.is_file())
    assert files == list(result.recordings)
    assert [pcm_of(path.read_bytes()) for path in files] == [owner_a, owner_b]
    stored = b"".join(path.read_bytes() for path in files)
    assert other not in stored


def test_missing_timing_leaves_store_unchanged(tmp_path):
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    recordings.mkdir()
    data.mkdir()
    (recordings / "sentinel.txt").write_text("keep", encoding="utf-8")
    (data / "sentinel.txt").write_text("keep", encoding="utf-8")
    before_recordings = _snapshot(recordings)
    before_data = _snapshot(data)
    clip, _timing, *_rest = _mixed_clip(tmp_path)
    asr = FakeAsr(["owner-line-1"])

    with pytest.raises(IngestRefused, match="timing file is required"):
        import_clip(
            clip,
            None,
            recordings_dir=recordings,
            data_dir=data,
            asr=asr,
            llm=FakeLlm(),
            voice=FakeVoice(),
        )
    missing = tmp_path / "no-such.timing"
    with pytest.raises(IngestRefused, match="timing file is required"):
        import_clip(
            clip,
            missing,
            recordings_dir=recordings,
            data_dir=data,
            asr=asr,
            llm=FakeLlm(),
            voice=FakeVoice(),
        )
    empty = tmp_path / "empty.timing"
    empty.write_text("# no ranges\n\n", encoding="utf-8")
    with pytest.raises(IngestRefused, match="no owner speech ranges"):
        import_clip(
            clip,
            empty,
            recordings_dir=recordings,
            data_dir=data,
            asr=asr,
            llm=FakeLlm(),
            voice=FakeVoice(),
        )

    assert asr.seen == []
    assert _snapshot(recordings) == before_recordings
    assert _snapshot(data) == before_data

    absent_recordings = tmp_path / "new-recordings"
    absent_data = tmp_path / "new-data"
    with pytest.raises(IngestRefused):
        import_clip(
            clip,
            None,
            recordings_dir=absent_recordings,
            data_dir=absent_data,
            asr=asr,
            llm=FakeLlm(),
            voice=FakeVoice(),
        )
    assert not absent_recordings.exists()
    assert not absent_data.exists()


def test_transcript_and_style_profile_come_from_owner_lines(tmp_path):
    asr = FakeAsr(["owner-line-1", "owner-line-2"])
    llm = FakeLlm("Short and direct.")
    _result, _recordings, data, *_rest = _run(tmp_path, asr=asr, llm=llm)

    transcripts = list((data / "transcripts").glob("*.json"))
    assert len(transcripts) == 1
    transcript = json.loads(transcripts[0].read_text(encoding="utf-8"))
    assert [item["text"] for item in transcript["utterances"]] == ["owner-line-1", "owner-line-2"]

    profile = json.loads((data / "style_profile.json").read_text(encoding="utf-8"))
    assert profile["description"] == "Short and direct."
    assert [turn["text"] for turn in profile["few_shot_turns"]] == ["owner-line-1", "owner-line-2"]
    assert llm.prompts
    assert "owner-line-1" in llm.prompts[0]
    assert "owner-line-2" in llm.prompts[0]
    assert "other-speaker-line" not in llm.prompts[0]
    assert "other-speaker-line" not in (data / "style_profile.json").read_text(encoding="utf-8")


def test_voice_clone_receives_owner_audio_only(tmp_path):
    voice = FakeVoice()
    result, _recordings, _data, owner_a, other, owner_b, _clip = _run(tmp_path, voice=voice)
    assert result.voice_clone_id == "clone-registered"
    assert len(voice.segments) == 1
    uploaded = voice.segments[0]
    assert uploaded == [path.read_bytes() for path in result.recordings]
    assert [pcm_of(segment) for segment in uploaded] == [owner_a, owner_b]
    assert other not in b"".join(uploaded)
    assert MARKER not in b"".join(uploaded)


def test_rerun_does_not_duplicate_ranges_or_turns(tmp_path):
    asr = FakeAsr(["owner-line-1", "owner-line-2"])
    llm = FakeLlm()
    voice = FakeVoice()
    clip, timing, *_rest = _mixed_clip(tmp_path)
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    kwargs = {
        "recordings_dir": recordings,
        "data_dir": data,
        "asr": asr,
        "llm": llm,
        "voice": voice,
    }
    first = import_clip(clip, timing, **kwargs)
    before = _snapshot(recordings), _snapshot(data)
    second = import_clip(clip, timing, **kwargs)

    assert second.skipped is True
    assert second.recordings == first.recordings
    assert _snapshot(recordings) == before[0]
    assert _snapshot(data) == before[1]
    wavs = [path for path in recordings.rglob("*.wav") if path.is_file()]
    assert len(wavs) == 2
    profile = json.loads((data / "style_profile.json").read_text(encoding="utf-8"))
    assert len(profile["few_shot_turns"]) == 2
    assert len(asr.seen) == 2
    assert len(llm.prompts) == 1
    assert len(voice.segments) == 1


def test_reimport_matches_equivalent_range_spellings(tmp_path):
    asr = FakeAsr(["owner-line-1", "owner-line-2"])
    llm = FakeLlm()
    voice = FakeVoice()
    clip, timing, owner_a, _other, owner_b = _mixed_clip(tmp_path)
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    kwargs = {
        "recordings_dir": recordings,
        "data_dir": data,
        "asr": asr,
        "llm": llm,
        "voice": voice,
    }
    import_clip(clip, timing, **kwargs)
    alt = tmp_path / "alt.timing"
    alt.write_text("0.00 1.00\n2.00 3.00\n", encoding="utf-8")
    second = import_clip(clip, alt, **kwargs)
    assert second.skipped is True
    wavs = sorted(path for path in recordings.rglob("*.wav") if path.is_file())
    assert [pcm_of(path.read_bytes()) for path in wavs] == [owner_a, owner_b]
    profile = json.loads((data / "style_profile.json").read_text(encoding="utf-8"))
    assert len(profile["few_shot_turns"]) == 2
    assert len(voice.segments) == 1
    assert len(asr.seen) == 2
    assert len(llm.prompts) == 1


def test_reimport_rewrites_missing_wavs(tmp_path):
    voice = FakeVoice()
    clip, timing, owner_a, _other, owner_b = _mixed_clip(tmp_path)
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    kwargs = {
        "recordings_dir": recordings,
        "data_dir": data,
        "asr": FakeAsr(["owner-line-1", "owner-line-2"]),
        "llm": FakeLlm(),
        "voice": voice,
    }
    first = import_clip(clip, timing, **kwargs)
    for path in first.recordings:
        path.unlink()
    second = import_clip(clip, timing, **kwargs)
    assert second.skipped is False
    assert all(path.is_file() for path in second.recordings)
    assert [pcm_of(path.read_bytes()) for path in second.recordings] == [owner_a, owner_b]
    profile = json.loads((data / "style_profile.json").read_text(encoding="utf-8"))
    assert len(profile["few_shot_turns"]) == 2
    assert len(voice.segments) == 1


def test_reimport_to_another_recordings_dir_writes_wavs(tmp_path):
    voice = FakeVoice()
    clip, timing, owner_a, _other, owner_b = _mixed_clip(tmp_path)
    data = tmp_path / "data"
    first_dir = tmp_path / "recordings-a"
    second_dir = tmp_path / "recordings-b"
    shared = {
        "data_dir": data,
        "asr": FakeAsr(["owner-line-1", "owner-line-2"]),
        "llm": FakeLlm(),
        "voice": voice,
    }
    import_clip(clip, timing, recordings_dir=first_dir, **shared)
    second = import_clip(clip, timing, recordings_dir=second_dir, **shared)
    assert second.skipped is False
    assert all(path.is_file() and path.is_relative_to(second_dir) for path in second.recordings)
    assert [pcm_of(path.read_bytes()) for path in second.recordings] == [owner_a, owner_b]
    profile = json.loads((data / "style_profile.json").read_text(encoding="utf-8"))
    assert len(profile["few_shot_turns"]) == 2
    assert len(voice.segments) == 1


def _regular_files(root: Path) -> set[Path]:
    found: set[Path] = set()
    if not root.exists():
        return found
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            try:
                if path.is_file() and not path.is_symlink():
                    found.add(path)
            except OSError:
                continue
    return found


def test_other_participant_bytes_are_not_stored(tmp_path, monkeypatch):
    temp_dir = tmp_path / "tmp"
    temp_dir.mkdir()
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("TMPDIR", str(temp_dir))
    monkeypatch.setenv("TEMP", str(temp_dir))
    monkeypatch.setenv("TMP", str(temp_dir))
    voice = FakeVoice()
    llm = FakeLlm()
    clip, timing, _owner_a, other, _owner_b = _mixed_clip(tmp_path)
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    before = {
        "cwd": _regular_files(work),
        "private_tmp": _regular_files(temp_dir),
        "tmp": _regular_files(Path("/tmp")),
    }
    registered: list[tuple] = []

    def spy_register(func, *args, **kwargs):
        registered.append((func, args, kwargs))
        return func

    monkeypatch.setattr(atexit, "register", spy_register)

    import_clip(
        clip,
        timing,
        recordings_dir=recordings,
        data_dir=data,
        asr=FakeAsr(["owner-line-1", "owner-line-2"]),
        llm=llm,
        voice=voice,
    )
    for func, args, kwargs in registered:
        func(*args, **kwargs)

    other_wav = wav_bytes(other)
    clip_bytes = clip.read_bytes()
    banned_digests = {
        hashlib.sha256(other).hexdigest(),
        hashlib.sha256(other_wav).hexdigest(),
        hashlib.sha256(clip_bytes).hexdigest(),
    }
    stored_files = [
        path
        for root in (recordings, data)
        for path in root.rglob("*")
        if path.is_file()
    ]
    digests = []
    for path in stored_files:
        payload = path.read_bytes()
        digests.append(hashlib.sha256(payload).hexdigest())
        assert other not in payload
        assert MARKER not in payload
        assert clip_bytes not in payload
        assert b"other-speaker-line" not in payload
    assert banned_digests.isdisjoint(digests)

    after = {
        "cwd": _regular_files(work),
        "private_tmp": _regular_files(temp_dir),
        "tmp": _regular_files(Path("/tmp")),
    }
    for label, paths in after.items():
        for path in paths - before[label]:
            try:
                payload = path.read_bytes()
            except OSError:
                continue
            assert other not in payload, label
            assert MARKER not in payload, label
            assert clip_bytes not in payload, label

    profile = json.loads((data / "style_profile.json").read_text(encoding="utf-8"))
    assert all(turn["text"].startswith("owner-line-") for turn in profile["few_shot_turns"])
    assert "other-speaker-line" not in llm.prompts[0]
    assert other not in b"".join(voice.segments[0])
    assert clip_bytes not in b"".join(voice.segments[0])


def test_provider_failure_writes_nothing(tmp_path):
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    clip, timing, *_rest = _mixed_clip(tmp_path)
    voice = BoomVoice()
    with pytest.raises(RuntimeError, match="voice down"):
        import_clip(
            clip,
            timing,
            recordings_dir=recordings,
            data_dir=data,
            asr=FakeAsr(["owner-line-1", "owner-line-2"]),
            llm=FakeLlm(),
            voice=voice,
        )
    assert not recordings.exists()
    assert not data.exists()
    assert len(voice.segments) == 1
    assert all(MARKER not in segment for segment in voice.segments[0])


@pytest.mark.parametrize("timing_text", ["nan 1", "inf 2", "-1 2", "3 1"])
def test_bad_ranges_are_refused(tmp_path, timing_text):
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    clip, _timing, *_rest = _mixed_clip(tmp_path)
    timing = tmp_path / "bad.timing"
    timing.write_text(timing_text + "\n", encoding="utf-8")
    with pytest.raises(IngestRefused, match="refusing to store clip"):
        import_clip(
            clip,
            timing,
            recordings_dir=recordings,
            data_dir=data,
            asr=FakeAsr(["owner-line-1"]),
            llm=FakeLlm(),
            voice=FakeVoice(),
        )
    assert not recordings.exists()
    assert not data.exists()


def test_out_of_range_timing_writes_nothing(tmp_path):
    recordings = tmp_path / "recordings"
    data = tmp_path / "data"
    clip, _timing, *_rest = _mixed_clip(tmp_path)
    timing = tmp_path / "past-end.timing"
    timing.write_text("0.0 9.0\n", encoding="utf-8")
    asr = FakeAsr(["owner-line-1"])
    with pytest.raises(IngestRefused, match="outside the clip"):
        import_clip(
            clip,
            timing,
            recordings_dir=recordings,
            data_dir=data,
            asr=asr,
            llm=FakeLlm(),
            voice=FakeVoice(),
        )
    assert asr.seen == []
    assert not recordings.exists()
    assert not data.exists()
