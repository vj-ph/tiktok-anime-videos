# Nationalfeiertag: playful history intro and B2 discussion

Status: complete checked preview for approval, October 25, 2026.
The reusable dressing code has been checked with a silent native fixture
and inspected full-size renders; see the review delivery below.
The user has now requested the complete preview. The authoritative screenplay
is `pilot_3d/episodes/oeif_b2_nationalfeiertag.json` (13 turns).
Three local excerpts of the selected Austrian recordings have independently
matching, unprompted ASR transcripts; shared originals remain unchanged.
Episode validation and 81 focused tests pass. Real audio in
`pilot_3d/builds/oeif_b2_nationalfeiertag_v7_preview_r2/` is 100.833333 seconds
including pauses and CTA. All 13 turns match independent, unprompted German
ASR. All 24 subtitle pages pass (minimum 1.916667 encoded seconds, maximum
19.948052 encoded characters/second). Seven low-confidence alignment tokens
remain disclosed in `audio_qa.json`; no auditory/accent certification is claimed.
The full native preview is complete in
`pilot_3d/builds/oeif_b2_nationalfeiertag_v7_preview_r3/`: `pilot.mp4` and
`pilot_clean.mp4` both decode completely at 720x1280, H.264/yuv420p, 24 fps,
with AAC 48 kHz mono audio. The second run's native check caught a pose-dependent opening-frame
hair/hat collision before rendering. Fitting now undoes the head's pose before
sizing and binds the resulting hat back to its native head transform.
An intentionally tilted regression in `austrian_props_tilted_fit_r11` passes
326 head/hair samples with 8.9 mm minimum clearance. The lower brim position,
hat dimensions and all accepted prop choices remain unchanged. The third run
reuses every second-run raw recording; the failed scene/receipt is preserved.
Its full native checks pass 1210 head/hair poses, five doorway crossings and
249 caption-clear portraits, with minimum hair/crown clearance of 1.505 mm.
The final `episode_qa.json` verifies 27 actual encoded boundary samples,
the 29-frame examiner hold, full 192-frame reading card, 144-frame CTA and
correct B2 cover at the beginning/middle/end. All 20 frozen output and 21
source hashes verify, as do all 51 earlier masters, the source book and the
shared voice originals. Final full-size entrance/backpack/flags, examiner
drinks, hat portrait, reading card and ending frames have been inspected;
see `episode_review/visual_inspection.json` and both contact sheets.
Posting drafts are in `posts/oeif_b2_nationalfeiertag/`.
Manual listening and user preview approval remain pending. No production or
upload has been requested or performed; current platform upload constraints
and mobile placement are not certified.
The user selected a 100-120-second target.
The source book remains unchanged. The selected visual props
are flags, Samir's hat, the examiner's coffee set and Samir's backpack.
No strudel or other food prop is included.

### Requested title revision after preview

The authored episode's main title and visible opening hook now read
**ÖIF B2: Neutral? Nicht bei Feiertagen!**. Both posting drafts match.
The compact header already identifies ÖIF B2 in its brand row and keeps the
short topic row to preserve the approved layout. This editorial-only revision
does not change speech, voices, pauses or the checked r3 preview.
The user requested no replacement preview and only the production command;
no new render has been started. See the README command using the revised
authored JSON, a fresh production directory and exact r3 `--reuse-audio`.
All six episode tests, configured-runtime episode validation, layout generation
on the real timeline and exact audio-reuse checks pass. All frozen r3 output
and source hashes remain unchanged; the proposed production directory is absent.

## Concept

Main title: **ÖIF B2: Neutral? Nicht bei Feiertagen!**

An Austrian-themed exam room surprises Samir. Lea explains the historical
connection, Samir makes a deliberately silly neutrality joke, and a dry
examiner moves them into a substantive discussion about an additional holiday.
Humour comes from the characters and their enthusiasm for time off, not from
mocking Austrian identity or treating neutrality as a rule for private opinions.

The history intro is fictional entertainment, not an official exam phase.
The subsequent discussion is a shortened practice adaptation, not a full
test or complete model dialogue. Clearly separate the two with:

