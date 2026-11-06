# Teams virtual mic and stop hotkey

Answer audio is sent to Teams by playing it into a virtual microphone (VB-Cable on Windows, BlackHole on macOS). The owner can cut the twin off and return Teams to his real mic.

## Acceptance criteria

- While an answer is playing, the process writes PCM only to the configured virtual device, which is the device Teams is told to use as its microphone.
- When the twin is idle, the selected Teams input is the physical microphone, not the virtual device.
- Pressing the stop hotkey silences the virtual device within 300ms (no further non-silent samples) and switches the Teams input back to the physical mic within the same 300ms. The clock starts at the hotkey event.
- A stopped answer is discarded. No later chunk from that reply is played.
- After the hotkey, a new address can still be answered on a later turn. The hotkey does not exit the app.
