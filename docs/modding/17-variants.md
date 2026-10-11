# Choose what a zombie wears: variants

**You will:** pick a zombie's head, hat, shirt, trousers, shoes and clothing colours,
see that look in 3D, and export it the way you need: just that look, or every part
sorted into groups for Blender.   **Time:** ~5 min.   **Games:** both.
**You need:** DR2 Studio and a built index ([`03-browsing.md`](03-browsing.md)); Blender
4.2 or newer for the Blender part ([`07-blender-setup.md`](07-blender-setup.md)).

## Why a zombie has many looks in one file

One zombie model holds **every look at once**: `zombie_skinny_2` has four heads, two
hats, four shirts, three pairs of trousers, a burnt version, and the *wound caps* the game
shows where an arm or the head has come off. The game never shows all of that: it picks
**one choice per slot** for each zombie (head 2, no hat, shirt 3, trousers 1…) and hides
the rest. That is how a crowd of the same zombie looks varied.

How does the game know which part is which? From the **part names**: `head2_headShape`
is head 2, `chest_shirt3Shape` is shirt 3, `headwear2Shape` is hat 2. A table inside the
game lists the name patterns (the toolkit has a copy). So DR2 Studio can sort the parts
exactly the way the game does. The words, in plain terms ([glossary](../glossary.md)):

