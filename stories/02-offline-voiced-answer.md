# Offline text question to a voiced answer

With a style profile and a voice clone loaded, a Japanese or English text question produces a spoken Japanese reply in the owner's voice. No microphone and no Teams.

## Acceptance criteria

- The first PCM sample is delivered within 2 seconds of submitting the question, measured on the local pipeline (stub or real TTS). The test clock starts at submit and stops at the first sample handed to the audio output.
- The reply text is Japanese on every item in the pinned eval set (language id `ja`, 100%).
- Style eval, pinned with the eval set version: an LLM judge scores each reply 1–5 against the style profile and five held-out owner turns, on politeness, typical length and directness, and characteristic phrasing. Pass when the mean is at least 4.0 and no item is below 3. The owner may replace the judge on the same rubric; that rating is the record.
- The spoken audio is the TTS of that Japanese text via the voice-clone interface. Swapping the TTS fake changes the bytes and nothing else in the call path.
- The reply is streamed: audio begins before the full LLM completion is finished. A test with a slow token stream asserts the first sample arrives before the final token.
