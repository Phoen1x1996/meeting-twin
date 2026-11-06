# Secrets stay in the environment

The repo is public. Credentials for ASR, the LLM, and TTS are read from the environment and nowhere else.

## Acceptance criteria

- A repo scan, run in tests, fails if any tracked file contains a live-looking API key or a hard-coded secret assignment. `.env` is gitignored. `.env.example` lists names only and has empty values.
- Provider clients take keys from `ASR_API_KEY`, `LLM_API_KEY`, and `TTS_API_KEY` (or `ELEVENLABS_API_KEY` for that client). Missing variables fail at startup with the variable name, not with a fallback key.
- Unit tests construct clients with fake keys supplied through the environment or the constructor in the test, never with a default literal in production code.
- `recordings/`, `data/`, transcripts, style profiles, and voice-clone artifacts match `.gitignore` and are absent from `git ls-files`.
