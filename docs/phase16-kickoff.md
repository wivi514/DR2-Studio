# Phase 16 kickoff: things and maps from Dead Rising 2 and Off the Record (PC)

> **Status 2026-10-12 (night): first research, not started.** After phase 15, whose
> import machinery (source games, cross-game tables, the importer and its checker,
> requirements) phase 16 reuses.

**Direction (user, 2026-10-12):** "for phase 16 pretty much the same thing, but able to
import from the PC version of Dead Rising 2 and Off the Record."

## What a first look found (2026-10-12)

The user owns both on Steam (`~/.local/share/Steam/steamapps/common/Dead Rising 2`, 6.5
GB; `…/Dead Rising 2 Off the Record`, 6.7 GB). They are **sources only**: the toolkit
reads them to make mods for Case Zero / Case West; it never writes them.

* **Same layout** as the console games: `data/datafile.big`, `streamedassets.big`,
  `models/`, `anim/`, `audio/`, `shaders/`, `skeleton/`… (DR2 850 files, OTR 902).
* **`.big` archives:** the index reads with the toolkit's reader as it is. Compressed
  entries (flag 1, `datafile.big`'s every entry) are **zlib behind a 4-byte big-endian
  uncompressed size** (console: LZX).
* **Payloads are little-endian** (PC): a skeleton node record is the console's record
  byte-swapped (`dummy01`, `dummy01.arrow`… the same names and rig). Every format needs a
  PC reading (byte order per structure, CLAUDE.md rule 1), then a writer to the console's.
* **Textures:** the `.bct` header differs from the console's (first byte `00` instead of
  `05`; PC formats, not tiled ❓). Models: PC vertex declarations ❓. Audio: `data/audio`
  banks (`.big`), format ❓. Animations: probably the same layout byte-swapped ❓.
* **Text files** (`items.txt`, levels, missions) are plain text, read as they are.

### Case Zero is already Dead Rising 2's program, with DR2's slots

Phases 14 and 15 found that Case Zero's executable still lists **Dead Rising 2's 82
level slots** and **32 zombie types**. Dead Rising 2 PC's level folders are **exactly
those slot names**: `americana_casino`, `arena_backstage`, `arena_stadium`,
`atlantica_casino`, `boss_battle_KCOT`, `boss_battle_train`, `food_barn`,
`fortune_exterior`, `laboratory`, `main_menu`, `palisades_mall`, `royal_flush`,
`safehouse`, `south_plaza`, `tape_die`, `underground`, `yucatan_casino`. So a DR2 map
goes into Case Zero **under its own name**, and DR2's zombies (`zombie_bride`,
`zombie_cheerleader`, `looter`, `mercenary_*`…) into **their own type slots**: the most
natural import of all three phases. Its bosses (psychopaths: `boss_boykin`, `boss_chef`,
`boss_diva`… models in `npcs.big`; DR2's `battle_*.txt` files) meet Case Zero's
program's DR2 code: what remains of it is the big unknown (in-game tests).

Off the Record adds `theme_park` (Uranus Zone) and Frank West; it has no slot in either
console program, so it goes into a free slot under another name (phase 15's way).

Case West (10 slots, 10 zombie types) takes DR2 / OTR things the phase 15 way: mapped
types, `w_mall`.

## Plan (sketch)

1. PC readers: `.big` zlib entries; byte-swapped scene, vertex, texture (PC → console
   texture conversion: decode, then the toolkit's encoder and tiler), animation, audio
   (decode → the recomps' PCM substitution, phase 5, or re-encode), each with a census
   over every file of both PC games (CLAUDE.md gates).
2. Game profiles for the PC games as **sources** (`dr2pc`, `otrpc`), found through Steam's
   library folders on every OS (`platformdirs`), never shipped data.
3. Phase 15's importer with the PC games as sources; requirements naming them (Steam app
   ids instead of title ids).
4. In-game tests first, as always: a DR2 weapon in Case Zero, a DR2 zombie type in its own
   slot, a small DR2 level (`food_barn`) in its own slot, a psychopath.

## Questions for the user (when it starts)

* Which PC versions exactly (Steam's current builds; the GOG ones?), and whether mods may
  require them (the player must own them, as with Case West in phase 15).
* Off the Record's own things first, or Dead Rising 2's?
