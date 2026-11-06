"""Read a timing file and cut owner speech ranges out of a wav in memory."""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass


def canonical_seconds(value: float) -> str:
    """Stable spelling so 0.0 and 0.00 are the same range."""

    return format(value, ".10g")


class TimingError(ValueError):
    """The timing file is not a list of owner speech ranges."""


class AudioError(ValueError):
    """The clip is not a wav, or a range does not fit inside it."""


@dataclass(frozen=True)
class SpeechRange:
    """One owner range. start and end are the timing-file tokens, in seconds."""

    start: str
    end: str

    @property
    def start_seconds(self) -> float:
        return float(self.start)

    @property
    def end_seconds(self) -> float:
        return float(self.end)

    def as_dict(self) -> dict[str, str]:
        return {
            "start": canonical_seconds(self.start_seconds),
            "end": canonical_seconds(self.end_seconds),
        }


def parse_timing(text: str) -> list[SpeechRange]:
    """Parse `start end` lines in seconds. Blank lines and # comments are ignored."""

    ranges: list[SpeechRange] = []
    seen: set[tuple[float, float]] = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) != 2:
            raise TimingError(f"line {line_number}: expected start and end in seconds")
        start, end = parts
        try:
            start_seconds = float(start)
            end_seconds = float(end)
        except ValueError as exc:
            raise TimingError(f"line {line_number}: expected start and end in seconds") from exc
        if start_seconds < 0 or end_seconds <= start_seconds:
            raise TimingError(f"line {line_number}: end must be greater than start")
        key = (start_seconds, end_seconds)
        if key in seen:
            continue
        seen.add(key)
        ranges.append(SpeechRange(start, end))
    return ranges


def slice_wav(wav_bytes: bytes, ranges: list[SpeechRange]) -> list[bytes]:
    """Return one wav per range. Nothing outside those ranges is included."""

    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as source:
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            frame_rate = source.getframerate()
            frame_count = source.getnframes()
            frames = source.readframes(frame_count)
    except (wave.Error, EOFError) as exc:
        raise AudioError("not a readable wav file") from exc

    frame_width = channels * sample_width
    if frame_width <= 0 or len(frames) != frame_count * frame_width:
        raise AudioError("not a readable wav file")

    slices: list[bytes] = []
    for speech_range in ranges:
        start = int(round(speech_range.start_seconds * frame_rate))
        end = int(round(speech_range.end_seconds * frame_rate))
        if start < 0 or end > frame_count or start >= end:
            raise AudioError("timing range is outside the clip")
        chunk = frames[start * frame_width : end * frame_width]
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as target:
            target.setnchannels(channels)
            target.setsampwidth(sample_width)
            target.setframerate(frame_rate)
            target.writeframes(chunk)
        slices.append(buffer.getvalue())
    return slices
