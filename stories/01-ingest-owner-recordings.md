# Ingest the owner's recordings

The owner points the app at his own meeting clips and a timing file of when he spoke. The app keeps only those ranges, transcribes them, writes a style profile, and registers a voice clone from that audio.

## Acceptance criteria

- Given a clip plus a timing file of owner speech ranges, the files written under `recordings/` match those ranges and nothing outside them.
- Given a clip with no timing file, import refuses to store it and leaves `recordings/` and `data/` unchanged.
- A transcript and a style profile (short style description plus few-shot turns, all from his lines) are produced from the imported clips.
- The voice-clone step is called with only the imported owner audio. The provider client is swappable; the test uses a fake and asserts the audio bytes it received.
- Re-running import on the same clip does not duplicate ranges or few-shot turns.