- Opening label: `26. Oktober · Nationalfeiertag`
- Discussion label: `ÖIF B2 · Teil 2 · Kurzdialog`

## Source and historical basis

Book: `german_exam_books/b2/speaking_oeif_gpt_v2/book_no_toc.md`,
Kapitel 2, discussion 7:
`Soll ein zusätzlicher gesetzlicher Feiertag eingeführt werden?`
The exercise starts at line 937 and the model dialogue at line 970 in the
current book.

Use the existing Nationalfeiertag as the opening context, then explicitly
ask about an **additional** holiday. Do not imply October 26 is a proposed
holiday or suggest replacing it.

Historical source checked October 25, 2026:
Bundeskanzleramt, `Aktivitäten zum Nationalfeiertag 2026`,
https://www.bundeskanzleramt.gv.at/bundeskanzleramt/besuchen-sie-uns/nationalfeiertag.html

The Nationalrat passed the neutrality constitutional law on October 26, 1955.
October 26 became the Nationalfeiertag in 1965. Do not confuse the date with
the signing of the Staatsvertrag or describe it as the day the last soldier
left Austria.

## Authored screenplay

Timing is an unmeasured target. Confirm it with real Qwen audio before scene
baking; never speed up speech or falsify clocks to fit the target.

### 1. Entrance and comic history introduction

Keep the familiar entrance. Austrian decorations become visible immediately.
Samir notices a desk flag; his hat stays attached to his head throughout.

**Prüfer:** Guten Tag. Nehmen Sie bitte Platz.

**Samir:** So viele Fahnen! Habe ich die Prüfung oder einen Staatsbesuch gebucht?

**Lea:** Nur die Prüfung. Am 26. Oktober 1955 beschloss der Nationalrat die
Neutralität. Seit 1965 ist dieser Tag der Nationalfeiertag.

**Samir:** Dann bleibe ich auch neutral: ausschlafen oder spazieren gehen?

**Lea:** Beim Frühstück darfst du dich trotzdem entscheiden.

Brief reaction from Lea; the examiner remains straight-faced. No laugh track,
shouting, exaggerated accent or extra generated laughter.

### 2. Clear transition into B2 practice

**Prüfer:** Und jetzt entscheiden Sie sich für ein Argument. Soll Österreich
einen zusätzlichen Feiertag bekommen?

Show a separately labelled **gekürzter Leseimpuls** during the eight-second
learning pause:

> Familien profitieren von gemeinsamer Freizeit.
> Pflege und Verkehr arbeiten auch an Feiertagen.
> Fester Feiertag oder frei wählbarer Tag?

This is an original short training summary, not the full book text or an
official stimulus. Its statements support both initial text reactions below.

### 3. Text reactions, arguments and interaction

**Lea:** Der Text betont gemeinsame Freizeit. Ich bin dafür: Meine Schwester
und ich haben sonst selten gleichzeitig frei.

**Samir:** Mich beschäftigt der Hinweis auf Pflegekräfte: Sie arbeiten auch an
Feiertagen. Wäre ein freier Tag nach eigener Wahl nicht gerechter?

**Lea:** Das stimmt. Trotzdem ersetzt Urlaub keinen gemeinsamen Tag. Welcher
Anlass verbindet uns, und wie berücksichtigen wir Schichtarbeit?

**Samir:** Ein Tag fürs Ehrenamt könnte verbinden. Dazu brauchen wir
verlässlichen Zeitausgleich und Schutz vor zusätzlicher Arbeitsverdichtung.

**Lea:** Einverstanden. Entscheidend ist nicht nur mehr Freizeit, sondern eine
faire Verteilung. Auch kleine Betriebe brauchen Planungssicherheit.

**Samir:** Für faire Dienstpläne bin ich sofort zu haben. Für Frühdienst weniger.

**Prüfer:** Ein gutes Argument. Und ausschlafen können Sie nach der Prüfung.

The final line is a comedy callback, not scoring feedback or a claim that the
whole examination has ended. Both candidates remain competent adults; Samir
contributes real arguments rather than serving only as the joke character.

### 4. Book ending

