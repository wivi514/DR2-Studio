# Change in-game text, translations and game data files

**You will:** change what the game says (a menu label, a subtitle, an item description)
in any language, and edit the game's text data files (zombie stats, item tables), with a
view of exactly what you changed.   **Time:** ~10 min.   **Games:** both.
**You need:** the toolkit pointed at your game ([`02-game-data.md`](02-game-data.md)), an
up-to-date index (DR2 Studio: **Build / refresh index**), and a recomp to see it in game.

Two kinds of text live in the games:

- **Strings**: everything shown on screen. They sit in one **string bank** per language
  (`data/frontend/str_en.bcs` for English, `str_fr` French, `str_it` Italian, `str_es`
  Spanish, `str_ja` Japanese, `str_ko` Korean). Each string has a number, its **string
  id**, and a developer name, its **label** (`10611` = `IDS_PRESS_START`). Your mod lists
  only the strings it changes; several mods can change different strings of the same
  bank.
- **Text files**: the game's own data and scripts, mostly in `data/datafile.big`
  (`zombie_effects.txt`, item and mission tables) and, in Case West, loose `.csv` and
  `.txt` files. Your mod holds the whole edited file.

## Steps: change a string

### In DR2 Studio

1. Open or create a mod at the bottom (**Open mod…** / **New mod…**).
2. In **Browse**, open `data` → `frontend` and click `str_en.bcs` (English). The middle
   shows a table: **id**, **label**, **text**.
3. Type in the filter box to find a string, by its text (`press start`), its label
   (`IDS_PRESS_START`) or its id (`10611`).
4. Double-click the text, type the new one, press Enter. The row turns yellow (hover it
   to see the game's text), the log says `en string 10611 → '…'`, and the mod's file
   list shows `data/frontend/str_en.bcs.json`. Notes under the table warn you when the
   new text breaks a rule (below).
5. To undo one string: select its row and click **Revert string**.
6. **▶ Play**: the recomp starts and the title screen says your text.

### With the `dr2` command

```
dr2 strings search press start                 # 10611  en  IDS_PRESS_START  PRESS START
dr2 strings show IDS_PRESS_START               # the same string in every language
dr2 strings set my_mod IDS_PRESS_START "PRESS START TO SURVIVE"
dr2 strings set my_mod 10611 "HOLA" --lang es  # another language
dr2 strings unset my_mod 10611                 # drop a change
dr2 mod check my_mod -g cz
dr2 mod deploy my_mod -g cz
```

`dr2 strings search` looks in English unless you add `--lang fr` (or `--lang all`);
`-g cw` searches Case West. `dr2 strings export --lang all -o strings/` writes every bank
as JSON, to read or to start a translation.

### The mod file

`dr2 strings set` and Studio write `replace/data/frontend/str_<lang>.bcs.json`. You can
also write it yourself; only `"strings"` matters (ids or labels), the rest is a reminder:

```json
{
 "format": "dr2kit strings v1",
 "bank": "data/frontend/str_en.bcs",
 "strings": {
  "10611": "PRESS START TO SURVIVE",
  "IDS_START_DEMO": "PLAY"
 }
}
```

### Rules for a string

- **Colours and icons need a leading `@`.** `@Find [00CC00FF,Zombrex] for Katey` draws
  "Zombrex" in green; `[@x_button_ig]` draws the X button. Without the `@` at the start,
  the brackets are printed as they are. The colour is red, green, blue, opacity in hex
  (`FF0000FF` is red).
- **Keep the `%` codes.** `%s`, `%d`, `%1`… are where the game puts a name, a number or a
  time. Dropping or adding one can show garbage or crash; the toolkit warns you.
- `\n` (in JSON, or typed as `\n` in `dr2 strings set`) starts a new line.
- Accented letters and other alphabets work (the banks are UTF-8), as long as the game's
  font has them: Japanese and Korean fonts exist for those languages.
- New ids are allowed only below the last id of the bank, and nothing shows them until a
  layout or script names them. Changing existing strings is the normal case.

## Steps: edit a text file

### In DR2 Studio

1. Open or create a mod.
2. Find the file: **Search** for `zombie_effects`, or browse `data/datafile.big`.
3. The middle is an editor. Change what you want (`EFFECT_CONDITION_SWIPE_AT_PLAYER =
   "162"` → `"262"`), then **Save to mod**. The mod's file list shows
   `data/datafile.big/zombie_effects.txt`.
4. Click **Changes** to see a diff: red lines are the game's, green lines yours. Click it
   again to go back to editing.
5. **Revert to the game's** removes your copy from the mod.
6. **▶ Play**.

Without an open mod the text is read-only. A few files are locked (below).

### With the `dr2` command

```
dr2 extract data/datafile.big/zombie_effects.txt -o work
# edit work/data/datafile.big/zombie_effects.txt in any text editor, then:
mkdir -p my_mod/replace/data/datafile.big
cp work/data/datafile.big/zombie_effects.txt my_mod/replace/data/datafile.big/
dr2 mod check my_mod -g cz && dr2 mod deploy my_mod -g cz
```

The file under `replace/` replaces the game's file as a whole. If the original was
compressed in its archive, the build compresses yours too.

### Files you can't change

The game checks a few files against a fingerprint stored in its program and **crashes**
on an edited copy. The toolkit refuses them (`dr2 mod check` says why; Studio opens them
read-only):

- Case Zero: `data/audio/Prologue.txt`
- Case West: `data/audio/Safehouse.txt`, `data/audio/scenegraph.txt`,
  `data/audio/audiomixer.txt`, `data/audio/curves.txt`, `data/controls/padmap.txt`,
  `data/models/zombies/zombie_pdv_variations.txt`

## Check it worked

- `dr2 mod check my_mod -g cz` lists `strings  data/frontend/str_en.bcs` (or `raw  …`
  for a text file) and "OK".
- In game, the string reads as you wrote it (the in-game check changed the title
  screen's PRESS START in both recomps).
- The recomp's log (or terminal) says `str_en.bcs served from the MODS overlay`.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| The brackets show on screen: `[00CC00FF,Zombrex]` | The string doesn't start with `@` | Put `@` first. |
| `id … is not in the bank, and new ids must be below its last id` | You used an id that doesn't exist | Find the string's real id with `dr2 strings search`. |
| `… is neither a string id nor a known label` | A typo in the label | `dr2 strings search IDS_` + part of it. |
| `changed by both a and b at the same priority` | Two mods change the same string | Order them in the mod manager ([`06-mod-packages.md`](06-mod-packages.md)), or raise one's `priority`. |
| `replaces … as a whole and … changes strings in it` | One mod has a whole `str_en.bcs`, another a `.bcs.json` | Use `.bcs.json` in both. |
| `the game checks … against a digest` | A locked file (above) | It can't be modded. |
| My text shows in English only | You changed `str_en` | Change each language's bank (`--lang fr` …). The game uses the language set in the recomp's launcher. |
| Keyboard prompts ("PRESS ENTER") went back to pad wording | The recomp's keyboard layer (`game_kbm`) also edits `str_en.bcs`, and a deployed string mod's bank is used instead (deploy prints a warning) | Known limit: with a string mod installed, the keyboard wording of the English bank is the shipped one. |

## Going further

- Several mods at once, load order, sharing: [`06-mod-packages.md`](06-mod-packages.md).
- The string bank format: [`../formats.md`](../formats.md) §Strings; the locked files:
  §Digest-checked files.
- Where texts are: [`asset-catalogue.md`](asset-catalogue.md) §Text.
