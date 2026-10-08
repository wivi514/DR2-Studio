# Asset catalogue: where things are

A map of the games' files for modders: where to look for a character, an outfit, a
texture. Paths are virtual paths ([glossary](../glossary.md)); paste them into DR2
Studio's search or a `dr2` command. Grows with each phase; corrections welcome.

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
| `data/skeleton/*.big` | The rigs (phase 3) |
| `data/audio/*.big` | Sound banks (phase 5) |

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

## Texture name endings

| Ending | Meaning | Edit it for… |
|---|---|---|
| `_cm` | colour map | colours, prints, logos |
| `_nm` | normal map (DXN or DXT1) | bumps and folds; edit with care |
| `_sm` | specular map | shininess |
| `_mask` | tint mask (clothing) | which parts get tinted |
| `_ne`, `_si`, `_rm`, `_no`, `_det`, `_om`, `_ig` | lighting / detail maps, meanings still being worked out | — |
| `AO_…`, `LM_…` | ambient occlusion / light maps of the map | baked shadows |
