# meeting-twin

Local tool that answers in the owner's voice when he is addressed in a meeting.

## Import the owner's recordings

Point the command at one of his clips and a timing file of when he spoke. Import keeps those ranges, transcribes them, writes a style profile from his lines, and registers a voice clone from that audio. Audio outside the ranges is discarded in memory and is not written.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

Set `ASR_API_KEY`, `LLM_API_KEY`, and `ELEVENLABS_API_KEY` in the environment before running. `.env.example` lists the names and has empty values. Copy it to `.env` (gitignored) if you keep the values locally; the app reads the environment, not the file.

```bash
meeting-twin import path/to/clip.wav --timing path/to/clip.timing
```

`--recordings-dir` and `--data-dir` default to `recordings` and `data`.

The timing file is plain text. Each line is one owner range in seconds from the start of the clip: `start end`. Blank lines and `#` comments are ignored.

```
# start end, in seconds
12.50 18.00
40.00 44.25
```

Without `--timing`, import refuses and leaves `recordings/` and `data/` unchanged. Importing the same clip and timing file again does not duplicate ranges or style-profile turns.

Output, all gitignored:

- `recordings/<clip-id>/000.wav`, `001.wav`, ... — one file per owner range
- `data/transcripts/<clip-id>.json` — his lines
- `data/style_profile.json` — a short style description plus few-shot turns from those lines
- `data/manifest.json` — the ranges and the voice-clone id returned by the provider

The default ASR and LLM clients speak the OpenAI-compatible APIs. The default voice clone is ElevenLabs. A missing variable stops the command and prints that variable's name. Tests pass fakes and do not need keys:

```bash
pip install -e ".[dev]"
pytest
```
