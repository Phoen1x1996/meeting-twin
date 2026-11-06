import pytest

from meeting_twin.audio import AudioError, TimingError, parse_timing, slice_wav
from wavutil import RATE, pcm_constant, pcm_of, pcm_sine, wav_bytes, write_wav


def test_parse_timing_ignores_comments_and_duplicate_ranges():
    text = """
# owner ranges in seconds
0.0 1.0

2.0 3.0
0.0 1.0
"""
    ranges = parse_timing(text)
    assert [(item.start, item.end) for item in ranges] == [("0.0", "1.0"), ("2.0", "3.0")]


def test_parse_timing_rejects_bad_lines():
    with pytest.raises(TimingError):
        parse_timing("0.0\n")
    with pytest.raises(TimingError):
        parse_timing("1.0 1.0\n")
    with pytest.raises(TimingError):
        parse_timing("-1 2\n")


def test_slice_wav_keeps_only_the_ranges(tmp_path):
    owner_a = pcm_sine(RATE, 440)
    other = pcm_constant(RATE, 0x1337)
    owner_b = pcm_sine(RATE, 660)
    clip = tmp_path / "clip.wav"
    write_wav(clip, owner_a + other + owner_b)

    slices = slice_wav(clip.read_bytes(), parse_timing("0.0 1.0\n2.0 3.0\n"))
    assert len(slices) == 2
    assert pcm_of(slices[0]) == owner_a
    assert pcm_of(slices[1]) == owner_b
    assert other not in slices[0]
    assert other not in slices[1]
    assert wav_bytes(owner_a) == slices[0]


def test_slice_rejects_range_past_end_of_clip():
    clip = wav_bytes(pcm_sine(RATE, 440))
    with pytest.raises(AudioError):
        slice_wav(clip, parse_timing("0.0 2.0\n"))