Six-second visual CTA, not extra spoken dialogue:

> Mehr B2-Dialoge
> im ÖIF-B2-Sprechbuch
> Amazon-Buchlink im Profil

Use the actual B2 book cover, not the old DTZ or TEF cover. Posting copy should
identify the comedy introduction and shortened independent practice, with the
usual book-promotion, synthetic-media and rig disclosures.

## Visual design

Keep the existing room, Lea, Samir, examiner, observer and restrained acting.
No outdoor scene or elaborate cloth simulation is needed.

| Element | First-episode design |
| --- | --- |
| Room | A red-white-red wall banner and small desk flags, clear of the brand plaque and character faces |
| Lea | Existing outfit, hair and face unchanged |
| Samir | Existing outfit with a dark-green Alpine-style hat and small red-white-red band |
| Examiner | Existing professional outfit, coffee cup/saucer/water glass and dry comic reactions |
| Observer | Existing silent observer, unchanged |
| Backpack | Stationary beside Samir's chair, clear of the entrance and feet; visible in an opening wide shot |
| Camera | Wide entrance reveal, then normal stable speaker shots and subtle reaction holds |

The hat is playful styling, not a claim that it is uniquely Austrian or typical
of everyone in Austria. Avoid dressing every character in festival costume.
Do not obscure eyes, eyebrows or lip-sync, and check hat clearance through the
door, seating and head turns. Avoid hand-held flag waving or hat removal in
this first version: they add contact and animation complexity without helping
the dialogue.

## Austrian reference-voice casting

Use the user-selected set:
`../shared-voices/gemini_3.8_flash_tts/austrain/`
(relative to the video-repository root). Preserve the supplied spelling.

| Role | Actual reference filename |
| --- | --- |
| Lea / candidate_a | `female_young_adult_austrian.wav` |
| Samir / candidate_b | `male_young_adlut_austrian.wav` |
| Examiner | `male_middle_adult_austrian.wav` |

All six WAVs in the set opened successfully as mono, 24 kHz, 16-bit PCM.
The selected clips are respectively 14.92, 14.36 and 15.36 seconds. These
container checks are not a listening, accent or pronunciation certification.

`voices.json` currently lists different filenames and a missing
`reference_text.txt`; its model metadata also should not be treated as verified
provenance for these differently named files. Do not silently rename/edit the
shared set or load those stale entries.

`phrase.txt` contains a dialect-heavy reference passage. Independent ASR
corroborated that passage but inconsistently recognized its dialect words.
The episode therefore uses local, unretimed PCM16 excerpts of the clean final
15 words: "Wie ein kleiner König. Aber lass uns das jetzt schnell vergessen
und das Leben genießen!" All three derived clips independently match that
text without a recognition prompt. Their durations are 4.245, 4.3 and 4.86
seconds. Source/crop hashes and ASR evidence are recorded in
`pilot_3d/assets/voices/austrian/provenance.json`; the shared files are untouched.
No insults or beer-garden passage enter the episode. ASR agreement is not
human listening or accent certification.

Qwen3-TTS 1.7B Base remains the episode synthesis model. The user explicitly
requested different references for this Austrian episode; existing DTZ/TEF
voices remain unchanged. Review the real generated speech before rendering.

The first audio take is preserved in
`pilot_3d/builds/oeif_b2_nationalfeiertag_v7_preview_r1/`, including its two
unresolved ASR wording differences. The second take uses clearer wording for
turns 08 and 10; all other 11 raw recordings are byte-identical. No voice,
speech-rate setting or measured alignment was altered to force agreement.

## Reusable dressing implementation

The user approved implementation and prop-review stills. Use the small,
opt-in `scene.dressing` configuration, not a parallel scene generator:

| Configurable surface | Reusable scope |
| --- | --- |
| Room decorations | Optional banners and desk flags with explicit colour/placement choices |
| Garment palette | Possible later extension; no outfit recolouring needed for these four selected props |
| Accessories | Optional per-actor head-attached hat, including colour/band |
| Voice casting | Per-episode role references, reusable as an Austrian cast preset |

