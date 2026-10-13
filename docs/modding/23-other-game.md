# Use the other game's items: Case West's in Case Zero, Case Zero's in Case West

**You will:** put an item of the other game (Case West's Laser Sword in Case Zero, a Case
Zero item in Case West) into your mod, with everything it needs, and place it in a level.
**Time:** ~5 min.   **Games:** both, **and you need both games' data** on your computer.
**You need:** the toolkit with **both** game folders set
([`02-game-data.md`](02-game-data.md): **Game folders…** in DR2 Studio) and a mod
([`06-mod-packages.md`](06-mod-packages.md)).

> Phase 15, started 2026-10-12. Every item of each game plans into the other with no
> name left unresolved (`dr2 census --import`), and a mod with one builds. **Not yet seen
> in game**: the in-game tests U1-U3 (does a brought item's model draw with its own
> game's shaders, do its moves play, do its sounds play) are next. Until they pass,
> treat an imported item as an experiment and keep a copy of your save.
>
> **Known limit (2026-10-12):** the game keeps room for only about **26** extra pixel
> shaders in Case Zero (3 in Case West), and one Case West weapon brings ~45. Until the
> recomps grow that room, a mod whose item brings more **crashes while loading**
> ("Shader constant set overflow" in the log). The report lists how many each item
> brings.

## Why both games are needed

A mod made with the toolkit never contains the games' files (that's what makes it safe to
share). An imported item is a **recipe**: "copy the Laser Sword's model from Case West".
The recipe is followed on the computer that builds the mod, from **its own** copy of Case
West. So whoever plays your mod needs both games, and the mod says so: DR2 Studio and
`dr2 mod info` show *Made from Case West's files* ([guide 06, What a mod
needs](06-mod-packages.md#what-a-mod-needs)).

## What comes with the item

Both games run the same engine, so models, textures, sounds and animations cross over as
they are. What differs is which **names** each game knows. The importer goes through
every setting of the item (its block of `items.txt`) and decides, for each name:

| What | What happens |
|---|---|
| The model | copied from the other game, drawn with **that game's own shaders**, which are copied into this game's shader banks under new names (the two games compiled their shaders differently) |
| Its moves (`AnimBankName`) | the other game's move bank is copied when this game lacks it |
| Its sounds (`AudioFilename`) | the other game's sound bank is copied when this game lacks it |
| Its name and texts | new text numbers in your mod; the words are read from the other game's text when the mod is built, in every language |
| Effects (fire, sparks…) | matched **by name**: the two games number them differently after 370. An effect this game doesn't have is left off (listed) |
| Other items it names (a combo's two items, a weapon's pieces) | kept if this game has them, otherwise imported too |
| A combo card | its picture copied, its card number changed if this game uses it |
| Parts this game's program doesn't know (Case West's `cExternalLocatorItem`, `cTurretInfoItem`…) | left out, listed: Case Zero's program couldn't build them |
| A model this game has under the same name (`clothesbox`, `bowieknife`) | this game's own copy is used: it is the same object |

The window shows this list for the item you pick before anything is written.

## Steps

### In DR2 Studio

1. Open your mod (**Open mod…** / **New mod…**) and pick the game it is for (the game
   box in the toolbar): this is the game the item goes **into**.
2. Click **Other game's items…** (under the mod's buttons).
3. Type part of the name in the filter (`laser`), click the item. The right side says what
   comes with it: what is brought, renumbered or left out, and why.
4. Click **Add to mod**. The mod now holds the recipes, the item's block of `items.txt`
   and the text copies; its `mod.toml` says it needs both games.
5. Place it: **Maps** tab → **Add item…** → type its name (`LaserLightSword`)
   ([guide 19](19-edit-a-level.md)).
6. **▶ Play**.

### With the `dr2` command

```
dr2 mod import-item my_mod LaserLightSword --from cw -g cz -n   # only say what it does
dr2 mod import-item my_mod LaserLightSword --from cw -g cz      # add it to the mod
dr2 level edit my_mod prologue add "cItemPlacement MyLaser" ItemName=LaserLightSword Location=-278.5,3.39,-36.5
dr2 mod info my_mod                                              # it needs both games
dr2 play -g cz
```

## Check it worked

`dr2 mod info my_mod` lists *Made from Case West's files*; `dr2 mod build my_mod -g cz -o
out` builds without errors. In game, the item lies where you placed it.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| `… needs Case West's game data on this computer` | The other game's folder isn't set | **Game folders…** in Studio, or `dr2 games set cw <folder>` |
| `Case Zero already has an item named X` | Both games have it | Use this game's own (place it from the Maps tab) |
| The window says *This window needs both games' data* | Same as the first row | Same fix |
| An effect is missing on the weapon | The report says *Case Zero has no effect …* | Pick one of this game's effects for it ([guide 21](21-effects.md)) |

## Going further

- What a mod needs, and the `requirements.json` a launcher reads:
  [guide 06](06-mod-packages.md#what-a-mod-needs).
- How it works, for developers: `dr2kit/mods/importitem.py`,
  `dr2kit/convert/shadercarry.py`, [`formats.md`](../formats.md) §"Across the games:
  shader banks", [`phase15-kickoff.md`](../phase15-kickoff.md).
