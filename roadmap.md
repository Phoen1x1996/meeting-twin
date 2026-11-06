# Roadmap

Each phase is usable on its own. Do not start a phase until the previous phase's stories pass. Latency is designed in from phase 2: stream every stage, and start audio on the first chunk.

## Phase 1 — Data ingest

Import recordings of the owner's own meeting utterances and the timestamps of when he speaks. Transcribe those clips. Build a style profile (prompt text plus few-shot excerpts from his transcripts). Set up the voice clone from that audio only.

No other participant's audio is kept. Import either receives owner-only clips, or cuts the owner's ranges and discards the rest before anything is written.

## Phase 2 — Offline voiced answer

Text question in, spoken Japanese answer out, in the owner's voice and style. First audio sample in under 2 seconds on the local machine. No live meeting yet. This is the latency and style baseline.

## Phase 3 — Live listening and addressed-detection

Listen to the meeting. Speak only when the owner is addressed by name or asked a question. Otherwise stay silent. On a labeled test set, the false-trigger rate is under 5%. The 2-second first-audio budget still holds, measured from the moment he is addressed.

## Phase 4 — Teams

Route the answer into Microsoft Teams through the virtual microphone (VB-Cable or BlackHole). The stop hotkey mutes the twin within 300ms and switches Teams back to the real microphone. Releasing the stop state does not resume a cut-off answer.
