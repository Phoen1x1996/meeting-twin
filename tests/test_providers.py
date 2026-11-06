import json

import pytest

from meeting_twin.cli import build_voice_client
from meeting_twin.providers import (
    AsrClient,
    ElevenLabsVoiceCloneClient,
    LlmClient,
    MissingEnvError,
)

KEY_NAMES = ("ASR_API_KEY", "LLM_API_KEY", "TTS_API_KEY", "ELEVENLABS_API_KEY")


class _Response:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _clear_keys(monkeypatch):
    for name in KEY_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_missing_env_names_the_variable(monkeypatch):
    _clear_keys(monkeypatch)
    cases = (
        (AsrClient, "ASR_API_KEY"),
        (LlmClient, "LLM_API_KEY"),
        (ElevenLabsVoiceCloneClient, "ELEVENLABS_API_KEY"),
    )
    for cls, variable in cases:
        with pytest.raises(MissingEnvError) as caught:
            cls()
        assert caught.value.variable == variable
        assert variable in str(caught.value)


def test_blank_env_is_missing(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("ASR_API_KEY", "   ")
    with pytest.raises(MissingEnvError) as caught:
        AsrClient()
    assert caught.value.variable == "ASR_API_KEY"


def test_constructor_key_does_not_require_env(monkeypatch):
    _clear_keys(monkeypatch)
    supplied = "constructor" + "-key"
    client = AsrClient(api_key=supplied)
    assert client.api_key == supplied


def test_elevenlabs_does_not_fall_back_to_tts_key(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("TTS_API_KEY", "tts-only")
    with pytest.raises(MissingEnvError) as caught:
        ElevenLabsVoiceCloneClient()
    assert caught.value.variable == "ELEVENLABS_API_KEY"


def test_asr_request_uses_env_key_and_audio(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("ASR_API_KEY", "asr-from-env")
    seen = []

    def opener(request, timeout):
        seen.append((request, timeout))
        return _Response({"text": " owner line "})

    text = AsrClient(opener=opener).transcribe(b"RIFFowner-audio")
    request, timeout = seen[0]
    assert text == "owner line"
    assert timeout == 120
    assert request.full_url.endswith("/audio/transcriptions")
    assert request.get_header("Authorization") == "Bearer asr-from-env"
    assert b"RIFFowner-audio" in request.data


def test_llm_request_uses_env_key_and_prompt(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "llm-from-env")
    seen = []

    def opener(request, timeout):
        seen.append(request)
        return _Response({"choices": [{"message": {"content": " Short and direct. "}}]})

    text = LlmClient(opener=opener).complete("describe only these lines")
    request = seen[0]
    assert text == "Short and direct."
    assert request.full_url.endswith("/chat/completions")
    assert request.get_header("Authorization") == "Bearer llm-from-env"
    body = json.loads(request.data.decode())
    assert body["messages"][0]["content"] == "describe only these lines"


def test_import_voice_client_uploads_audio_with_elevenlabs_key(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("TTS_API_KEY", "tts-only")
    with pytest.raises(MissingEnvError) as caught:
        build_voice_client()
    assert caught.value.variable == "ELEVENLABS_API_KEY"

    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-from-env")
    seen = []

    def opener(request, timeout):
        seen.append(request)
        return _Response({"voice_id": "voice-from-test", "requires_verification": False})

    owner = b"OWNER-WAV-BYTES"
    clone_id = build_voice_client(opener=opener).register([owner])
    assert clone_id == "voice-from-test"
    assert owner in seen[0].data
    assert seen[0].get_header("Xi-api-key") == "el-from-env"


def test_voice_clone_upload_contains_only_given_audio(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-from-env")
    seen = []
    owner = b"OWNER-WAV-BYTES"
    other = b"OTHER-PARTICIPANT-BYTES"

    def opener(request, timeout):
        seen.append(request)
        return _Response({"voice_id": "voice-from-test", "requires_verification": False})

    clone_id = ElevenLabsVoiceCloneClient(opener=opener).register([owner])
    request = seen[0]
    assert clone_id == "voice-from-test"
    assert request.full_url.endswith("/voices/add")
    assert request.get_header("Xi-api-key") == "el-from-env"
    assert owner in request.data
    assert other not in request.data
