# Optional scene props

`austria.json` is the value of an episode's optional `scene.dressing` block,
not a standalone episode. Copy it into the episode to enable both Austrian
flags, the examiner's coffee set, Samir's backpack and head-attached hat.
Omitting the block adds no props and needs none of these asset files.

`canada.json` enables a Canadian wall flag and a small desk flag without
the Austrian accessories or downloaded models. The authored TEF Canada Section
A and B episodes select this dressing explicitly; other episodes keep their
existing defaults. Geometry and the desk pole/base are original Blender meshes.
The wall flag is 90 x 45 cm and the desk flag is 24 x 12 cm.
The complete maple-leaf artwork is an unmodified 1280 x 640 PNG downloaded
from Wikimedia Commons, not an imported third-party 3D scene.
`canada.provenance.json` records its public-domain source designation,
publisher/download URLs, authors and exact PNG/source-SVG hashes.
This separate catalogue leaves the existing CC0 model metadata unchanged.
The PNG is packed into the scene for offline rendering; the original SVG is
also checked and included with the selected source assets in frozen deliveries.

The two downloaded models are free CC0 assets, checked October 24, 2026.
`provenance.json` records their publisher pages, download URLs, authors,
licences, exact source hashes and adaptations. No paid model was purchased.

| File | Source | Use |
| --- | --- | --- |
| `tea_set_01_1k.blend` | Poly Haven, Tea Set 01 | Only the small cup and round saucer are appended; original texture materials are replaced with plain porcelain |
| `pixor-library-backpack.glb` | Pixor free library, Backpack | Five mesh parts, flat colours; normalized to 52 cm high |

The water glass, coffee surface, flag geometry and simplified Alpine-style felt
hat are original procedural geometry; Canadian flag artwork is sourced as
described above. The hat uses the approved custom fallback,
not a sourced/purchased hat. No strudel, flag-waving, drinking, carrying or
cloth simulation is included.

The coffee set replaces the nearby generic left water cup only in dressed
scenes. Cup-foot contact is measured against the real saucer surface, not just
the group's table-height bounds. The clear glass uses stylized
transparent/Fresnel shading to retain the existing room's four-bounce budget.
The cup and glass are grouped near the examiner's table edge, clear of the
sampled hand gestures rather than placed in the middle of the table.

Both model files remain byte-for-byte downloads. No texture downloads,
Blender add-on, online access or third-party application is needed at render
time. Blender's built-in glTF importer handles the backpack. Appending the tea
set never runs embedded scripts; continue using `--disable-autoexec`.
CC0 attribution is not required; the source record is retained for provenance.
Existing character-rig attribution requirements still apply.

Named anchors target the current `exam_room` geometry. The supported first
set is deliberately small:

| Type | Required options |
| --- | --- |
| `flag` | `pattern: "austria"` or `"canada"`; `anchor: "back_wall_left"` or `"table_corner"` |
| `coffee_set` | `anchor: "examiner_table_side"` |
| `backpack` | `anchor: "candidate_b_chair_side"`; candidate B must be active |
| `hat` (in `accessories`) | `style: "alpine"`; `actor`: an active actor slot |

Hatted actors' normal close-up cameras are fitted to keep their complete head
and hat between the existing header and subtitle panels. The original and
adjusted lens/shift settings are recorded; native checks sample the actual
speaking poses for clearance. Other actors' cameras and all undressed episodes
retain their existing framing. Wide and picture-card cameras are not refitted.
The brim sits below the actual head surface rather than perching on its bounding
box. An owner-local, head-following lattice compresses only hair above the brim
inside the crown; the hairline, source mesh/shape keys and other actors are
unchanged. Omitting the hat adds no hair modifier.

The backpack is background dressing in the opening entrance/welcome wide
shot, on the floor beside Samir's chair at the lower right of the image. It
need not appear in the tighter speaker shots. The fixture's separate backpack
detail camera is inspection-only; its room-wide review can also differ from
the camera selected at that moment on the episode timeline. Review metadata
distinguishes these views and includes an annotated actual entrance frame.

Unknown options, duplicate anchors, duplicate head accessories and inactive
owners are rejected rather than silently ignored. This is not a generic asset
loader or an outfit/colour editor. Other episodes may reuse or omit individual
items; new styles/anchors need implementation and a checked native fixture.

The pipeline hashes selected source assets and this metadata before generation,
records dressing objects and native head attachment in the scene manifest,
packs required images, and copies selected source assets into
`dressing_assets/` in frozen deliveries. No downloaded asset is fetched again
during generation.

Native checks cover the actual saved objects, hat fit and head-following at
every sampled pose, upper-hair clearance against the actual crown mesh,
doorway clearance, floor/table support, the cup/saucer
contact, backpack route clearance and fingertips around the desk props.
Canadian flag checks also require the pinned packed PNG, connected shader
texture, unchanged artwork UV orientation and 2:1 geometry. The Canadian wall
flag sits 5 cm below the shared wall anchor to fit the interview close-up
above its header; the Austrian placement is unchanged.
Rendered inspection remains necessary for appearance and caption visibility.

The Canadian native/visual reference is
`builds/tef_canada_b1_canada_decor_review_r2/`. Its
`review/contact_sheet.jpg` compares actual wide, candidate and friend shots
with the prior B1 preview and real captions. The complete wall flag fits above
the candidate header; the desk flag is visible in the wide shot and stays
clear of sampled fingertips. `review/canada_flag_detail.png` is an inspection
camera, not an episode shot. `canada_dressing_review.json` records image hashes,
packed-source checks, three one-pose negative regressions and exact reuse of
the 72.833333-second speech/timing. No new full video was exported; all seven
earlier movies and 116 frozen delivery/source files were preserved.
