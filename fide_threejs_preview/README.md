# Three.js-native fide speaking preview

A separate technical prototype: procedural room, three seated characters,
speech-driven mouths, deterministic gestures/blinks, illustrated picture task
and measured word highlights. No Blender, glTF files, skeletons or skin weights.
Nothing in the existing generators is modified.

The excerpt shows an A2 picture description and a follow-up question, **not the
complete A2-B1 examination**. The requested full-video title is demonstrated in
the opening. Full exam content and final casting still need their own review.

## Deliverables

Generated files live in `builds\preview_swiss_r1\`:

| File | Purpose |
| --- | --- |
| `youtube.mp4` | Landscape technical preview, 960 x 540, 24 fps |
| `social.mp4` | Independently laid-out portrait preview, 540 x 960, 24 fps |
| `contact_youtube.jpg`, `contact_social.jpg` | Contact sheets decoded from the exported videos |
| `dialogue.wav`, `timeline.json` | Unaccelerated speech, pauses, measured words and RMS envelopes |
| `speech_review.json` | Independent, unprompted local ASR transcript |
| `render_receipt.json`, `final_audit.json` | Browser and encoded-delivery checks |
| `voice_inputs.json`, `audio_receipt.json` | Exact reference/input hashes |
| `existing_files.json` | Baseline hashes of tracked files outside this folder |
| `delivery_manifest.json` | SHA-256 inventory of this prototype and final delivery |

These are preview resolutions, not full-resolution production exports.
The temporary `layout_fixture` build contains synthetic timings solely for
layout tests; it cannot be exported as a voiced preview.

The delivered Swiss preview is **21.875 seconds / 525 frames per format**.
Five unit tests and 324 native-browser word-boundary checks passed.
Both videos fully decode, and the 541 tracked pre-existing files are unchanged.
The decoded contact sheets have been visually inspected. Human listening is
still pending: independent ASR transcribed the answer's "fährt" as "währt";
the raw result is retained rather than treated as verified pronunciation.

## Run from the repository root (PowerShell)

```powershell
npm ci --prefix .\fide_threejs_preview
npm test --prefix .\fide_threejs_preview

.\pilot_3d\.venv\Scripts\python.exe -B -X utf8 .\fide_threejs_preview\prepare.py prepare
.\pilot_3d\.venv\Scripts\python.exe -B -X utf8 .\fide_threejs_preview\prepare.py asr
node .\fide_threejs_preview\render.mjs --check-only
node .\fide_threejs_preview\render.mjs
.\pilot_3d\.venv\Scripts\python.exe -B -X utf8 .\fide_threejs_preview\review.py
```

Requires the repository's existing local Qwen/WhisperX/faster-whisper Python
environment and cached models, FFmpeg/FFprobe, Node, and Chrome. Set `CHROME_PATH`
if Chrome is not in its standard Windows installation location.
No new Python packages are needed.

For browser playback with audio and scrubbing:

```powershell
npm run serve --prefix .\fide_threejs_preview
```

Open the loopback address printed by the server, then click **Abspielen**.
The server binds only to `127.0.0.1`. Stop it with Ctrl+C.
Offline rendering owns and closes its own temporary server and browser.

### New revisions

Exports are not overwritten. Use a fresh build name when changing content:

```powershell
.\pilot_3d\.venv\Scripts\python.exe -B -X utf8 .\fide_threejs_preview\prepare.py prepare --build .\fide_threejs_preview\builds\preview_swiss_r2
.\pilot_3d\.venv\Scripts\python.exe -B -X utf8 .\fide_threejs_preview\prepare.py asr --build .\fide_threejs_preview\builds\preview_swiss_r2
node .\fide_threejs_preview\render.mjs --build=preview_swiss_r2
.\pilot_3d\.venv\Scripts\python.exe -B -X utf8 .\fide_threejs_preview\review.py preview_swiss_r2
```

## Design and verification

- Scene/characters are built from Three.js primitives in `room.mjs`.
  The candidate sits opposite the active examiner; the third person observes.
- `episode.json` controls the original six-turn demo script and pauses.
  The matching bus-stop illustration is an original local SVG.
- The examiner uses `male_middle_aged.wav`; the candidate uses
  `female_young_adult.wav` from the user-provided
  `..\shared-voices\gemini_3.8_flash_tts\swiss` folder.
  Each uses its own `text_<voice>.txt`, not the generic filename in the
  collection metadata. All selected WAVs, transcripts and metadata are hashed.
- The voices are synthetic Swiss Standard German references. ASR checks text;
  it does not certify accent quality or replace listening approval.
- Speech is locally synthesized, edge-quiet trimmed and resampled; never
  accelerated. All authored pauses remain in the exact 24-fps frame clock.
- WhisperX measures every spoken word. The expanded spoken title is mapped
  to the readable `fide-test A2-B1` only using its actual aligned intervals.
- Mouth openings follow per-frame speech RMS. Listeners and the observer
  remain closed-mouthed. This is basic amplitude animation, not phoneme lip-sync.
- Every image is rendered by explicit timeline time, not a real-time screen
  recording. Backward seeking must reproduce identical pixels.
- Chrome renders with software WebGL for predictable operation without a
  dedicated GPU requirement. This is not a GPU speed benchmark.
- Both native layouts check caption overflow, word boundaries and head
  positions before export. FFmpeg encodes exact screenshots plus the mixed WAV.
- The final audit checks full decode, resolution/frame count/duration,
  per-turn audio correlation, silent pause interiors, decoded/native reference
  frames and unchanged hashes of existing tracked files.

All task source, draft posts and generated outputs stay under this folder.
There is no fide book link/cover in this preview because none was supplied;
the Austrian book promotion is deliberately not reused. Posts are unpublished
drafts, with no fabricated Amazon CTA or book advertising claim.
