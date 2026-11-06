"""Build synthetic wavs in memory. Tests must not commit audio files."""

from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path

RATE = 16000
OTHER_SAMPLE = 0x1337
MARKER = struct.pack("<h", OTHER_SAMPLE) * 8


def pcm_sine(samples: int, freq: float, amplitude: int = 8000, rate: int = RATE) -> bytes:
    frames = bytearray()
    for index in range(samples):
        value = int(amplitude * math.sin(2 * math.pi * freq * index / rate))
        frames += struct.pack("<h", value)
    return bytes(frames)


def pcm_constant(samples: int, value: int) -> bytes:
    return struct.pack("<h", value) * samples


def wav_bytes(pcm: bytes, rate: int = RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def write_wav(path: Path, pcm: bytes, rate: int = RATE) -> None:
    path.write_bytes(wav_bytes(pcm, rate))


def read_pcm(path: Path) -> bytes:
    return pcm_of(path.read_bytes())


def pcm_of(payload: bytes) -> bytes:
    with wave.open(io.BytesIO(payload), "rb") as handle:
        pcm = handle.readframes(handle.getnframes())
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise AssertionError("expected mono 16-bit wav")
        return pcm
