"""Import the owner's own speech ranges, transcript, style profile, and voice clone."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from meeting_twin.audio import AudioError, SpeechRange, TimingError, parse_timing, slice_wav
from meeting_twin.providers import Asr, Llm, VoiceClone


class IngestRefused(RuntimeError):
    """Import will not store this clip. recordings/ and data/ are left untouched."""


@dataclass(frozen=True)
class ImportResult:
    clip_id: str
    recordings: tuple[Path, ...]
    voice_clone_id: str
    skipped: bool


def style_prompt(lines: list[str]) -> str:
    """Ask for a short style description using only the owner's lines."""

    body = "\n".join(lines)
    return (
        "Write a short description of this speaker's style. "
        "Use only the speaker's lines below.\n"
        f"{body}"
    )


def import_clip(
    clip_path: Path,
    timing_path: Path | None,
    *,
    recordings_dir: Path,
    data_dir: Path,
    asr: Asr,
    llm: Llm,
    voice: VoiceClone,
) -> ImportResult:
    """Keep the timing-file ranges, transcribe them, and register a voice clone.

    A missing timing file refuses the import before anything is written. Audio
    outside the owner ranges is discarded in memory and is not sent to the
    transcript, style profile, or voice clone.
    """

    ranges = _load_ranges(timing_path)
    if not clip_path.is_file():
        raise IngestRefused("refusing to store clip: clip file not found")

    clip_bytes = clip_path.read_bytes()
    try:
        slices = slice_wav(clip_bytes, ranges)
    except AudioError as exc:
        raise IngestRefused(f"refusing to store clip: {exc}") from exc
    clip_id = _owner_id(ranges, slices)
    manifest_path = data_dir / "manifest.json"
    manifest = _read_json(manifest_path, {"clips": {}})
    clips = manifest.setdefault("clips", {})
    stored = clips.get(clip_id)
    range_payload = [item.as_dict() for item in ranges]
    recording_paths = _recording_paths(recordings_dir, clip_id, ranges)

    if stored is not None and stored.get("ranges") == range_payload:
        missing = not all(path.is_file() for path in recording_paths)
        if missing:
            _write_bytes(recording_paths, slices)
        voice_clone_id = str(stored.get("voice_clone_id") or "")
        if voice_clone_id:
            return ImportResult(
                clip_id=clip_id,
                recordings=recording_paths,
                voice_clone_id=voice_clone_id,
                skipped=not missing,
            )
        voice_clone_id = voice.register(list(slices))
        stored["voice_clone_id"] = voice_clone_id
        _write_json(manifest_path, manifest)
        return ImportResult(
            clip_id=clip_id,
            recordings=recording_paths,
            voice_clone_id=voice_clone_id,
            skipped=False,
        )

    utterances = []
    for speech_range, segment in zip(ranges, slices, strict=True):
        utterances.append(
            {
                "start": speech_range.start,
                "end": speech_range.end,
                "text": asr.transcribe(segment).strip(),
            }
        )

    profile = _read_json(
        data_dir / "style_profile.json",
        {"description": "", "few_shot_turns": []},
    )
    turns = list(profile.get("few_shot_turns", []))
    seen = {(turn["clip_id"], turn["start"], turn["end"], turn["text"]) for turn in turns}
    for utterance in utterances:
        turn = {
            "clip_id": clip_id,
            "start": utterance["start"],
            "end": utterance["end"],
            "text": utterance["text"],
        }
        key = (turn["clip_id"], turn["start"], turn["end"], turn["text"])
        if key not in seen:
            turns.append(turn)
            seen.add(key)
    description = llm.complete(style_prompt([turn["text"] for turn in turns])).strip()

    _write_bytes(recording_paths, slices)
    _write_json(
        data_dir / "transcripts" / f"{clip_id}.json",
        {"clip_id": clip_id, "utterances": utterances},
    )
    _write_json(
        data_dir / "style_profile.json",
        {"description": description, "few_shot_turns": turns},
    )
    clips[clip_id] = {
        "ranges": range_payload,
        "recordings": [path.name for path in recording_paths],
    }
    _write_json(manifest_path, manifest)
    voice_clone_id = voice.register(list(slices))
    clips[clip_id]["voice_clone_id"] = voice_clone_id
    _write_json(manifest_path, manifest)
    return ImportResult(
        clip_id=clip_id,
        recordings=recording_paths,
        voice_clone_id=voice_clone_id,
        skipped=False,
    )


def _load_ranges(timing_path: Path | None) -> list[SpeechRange]:
    if timing_path is None or not timing_path.is_file():
        raise IngestRefused("refusing to store clip: timing file is required")
    try:
        ranges = parse_timing(timing_path.read_text(encoding="utf-8"))
    except TimingError as exc:
        raise IngestRefused(f"refusing to store clip: {exc}") from exc
    if not ranges:
        raise IngestRefused("refusing to store clip: timing file has no owner speech ranges")
    return ranges


def _owner_id(ranges: list[SpeechRange], slices: list[bytes]) -> str:
    digest = hashlib.sha256()
    for speech_range, segment in zip(ranges, slices, strict=True):
        payload = speech_range.as_dict()
        digest.update(payload["start"].encode())
        digest.update(b"\0")
        digest.update(payload["end"].encode())
        digest.update(b"\0")
        digest.update(segment)
    return digest.hexdigest()


def _recording_paths(recordings_dir: Path, clip_id: str, ranges: list[SpeechRange]) -> tuple[Path, ...]:
    clip_dir = recordings_dir / clip_id
    return tuple(clip_dir / f"{index:03d}.wav" for index in range(len(ranges)))


def _write_bytes(paths: tuple[Path, ...], slices: list[bytes]) -> None:
    for path, segment in zip(paths, slices, strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(segment)


def _read_json(path: Path, default):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
