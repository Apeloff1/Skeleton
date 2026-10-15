# Playable native PCM excerpts in live comparative emulator desk

The comparison host already collected authentic libretro 16-bit stereo samples for every native frame, but the previous browser desk discarded them. The live API now transports a **bounded** recent sample excerpt (up to 16,384 frames, 100k base64 characters), its sample rate and the original actual-PCM SHA digests, using the existing rights-cleared native host.

Each live game's controller stays immediately **beneath the unobstructed game image**. Below the controls is a separate manual **Listen to bounded native PCM** control. On explicit user click, the browser validates the excerpt length, adds a PCM RIFF/WAV header locally, and plays the short audio through an HTML audio element. The browser never automatically plays music, records microphone input or downloads games. CSP permits only same-origin connection and bounded locally created `blob:` media. Object URLs are revoked on view refresh.

This is a short local audio audition, not a complete real-time audio engine, music transcription, licensed-source reutilization for a new game, or Dragon audiovisual understanding. The emitted audio is game content from the operator's approved local rights-cleared ROM. The renderer is source-implemented, with synthetic PCM tests added; actual hardware/game playback verification is pending.
