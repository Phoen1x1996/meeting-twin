# meeting-twin

Local desktop tool for the owner (Japanese-speaking, uses Microsoft Teams). He is present in the meeting. When someone addresses him by name or asks him a question, the tool answers aloud in Japanese, in his cloned voice and speaking style, through a virtual microphone routed into Teams. A hotkey stops playback at once and switches Teams back to his real microphone.

Low latency is the core constraint. The first audio of an answer must start within 2 seconds of him being addressed. Otherwise the tool stays silent.

Style and voice data are recordings of the owner's own utterances, plus when he speaks. Store only his voice. Never persist other participants' audio.

## Tech stack

- Local Python app. The reply loop runs on the owner's machine.
- Virtual audio device: VB-Cable on Windows, BlackHole on macOS. TTS is written to that device; Teams selects it as the microphone while the twin is speaking. The physical mic is the Teams input when the twin is idle or stopped.
- Japanese streaming ASR, behind a provider interface. Partials feed addressed-detection; do not wait for a final transcript when a partial is already enough.
- LLM for the reply. System prompt plus few-shot turns taken from the owner's own transcripts (the style profile). Provider is swappable.
- Voice-clone TTS. ElevenLabs is the default candidate. TTS sits behind the same kind of interface so the provider can change without touching the pipeline. The clone is built only from the owner's voice.
- Global hotkey for stop and mic switch.

Streaming is mandatory on the hot path: ASR partials, LLM tokens, TTS audio chunks. Playback starts on the first speakable chunk.

## Conventions

- Python 3.11+.
- ASR, LLM, and TTS are small interfaces. Concrete clients live behind them. Tests use fakes.
- Secrets come from environment variables only. No API keys, tokens, or voice-clone IDs in source, tests, fixtures, or docs. Expected names: `ASR_API_KEY`, `LLM_API_KEY`, `TTS_API_KEY` (and `ELEVENLABS_API_KEY` only if that client reads it). See `.env.example` for names; it must not contain values.
- `recordings/`, `data/`, transcripts, style profiles, and voice-clone artifacts are gitignored. This repo is public. Do not commit audio or meeting text.
- Other participants' audio is processed in memory for ASR and then dropped. It is never written to disk, including temp files that outlive the process.
- The owner name used for address detection is configuration, not a hard-coded string scattered through the code.

## Tests

Once the package exists:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Latency, false-trigger, hotkey, language/style, privacy, and secret-scan checks are specified in `stories/`. Provider calls in unit tests are faked. Timing tests measure the local pipeline with a stub TTS that emits a first chunk immediately, plus one test that records real clock time from the trigger to the first PCM sample on the virtual device.