The `pilot_3d/assets/props/austria.json` preset combines the four selected
props; other episodes can reuse or omit individual parts. Outfit recolouring
and a separate voice preset remain possible later extensions.
Absent settings must preserve current DTZ/TEF visuals and voices exactly.
Respect the existing Windows/Linux runtime tooling, cache keys, source/asset
hash guards and fresh-build requirements.

The authored episode keeps the non-exam introduction in the existing welcome
phase, followed by one instruction and the discussion. Focused tests verify
that entrance seating finishes before eight seconds, that the later reading
card follows its real instruction rather than the history, and that the
semantic headers reset. No new shared animation phase was required.

Acceptance includes configuration rejection tests, unchanged default plans,
voice-reference/transcript validation, native accessory attachment/visibility,
and a few inspected full-size frames before a full preview. Generate speech
and measure the total runtime including pauses and CTA before promising
100-120 seconds. Any production render or publication needs separate approval.

### Concrete first implementation

Use one optional `scene.dressing` block, with named room anchors and explicit
accessory owners. This is the implemented first configuration:

```json
{
  "scene": {
    "dressing": {
      "props": [
        {"type": "flag", "pattern": "austria", "anchor": "back_wall_left"},
        {"type": "flag", "pattern": "austria", "anchor": "table_corner"},
        {"type": "coffee_set", "anchor": "examiner_table_side"},
        {"type": "backpack", "anchor": "candidate_b_chair_side"}
      ],
      "accessories": [
        {"type": "hat", "style": "alpine", "actor": "candidate_b"}
      ]
    }
  }
}
```

- Add one small `scene_dressing.py` module with pure configuration validation
  and lazily imported Blender builders. Use named anchors based on the existing
  room/table/chair geometry, not absolute coordinates in each episode.
- `episode_config.py` validates supported types/patterns/anchors, inactive
  actors and incompatible or duplicate placements. Missing dressing produces
  no objects or new default behaviour.
- `produce_v4.py` applies dressing after actor animation is baked and before
  saving the final scene. Reuse `StudioCharacter.from_scene()` and its existing
  head control rather than inventing a second skeleton/animation system.
- Create all new objects in a dedicated collection. Record requested settings,
  actual object names, anchors, actor/bone attachment and transforms in the
  scene manifest only for dressed episodes.
- Include the new module in existing source hashing, frozen-source snapshots
  and render/check receipts. Runtime/tool/device handling stays untouched.
- Fit only a hatted actor's normal close-up to the unchanged header/subtitle
  area. The rendered review caught an otherwise hidden hat top under the
  header; retain the wide and other actors' cameras unchanged.

Use free downloaded geometry where useful and simple procedural pieces:

- Flags: red-white-red mesh stripes; one wall flag and one small rigid desk
  flag with stand. No coat of arms, downloaded image or cloth simulation.
- Hat: crown, brim and band fitted to Samir's actual head/hair. Follow the
  evaluated head transform with a preserved attachment offset; parenting only
  to the actor root would leave the hat behind during head turns.
- Coffee set: sourced cup/handle and saucer from Poly Haven's CC0 Tea Set 01,
  with plain porcelain replacing the original textures. Add a procedural water
  glass and fixed liquid surfaces. No pouring, steam or hand-contact animation.
- Backpack: sourced CC0 model from the Pixor free library, normalized to 52 cm
  and grounded beside the chair. The initially considered Quaternius public
  download returned a quota error; no unavailable model or licence is claimed.
  Do not animate wearing it, putting it down or picking it up.

The simple hat is the approved custom fallback, not a downloaded or purchased
hat. Both downloaded sources have recorded publisher URLs, CC0 statements,
hashes and adaptations in `pilot_3d/assets/props/provenance.json`.

Extend `check_v4_scene.py` and native fixtures to verify saved objects,
head-following across entrance/seating/dialogue, ground/table contact and
clearance from the door/feet/hands. Inspect real wide and speaker frames with
captions so the flags, hat, coffee and backpack are actually visible where
intended, not merely present somewhere in the scene. Keep objects out of the
logo, face and subtitle regions. Re-run default German/TEF regressions to
ensure old episode settings still produce the same plans.

