"""ASR, LLM, and voice-clone providers.

Pipelines depend on the small protocols below. The concrete clients read
credentials from the environment and are swappable: pass another object with
the same methods to skip these HTTP adapters. Tests supply fakes.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Protocol

OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
ELEVENLABS_ADD_VOICE_URL = "https://api.elevenlabs.io/v1/voices/add"
DEFAULT_ASR_MODEL = "whisper-1"
DEFAULT_LLM_MODEL = "gpt-4o-mini"


class MissingEnvError(RuntimeError):
    """A required credential variable is unset or blank."""

    def __init__(self, variable: str):
        self.variable = variable
        super().__init__(f"Missing required environment variable: {variable}")


class ProviderError(RuntimeError):
    """A provider call failed. The message never includes the API key."""


class Asr(Protocol):
    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcribe one owner clip. Return the transcript text."""


class Llm(Protocol):
    def complete(self, prompt: str) -> str:
        """Return a completion for prompt."""


class VoiceClone(Protocol):
    def register(self, segments: list[bytes]) -> str:
        """Register a clone from owner audio. Return the provider clone id."""


def require_env(name: str) -> str:
    """Read one credential. Blank values fail; there is no fallback key."""

    if name not in os.environ:
        raise MissingEnvError(name)
    value = os.environ[name]
    if value.strip() == "":
        raise MissingEnvError(name)
    return value


def resolve_key(api_key: str | None, variable: str) -> str:
    if api_key is None:
        return require_env(variable)
    if api_key.strip() == "":
        raise MissingEnvError(variable)
    return api_key


def _multipart(
    fields: list[tuple[str, str]],
    files: list[tuple[str, str, bytes]],
) -> tuple[str, bytes]:
    boundary = "mt" + uuid.uuid4().hex
    blocks: list[bytes] = []
    for name, value in fields:
        blocks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode()
        )
    for name, filename, payload in files:
        blocks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + payload
            + b"\r\n"
        )
    blocks.append(f"--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", b"".join(blocks)


def _send(request: urllib.request.Request, opener, timeout: float = 120) -> dict:
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"Provider request failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError("Provider request failed") from exc
    try:
        payload = json.loads(raw.decode())
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProviderError("Provider response was not JSON") from exc
    if not isinstance(payload, dict):
        raise ProviderError("Provider response was not a JSON object")
    return payload


class AsrClient:
    """OpenAI-compatible transcription. Reads ASR_API_KEY and nothing else."""

    env_var = "ASR_API_KEY"

    def __init__(
        self,
        api_key: str | None = None,
        opener=None,
        *,
        model: str = DEFAULT_ASR_MODEL,
        url: str = OPENAI_TRANSCRIPTIONS_URL,
    ):
        self.api_key = resolve_key(api_key, self.env_var)
        self._opener = opener or urllib.request.urlopen
        self.model = model
        self.url = url

    def transcribe(self, wav_bytes: bytes) -> str:
        content_type, body = _multipart(
            [("model", self.model)],
            [("file", "owner.wav", wav_bytes)],
        )
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": content_type,
                "Accept": "application/json",
            },
            method="POST",
        )
        payload = _send(request, self._opener)
        text = payload.get("text")
        if not isinstance(text, str):
            raise ProviderError("ASR response did not include text")
        return text.strip()


class LlmClient:
    """OpenAI-compatible chat completion. Reads LLM_API_KEY and nothing else."""

    env_var = "LLM_API_KEY"

    def __init__(
        self,
        api_key: str | None = None,
        opener=None,
        *,
        model: str = DEFAULT_LLM_MODEL,
        url: str = OPENAI_CHAT_URL,
    ):
        self.api_key = resolve_key(api_key, self.env_var)
        self._opener = opener or urllib.request.urlopen
        self.model = model
        self.url = url

    def complete(self, prompt: str) -> str:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(
                {
                    "model": self.model,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        payload = _send(request, self._opener)
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("LLM response did not include completion text") from exc
        if not isinstance(text, str):
            raise ProviderError("LLM response did not include completion text")
        return text.strip()


class ElevenLabsVoiceCloneClient:
    """Instant voice clone. Reads ELEVENLABS_API_KEY and does not fall back."""

    env_var = "ELEVENLABS_API_KEY"

    def __init__(self, api_key: str | None = None, opener=None, *, url: str = ELEVENLABS_ADD_VOICE_URL):
        self.api_key = resolve_key(api_key, self.env_var)
        self._opener = opener or urllib.request.urlopen
        self.url = url

    def register(self, segments: list[bytes]) -> str:
        if not segments:
            raise ProviderError("Voice clone requires owner audio")
        content_type, body = _multipart(
            [("name", "meeting-twin-owner")],
            [("files", f"owner-{index}.wav", segment) for index, segment in enumerate(segments)],
        )
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": content_type,
                "Accept": "application/json",
            },
            method="POST",
        )
        payload = _send(request, self._opener)
        voice_id = payload.get("voice_id")
        if not isinstance(voice_id, str) or voice_id == "":
            raise ProviderError("Voice-clone response did not include voice_id")
        return voice_id


class TtsVoiceCloneClient:
    """Generic voice-clone client. Reads TTS_API_KEY only.

    The default meeting-twin voice path is ElevenLabsVoiceCloneClient. This
    client exists so a TTS provider can be constructed from TTS_API_KEY without
    borrowing another variable. It has no HTTP endpoint of its own.
    """

    env_var = "TTS_API_KEY"

    def __init__(self, api_key: str | None = None):
        self.api_key = resolve_key(api_key, self.env_var)

    def register(self, segments: list[bytes]) -> str:
        del segments
        raise ProviderError(
            "TtsVoiceCloneClient has no default HTTP provider; "
            "use ElevenLabsVoiceCloneClient or pass a VoiceClone"
        )
