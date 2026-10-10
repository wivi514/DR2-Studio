# Asset catalogue: where things are

A map of the games' files for modders: where to look for a character, an outfit, a
texture. Paths are virtual paths ([glossary](../glossary.md)); paste them into DR2
Studio's search or a `dr2` command. Grows with each phase; corrections welcome.

**Easier:** DR2 Studio's **Library** tab and `dr2 library` sort all of this by what it is
(characters, zombies, music, rigs…) with pictures, and export whole groups in one go
([`16-library.md`](16-library.md)). This page says where things are on disk.

Found something? `dr2 index textures-of <model>` lists a model's textures, and
`dr2 index used-by <texture>` the models using a texture
([`03-browsing.md`](03-browsing.md)).

## Big picture

| Folder / archive | What's inside |
|---|---|
| `data/models/npcs.big` | Every named character and **Chuck's outfits**, one model `.big` + one texture `.tex` pack each, mostly compressed |
| `data/models/zombies.big` | Zombie models and their textures (nested: `zombies.big/zombie_cop.big/zombie_cop_2.tex/…`) |
| `data/models/environment/prologue/*.big` | The Still Creek map, one archive per zone (`prologue_z01` … `z09`); `*_LOD.tex` are the low-detail far versions |
| `data/streamedassets.big` | Props and weapons loaded on demand (vending machines, food, spray paint, masks…) |
| `data/cine_props.big` | Props for cutscenes |
| `data/frontend/` | Menus and HUD: `fecmn.tex` / `ingame.tex` (icons), `loading.big` (loading-screen pictures), `str_<lang>.bcs` (text) |
| `data/preload4.big` | Things loaded at boot: default textures, colour-grading tables, a copy of `fecmn.tex`. Edit with care (see the troubleshooting guide) |
| `data/misc/textures/commoncolourcubes.tex`, `data/streamedassets.big/cc_*.bct` | Colour-grading tables (the "look" of each area), 1024×32 strips |
| `data/skeleton/*.big` | The rigs (below) |
| `data/audio/*.big` | Streamed sounds: music, voices, cutscene audio, long ambiences ([below](#sounds)) |
| `data/streamedassets.big/fx_*.big` | Sound-effect banks: recordings (`.xma`) and the effects that play them (`.sfx`) |

## Chuck (Case Zero)

Chuck's body is built from parts, each a model + texture pack in `data/models/npcs.big`:
`chest_*`, `leg_*`, `feet_*_over` / `_under`, `hands_*`, `head_*`, `headwear_*`. The
default Case Zero outfit is the `young_chuck` set:

| What | Texture |
|---|---|
| Orange "04" raglan shirt (default) | `data/models/npcs.big/chest_young_chuck.tex/young_cr_shirt_cm` (1024×1024 DXT1) |
| Arms | `…/chest_young_chuck.tex/young_cr_arms_naked_cm` |
| Jeans | `data/models/npcs.big/leg_young_chuck.tex/young_cr_pants_cm` |
| Face, hair | `head_young_chuck.tex`, `headwear_young_chuck.tex` |
| Watch | `…/chest_young_chuck.tex/watch_cm` (also in `hands_young_chuck.tex` and `streamedassets.big/fe_watch.big`) |

The other outfits you can find in game have their own sets: `chest_Hunting_Jacket_Orange_Vest`,
`chest_Bowling_Shirt_Jeans`, `chest_Greasy_Overall_Plaid_Shirt`, `chest_Diner_Waitress_Outfit`,
`chest_Plaid_Suit_Brown_Shirt_Tie`, hats under `headwear_*`, shoes under `feet_*`.

`chest_default.tex/cr_jacket_cm` is the **yellow IJIEK racing jacket**, Chuck's outfit in
Dead Rising 2 and Case West. Case Zero ships it too, but its Chuck doesn't start in it.

## Chuck and Frank (Case West)

| What | Texture |
|---|---|
| Chuck's default IJIEK jacket | `data/models/npcs.big/chest_default.tex/cr_jacket_cm` |
| Frank West's default jacket, shirt | `data/models/npcs.big/chest_default_frank.tex/frank_west_epi_jacket_cm`, `…/frank_west_epi_shirt_cm` |

## Skeletons (rigs)

`data/skeleton/` holds each rig family in several files: `<family>fullbody.big` is the
whole rig, and `…root`, `…upperbdy`, `…hand`, `…face` are the parts animations drive
separately. `cine<family>.big` are the cutscene versions. Bone names are shared across
families (`dummy01.l_upperarm`, `dummy01.r_thumb1`, `dummy01.jaw` …).

| Family | Full rig | Bones | For (measured 2026-10-09: each character's bones matched to the rigs, CZ / CW) |
|---|---|---|---|
| `player` | `playerfullbody.big` | 98 | Chuck and Frank: every outfit part, and most men (66 / 145 characters) |
| `female` | `femalefullbody.big` | 98 | women (13 / 19) |
| `large` | `largefullbody.big` | 98 | big men (2 / 1) |
| `child` | `childfullbody.big` | 98 | Katey (1 / 0) |
| `longcloak` | `longcloakfullbody.big` | 112 | characters with long coats, 14 more bones (0 / 1) |
| `zombie` | `zombiefullbody.big` | 30 | zombies (a light rig): every zombie variant, with its own proportions, and the cutscene zombies |
| `tiger` | `tigerfullbody.big` | 64 | the tiger (both games ship the rig) |
| `camera`, `stage`, `prop` | | 1 / 1 / 50 | cutscene camera, stage origin, and 50 prop slots (`prop01` …) for cutscene props |

A model carries its own copy of its rig (a character `.big` lists its 98 bones too), so a
`.glb` export is complete on its own. The families share their bone names and differ in
proportions; DR2 Studio's details and `info.txt` (*Export all…*) name the rig a model
matches ([`16-library.md`](16-library.md)). `dr2 info <model>` shows which bones each draw uses.

## Models

| Where | What |
|---|---|
| `data/models/npcs.big/<name>.big` | characters and outfit parts; textures in `<name>.tex` next to it. Whole NPCs: `boss_mechanic`, `cast_katey_pro_t1`, `cine_soldier` … |
| `data/models/zombies.big/<type>.big/<type>_<n>.big` | zombie variants |
| `data/streamedassets.big/<Item>.big/<item>.big` | weapons and props, often with a few bones (doors, wheels, blades) |
| `data/cine_props.big/<prop>.big/<prop>.big` | cutscene props (the bike, the ambulance doors …) |
| `data/models/environment/<area>/<zone>.big/<piece>.big/_COMP_<piece>.big` | level pieces, with shared ("combined") vertex buffers |

## Texture name endings

| Ending | Meaning | Edit it for… |
|---|---|---|
| `_cm` | colour map | colours, prints, logos |
| `_nm` | normal map (DXN or DXT1), OpenGL-style (green up) | bumps and folds; edit with care |
| `_sm` | specular map: the colour of the shine | shininess |
| `_mask` | tint mask (clothing) | which parts get tinted |
| `_ne`, `_si`, `_rm`, `_no`, `_det`, `_om`, `_ig` | lighting / detail maps, meanings still being worked out | — |
| `AO_…`, `LM_…` | ambient occlusion / light maps of the map | baked shadows |

## Sounds

Every sound is an `.xma` (search Studio with the kind box on **audio**). Click one to
play it; the Related list says which `.sfx` and game events use it.

| Where | What | Notes |
|---|---|---|
| `data/audio/music.big` | Music: 16 tracks in CZ (title `PressStartPrologue`, `HB_Indemnify`, the Celldweller boss track `Celldweller_TheBestItsGonnaGet` and its `_Vox` version, `KillTheSound_EndCredits1`…), 35 in CW (title `PressStartDR2`, `CommanderBattle`, `Sting*` cues…) | stereo |
| `data/audio/cinematics.big` | Cutscene audio, numbered (`39694.xma` is Case Zero's 5-minute prologue) | 5.1 (6 channels) |
| `data/audio/charvocals.big`, `chuck.big`, `bossvocals.big` | Voice lines, numbered (the dialogue tables use numbers only) | mono |
| `data/audio/ambience.big`, `streamfx.big` | Long ambiences and streamed effects (pay phone message, crowd chants, the PA broadcast) | mono / stereo |
| `data/streamedassets.big/fx_main.big` | Common effects: UI beeps (`FEError.sfx` → `cursorError43a_01a.xma`), hits, splats, Chuck's grunts | mono |
| `data/streamedassets.big/fx_ftsp*.big` | Footsteps by shoe type (`fx_ftspsneaker`, `fx_ftsphighheel`, `fx_ftspboots`…) | mono |
| `data/streamedassets.big/fx_zombie*.big` | Zombie voices, one bank per zombie voice set | mono |
| `data/streamedassets.big/fx_<weapon or vehicle>.big` | Each weapon's and vehicle's sounds (`fx_superbike`, `fx_chefknife`, `fx_propanetanknails`…) | mono |
| `data/audio/Prologue.txt` (CZ), `data/audio/*.txt` (CW) | The audio scene scripts: which events play which sounds. **Don't edit** (checked by the game) | text |

## Text

All on-screen text is in the string banks ([`11-text.md`](11-text.md)); find a string
with Studio's filter or `dr2 strings search <words>`.

| Where | What | Notes |
|---|---|---|
| `data/frontend/str_en.bcs` … `str_ko.bcs` | Every on-screen string in one language: English, French, Italian, Spanish, Japanese, Korean. 7,599 strings in CZ, 2,469 in CW | Change them with a `.bcs.json` |
| `data/frontend/str_id.bcs` | The label of every string (`IDS_PRESS_START`) | Read-only reference |
| `data/frontend/str_lg.bcs` | Legal and before-language-select text, mixed languages | |
| `data/datafile.big/*.txt` | Game data and scripts: zombie effects, items, missions, the scene graph | Edit as text ([`11-text.md`](11-text.md#steps-edit-a-text-file)) |
| `data/*.csv`, `data/**/*.ini` (CW) | Loose tables and settings | Text |

What the id ranges hold in Case Zero, going by the labels (`dr2 strings search IDS_`):

| Ids | Mostly |
|---|---|
| 1-9,999 | Menus, loading tips, store and map names, skill and combo-card text, level-up messages |
| 10,000-49,999 | Dialog boxes, options, online and save/load messages, HUD |
| 50,000-59,999 | Item display names (`IDS_DISPLAY_NAME_…`), button prompts in the world |
| 60,000-79,999 | Tutorials, survivor conversations, phone calls, Zombrex dialogue |
| 80,000-89,999 | Character names, achievements, some subtitles |
| 90,000-99,999 | Cutscene subtitles (`IDS_SUBTITLE_…`), font tests |

Files the game checks and that can't be changed: `data/audio/Prologue.txt` (CZ);
`data/audio/Safehouse.txt`, `scenegraph.txt`, `audiomixer.txt`, `curves.txt`,
`data/controls/padmap.txt`, `data/models/zombies/zombie_pdv_variations.txt` (CW).

## Movies (Case West)

| File in `data/movies` | What | Notes |
|---|---|---|
| `800a_intro.bik` | The opening movie, 39 s | 1280×720, 5.1 sound |
| `dr2_logo.bik`, `dr2_logo_b.bik` | The Dead Rising 2 logo, 10 s | 1280×720, 5.1 sound |
| `DR_LOGO_shortLoop.bik` | A 4 s logo loop | stereo |
| `807_monitors.bik` … `816_monitors.bik` | Security-monitor loops of the labs, 25-114 s | 512×512, no sound |

Play and export them in Studio or with `dr2 extract --mp4` ([`04-extracting.md`](04-extracting.md)).