| Word | Means | Example |
|---|---|---|
| **Slot** | Something the game picks one of | Head, Headwear, Shirt, Trousers, Skirt, Feet, Tall boots, Head tumour (Case West's gas zombie) |
| **On/off part** | A part that is shown or not | Wound caps, Burnt, Bare arms, Glasses, Chest accessories |
| **Colour choice** | Other colours for one piece of clothing | `jersey` has its own colours and 5 more |
| **Detail level** | The same zombie in another file, simpler, for when it is far away | `zombie_cop_2` (high), `_3` (medium), `_4` (low) |
| **Prop state** | A prop's other look kept in the same file | a slot machine's damaged logo, its win screen |

Before this was added (phase 9), DR2 Studio and the exports showed every part on top
of each other: a zombie wearing all its shirts at once.

## Steps: choose a look and see it

1. In the **Library** (left), open **Models → Zombies & enemies** and click a zombie, for
   example **zombie_skinny → Zombie Skinny**. Each zombie is **one** item now: its
   medium and low detail files are inside it (step 5).
2. The 3D view shows the **default look**: the first head, the first shirt, the first
   trousers…, glasses and accessories on, no wound caps, not burnt, its own colours.
   The **Variants** panel on the right of the 3D view lists what this zombie can wear.
3. Change **Head**, **Headwear**, **Shirt**, **Trousers**, **Feet**: the 3D view changes at
   once. Choose **none** to take a part off (a hat, for example).
4. Change a **Colour** drop-down (the little square shows its main colour): the model is
   re-coloured after a second or two (the colours are computed, "baked", from the
   game's own numbers: [`14-texturing-tools.md`](14-texturing-tools.md)).
5. **Detail** switches to the medium or low detail file of the same zombie (the game
   draws those further away). The look you chose follows, as far as that file has it
   (the low detail files have no separate heads).
6. Buttons: **Default** goes back to the default look, **Random** picks any look (as the
   game might), **Show everything** shows every part at once, to see what the file
   holds. Tick boxes switch **Wound caps**, **Burnt**, **Bare arms**… on and off.

The panel's last line says how many parts are shown and the game's own **hide mask** for
that look (a number: useful to compare with what the recomp reports; you can ignore it).

Props that keep states as parts (the casino's slot machines) get the same panel with
**Damaged**, **Far-away copy**, **Win screen** and **Screen off**. Most props don't
have any: a damaged cash register is a separate file (`cashregister_dmg.big`).

## Steps: export it the way you need

| You want | Click | You get |
|---|---|---|
| Just this look, for Substance Painter, a picture, or a mod of one look | **Export .glb…** | a `.glb` with only the parts and colours you chose |
| Everything, organised, for Blender | **Open in Blender**, or **Export all…** | every part, each in a collection named after its group (*Head 1*, *Head 2*, *Shirt 3*, *Wound caps*…); the parts your look doesn't show are hidden, and the colour choices are in Blender's **glTF Variants** tab |
| A whole group (all zombies) | **Export…** under the Library grid | every zombie, every detail level, each with every part organised, in its default look |

In Blender, after **Open in Blender** (or *File → Import → glTF 2.0* of an *Export all*
`.glb` with the DR2 add-on's **Import**):

- The **Outliner** (top right) shows the zombie's collection, and inside it one
  collection per group. Click the **eye** next to a part or a collection to show or hide
  it. (A plain *File → Import* without the DR2 add-on shows every part; their
  **Object Properties → Custom Properties** still say `dr2_group` and `dr2_shown`.)
- **Colours:** open the side panel (`N`) → **glTF Variants** tab (Blender 3.3 or newer)
  and click a choice (*jersey 3*). Use **Material Preview** (`Z`) to see it.
- **Export all…** also writes, in `textures/colours/`, each colour choice baked to a
  plain colour picture (`zombie_skinny_mtl_jersey_3.png`, `_0` is its own colours), and
  `info.txt` lists the slots, the choices and the look used.

## Putting a changed zombie back (mods)

Edit it as any model ([`08-edit-a-model.md`](08-edit-a-model.md)): **Open in Blender**,
change parts, then in the DR2 tab **Check rig** and **Export to mod**.

- **Hidden parts are left as they are.** Export to mod sends what is visible; the game's
  file keeps every other part unchanged. So you can change shirt 3 without touching the
  others: show it, hide the rest, export.
- An **Export .glb…** of one look, edited and put back with **Replace with .glb…**, works
  the same way: `dr2 model check` says *"exported as one look: the N part(s) of the
  other looks are kept as they are"*.
- **Keep the part names.** The game recognises a part by its name. A part renamed in
  Blender no longer matches (the check says *matches no shape*), and new parts can't be
  added yet.

## The same from the command line

```
dr2 variants data/models/zombies.big/zombie_skinny.big/zombie_skinny_2.big
dr2 variants data/models/zombies.big/zombie_skinny.big/zombie_skinny_2.big --variant head=3,shirt=2 --parts
dr2 extract --glb --variants shown --variant "head=3 shirt=2 colour.jersey=4" \
    data/models/zombies.big/zombie_skinny.big/zombie_skinny_2.big -o out
dr2 export zombies -g cw -o exports                      # every part, organised
dr2 export data/models/zombies.big/zombie_gas.big/zombie_gas_2.big -g cw -o exports \
    --variant head=2,tumour=none
```

- `dr2 variants` lists the slots (`Head (head): 1, 2, 3, 4 or none`), the on/off parts,
  the colour choices (`Colour jersey: own + 5 choices`) and, with `--parts`, every part
  with its group and whether the look shows it.
- A look is written `key=value`, separated by spaces or commas: `head=2`, `headwear=none`,
  `burnt=on`, `colour.jersey=4` (`0` = own colours), `damaged=on`; `default` and
  `everything` are words too. Anything you don't say keeps its default.
- `--variants all` (the default) writes every part organised; `--variants shown` only the
  chosen ones.

## If something went wrong

| Symptom | Cause | Fix |
|---|---|---|
| A zombie still wears everything | The index is older than the toolkit (pictures) or **Show everything** is ticked | **Build / refresh index**; untick **Show everything** |
| No **Variants** panel | The model has no choices (most models: people, props) | Nothing to choose: the game draws every part |
| *"head=5: this model has head 1, 2, 3, 4"* | That zombie has fewer heads | `dr2 variants <model>` lists what it has |
| A far soldier (CZ `zombie_soldier_3`) or security guard (CW `zombie_security_2`/`_3`) shows a part on every look | The game's file names that part with its number in the wrong place (`headwearShape2Deformed`); the game reads it without its number and draws it always | The toolkit reads it as meant and says so (`dr2 variants`, `dr2 model check`); the name can't be changed by a mod |
| In Blender every part shows | Imported without the DR2 add-on or Open in Blender | Hide parts with the eye icons, or re-import with the add-on |

## What is not known yet

- **How the game picks** each zombie's look (which head, which colours). The toolkit's
  default is the first of each slot; **Random** picks evenly. When the game's rule is
  found, the default will follow it.
- **Case West's colours.** Case West ships colour choices for its zombies but an empty
  list of them; whether its game uses them is still to check in game. The toolkit offers
  them (found by their names).

## Going further

- [`16-library.md`](16-library.md): the Library and Export all.
- [`08-edit-a-model.md`](08-edit-a-model.md), [`13-blender-addon.md`](13-blender-addon.md):
  editing and putting models back.
- For the curious: [`formats.md` §Variants](../formats.md#variants-which-parts-and-colours-a-model-shows-)
  has the game's table and how it was found.
