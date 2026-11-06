# Do not persist anyone else's audio

The meeting contains other people. Their audio may be read for live ASR. It must not be stored. The style corpus and the voice clone stay owner-only.

## Acceptance criteria

- A session fixture with owner speech and other-participant speech leaves, on disk, only the owner ranges. A checksum list of `recordings/`, `data/`, and surviving temp files contains no other-participant bytes.
- Killing the session (normal stop and process exit) does not flush buffers of other people's audio to disk.
- The style profile and the voice-clone upload contain only owner transcripts and owner audio. A test inspects both payloads.
- ASR text for other speakers, if held at all, lives in memory for the current session and is gone after the session ends. It is not in the style profile.
