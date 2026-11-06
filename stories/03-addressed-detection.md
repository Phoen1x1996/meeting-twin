# Speak only when addressed

While a meeting is playing, the tool answers only if the latest utterance addresses the owner by the configured name or asks him a question. Any other speech produces silence.

## Acceptance criteria

- On the labeled test set (each window tagged `addressed` or `not-addressed`), the false-trigger rate is under 5%. False-trigger rate is the share of `not-addressed` windows that the detector marks as addressed.
- Recall on `addressed` windows is at least 90%, so a detector that never fires does not pass.
- A `not-addressed` window produces no TTS call and no samples on the output device.
- An `addressed` window starts answer audio within 2 seconds of the address point (end of the name or of the question directed at him, as labeled).
- Detection may use streaming ASR partials. Other speakers' audio and the partial text used for detection are not written to `recordings/` or `data/`.