## Checked prop-review delivery

Initial directory: `pilot_3d/builds/austrian_props_review_r8/`.
Open `review/contact_sheet.jpg`; six raw PNGs and six `_captioned.png` versions
are alongside it. All PNGs are 720x1280, rendered with Cycles at 16 samples.
`studio.blend`, `scene_manifest.json`, `scene_checks.json` and
`dressing_review.json` retain the scene and image evidence. The coffee and
backpack detail cameras are inspection views, not additional episode shots.

The fixture is explicitly silent and synthetic. Its four short caption lines
and artificial word positions are not Qwen output, measured alignment, the B2
screenplay or a complete exam simulation. No movie was generated or published.
The Austrian voice-reference transcripts and the full intro/discussion episode
remain pending.

The real saved scene passed the existing native checks and additional checks:

- Hat: 326 head-following poses, four doorway-clearance samples and 30 speaking
  poses with the entire head/hat clear of the header and subtitles.
- Table props: no support-height error; closest sampled fingertip clearance
  is 17.2 cm for the desk flag and 30.5 cm for the coffee set.
- Cup: foot centred and ray-seated on the actual saucer, with 0.2 mm clearance.
- Backpack: grounded, with 12.0 cm minimum clearance outside the candidates'
  existing 34 cm route/body envelope.
- Required images packed; selected source asset hashes match their catalogue.

Rendered inspection caught and corrected an invisible head-helper affecting
hat placement, the hat top behind the header, a partly cropped wall flag,
cup/saucer spacing and dark low-bounce glass shading. Undressed scenes retain
their cameras and props; only a hatted actor's normal close-up is reframed.
The silent native TEF/interview regression also passes.

The initial review's broad regression run has 250 passing tests and three skips, with one
explicitly excluded pre-existing failure:
`test_runtime.RuntimeTests.test_platform_tools_and_legacy_linux_layout`
patches `sys.platform` to Windows on Linux/Python 3.12 and reaches an unavailable
`_winapi.NeedCurrentDirectoryForExePath`. Its files are unchanged. The 75
focused dressing/configuration/direction tests pass, and real German, TEF and
dressed-fixture configurations validate with local assets. Native Windows
execution of the new prop fixture has not been performed on this Linux host.
All 50 pre-existing movie master hashes remain unchanged.

### Placement revision after user review, October 25, 2026

Latest directory: `pilot_3d/builds/austrian_props_review_r10/`.
The initial r8 and intermediate r9 scenes and images are preserved. Extra
geometry checking found a small rear-hair poke-through in r9 during head
turns; r10 strengthens the covered-hair fitting and checks it at every sampled
pose against the real crown mesh, not just from the front camera.

- Move the coffee/water group from `(-1.09, -0.53)` to `(-0.90, -0.80)` metres
  on the tabletop: about 30 cm nearer the examiner. Native fingertip clearance
  remains 5.8 cm; cup/saucer contact and table support still pass.
- Lower the hat brim about 4.3 cm and fit it farther back around the actual
  head/hair geometry. A head-following lattice tucks only the upper hair inside
  the crown without changing its source mesh, shape keys, hairline or another
  actor. The seated brim is 6.8 cm below the measured head-surface top.
- Native hat checks pass 326 head-following poses, five doorway-clearance
  samples and 30 caption-clear speaking poses, with upper-hair containment
  checked throughout. The 75 focused regressions and the final undressed native
  interview control pass.
- Keep the backpack where it is. It is visible at lower right in the actual
  opening entrance/welcome shot (`01 Room overview`, frame 78, about 3.21 s
  in this synthetic fixture). `review/backpack_in_entrance.png` marks it in
  that frame. It is not guaranteed in speaker close-ups, and the dedicated
  backpack detail view is not an episode shot.

`dressing_review.json` now records each view's actual timeline camera and
whether that camera matches the rendered view. In particular, the room-wide
inspection at 10.79 seconds is not a claim of a wide-camera cut there:
the examiner camera is actually selected then. This revision remains a
silent prop review, not the voiced Nationalfeiertag episode.
