# See the game's levels in 3D: the Maps tab

**You will:** open a level (Case Zero's Fortune City street, Case West's labs…), fly
through it, switch on spawn points, zombie areas, map areas and more, click anything to
see what it is and where it comes from, and export a zone or a whole level for Blender.   **Time:** ~5 min.   **Games:** both.
**You need:** DR2 Studio ([`01-install.md`](01-install.md)) with your game folders set.
A built index helps (*Open in Library* needs it), but the Maps tab works without one.

## What a level is made of

A **level** is one place you can walk around. The game builds it from three kinds of
things ([glossary](../glossary.md)):

| What | Where it comes from | Example |
|---|---|---|
| **Pieces** | the level's **zones**: big archives the game loads as you move, each holding its building parts and a list of where each part goes | the bowling alley's walls, lanes and sign are 19 pieces of zone `prologue_z05` |
| **Items and doors** | the level's text file in `datafile.big` (`prologue.txt`) | 891 items in Case Zero's street: chairs, bottles, the bowling balls, weapons |
| **Markers** | the same text files | spawn points (where Chuck appears), zombie areas, map areas ("Junkyard"), triggers (doors to other levels), the navigation mesh (where zombies can walk) |

DR2 Studio puts all of these together the way the game does. The walls and floors also
get their **baked lighting** (each piece has a *lightmap*: shadows painted in advance)
and the **blended floors** (sand and gravel mixed through a mask), so it looks like the
game, not like grey boxes.

## Steps: open a level and look around

1. In DR2 Studio, pick the game at the top (**Case Zero** or **Case West**), then click
   the **Maps** tab on the left (next to **Library**).
2. Click a level, for example **Fortune City (the street) (prologue)**. The view opens at
   the level's start (where Chuck appears), and the parts load around you: the nearest
   first, with small textures far away and full-size ones near you.
   The **first time** you open a level this takes one or two minutes (DR2 Studio converts
   each zone once and keeps it); after that it opens in seconds.
3. Look around: **drag** with the left mouse button. Move: **W A S D** (or the arrow
   keys), **Q / E** to go down and up, hold **Shift** to go faster, and turn the **mouse
   wheel** to change your speed. Right-drag turns around the last thing you clicked.
   Click in the view first if the keys don't respond.
4. **Go to** (the **Map** panel, right) jumps to a spawn point, a map area ("Junkyard",
   "Cafeteria"), a map point (workbench, save point) or a zone. In the list on the left,
   open a level and double-click a zone to fly to it. The **Hierarchy** panel (left,
   under the list) lists everything in the level, buildings with their parts and collision
   inside: type a name in its filter and click a row to fly there.

## Arrange the windows

Every panel of DR2 Studio is a window of its own: **Browse**, **Viewer**, **Level (3D)**,
**Details**, **Map**, **Inspector**, **Hierarchy**, **Place** and **Mod and log**.

- **Resize** one by dragging the line between two panels.
- **Move** one by dragging its title bar to another side; drop it on another panel's title
  to stack them as tabs.
- **Its own window:** drag it out of DR2 Studio, or click the small window button at the
  right of its title bar (double-click the title to put it back). The 3D level on a second
  screen and the Inspector beside it is a good layout for editing.
- **Windows** (toolbar) shows or hides each panel, **Put every window back** docks them
  all, and **Reset layout** returns to how DR2 Studio started.

DR2 Studio remembers your layout. The Maps panels show while the **Maps** tab is chosen and
the Viewer and Details otherwise; a panel you dragged out as its own window stays open.

## Steps: layers, and what is this?

5. **Layers** (the **Map** panel) switch each kind of thing on and off. On at first: the
   buildings, items and doors, spawn points (green arrows: the way Chuck faces), map
   areas (blue outlines with their names) and map points. Off at first, tick them when you
   need them:
   - **Zombie areas** (red): the floor shapes the game fills with zombies.
   - **Triggers** (pink): doors to other levels and other places where pressing a button
     does something; a door to another level shows its name (*→ LEVEL_PROLOGUE_SAFEHOUSE*).
   - **Zombies**: the crowds the game's missions put in each zombie area (`missions.txt`),
     as example figures: the right types and numbers per area (up to 12 each), in a
     few of each type's looks, standing in their rest pose (arms out). The game spreads
     and dresses them itself while you play, so the exact spots differ. Click one to see
     its type and the mission that puts it there.
   - **Navigation mesh** (green): where zombies and survivors can walk.
   - **Collision** (see-through orange, edges drawn): the invisible walls and floors the
     player and zombies bump into, the game's *collision mesh*. It is simpler than what
     you see (a tree is a rough cone, a shop a few boxes), and it shows where an invisible
     wall stops you or where you can stand on a roof. Untick *Buildings* to see it alone.
     A handful of Case Zero shapes are left out because where they go isn't known
     (`dr2 census --levels` names them).
   - **Lighting areas** (yellow), **Sound areas** (cyan boxes: which echo applies where)
     and **Acoustics points**.
6. **Items and markers from:** some levels have more than one set of items. Case Zero's
   street has the story's (`prologue`) and the safehouse's (`prologue_safehouse`).
7. **Click** anything: the **Map** panel says what it is (*What is this?*). A piece: its name, its zone and
   its file. An item or a door: the item, its name in the level file and the line that
   places it, and its model. A marker: its name and settings.
8. For a piece or an item: **Open in Library** shows that model on its own (with its
   textures, *Export all…* and the other actions; needs the index), **Open in Blender**
   starts Blender with it, **Export .glb…** saves it for Blender.

**The in-game map** sits in the top-left corner (Case Zero's Fortune City map, Case
West's Phenotrans blueprint) with a red arrow where you are and the way you look. Like
the game's map, it shows the upper floor when you are upstairs and Case West's tunnels
when you are in the basement. Click on it to jump there. Untick *In-game map* in Layers to hide it.

**Time of day** (the **Map** panel): the slider picks the hour (00:00-23:00), and the view
takes the game's light for it from the level's lighting table: the sky's colours, the
fog, the sun or moon on items and characters, the ambient light. Walls and floors keep
their baked light (as in the game). In Case West each part of the facility has its own
table (the cafeteria, the server room…): the view uses the one for where you stand.
Untick *Time of day* for Studio's plain, neutral light.

**Copy camera position** puts the camera's x, y, z on the clipboard (handy for notes, or
to tell someone where something is).

## Steps: export a zone or the whole level

9. Fly into the zone you want (the status line names the zones shown) and click **Export
   zone…** in the **Map** panel, or **Export level…** for every zone; pick a folder.
   DR2 Studio writes `<folder>/cz/prologue/`:
   - `prologue_z05.glb`: the zone for Blender, with its buildings placed, the items and
     doors (if *Items and doors* is ticked) and the markers whose layers are ticked;
   - `text/`: the level's own files as the game has them (`prologue.txt`,
     `waypoint_prologue.txt`, `nm_prologue.txt`, the map's `fe_map_*.csv`, the lighting
     `prologue.csv`);
   - `info.txt`: what is in it, and how to open it.
   A zone takes a few seconds to a minute; the log at the bottom says when it is done.
   Files that are already there are skipped, so an interrupted export can be run again.
10. In Blender, open a zone with **File → Import → glTF 2.0**, or better with the DR2
    add-on's **Import zone** ([`13-blender-addon.md`](13-blender-addon.md)), which sorts it
    into collections (Buildings, Items and doors, Markers by kind) and wires the
    lightmaps in. Its *Zombies* and *Collision* boxes add those (the collision starts
    hidden: switch its collection on in the Outliner). With the plain importer, Blender shows each surface's colour map only.

## Your mods in the map

When mods are switched on, the Maps tab draws the level **with them**, as Play would put
them in the game: a recoloured wall, a new model of an item. **Ctrl+M** (or *With my
mods* in the toolbar) shows the level without them, and again with them; the camera
stays where it is. Clicking a piece or an item a mod changes says *Changed by mod: …*.
Only the zones a mod touches are built again.

A level texture often sits in several packs of one zone (the same wall on the garage and
the shed). The game uses the first copy in the zone for every piece, so the mod build
puts your PNG on every identical copy, whichever one you replaced.

## The same in the terminal

```
dr2 studio --map living_research -g cw        # DR2 Studio straight on a level's map
dr2 studio --map prologue --at -162,4,-30,0 -g cz   # …at a spot (x, y, z, heading°)
dr2 level list -g cz                          # every level and its zones
dr2 level info prologue -g cz                 # a level's zones: pieces, centres, sizes
dr2 level info prologue z05 -g cz             # one zone: every piece and where it goes
dr2 level things -g cz                        # the item sets (level scripts)
dr2 level things prologue --kind spawn -g cz  # what a level places, by kind
dr2 level things living_research --kind door --models -g cw   # with each model's file
dr2 export prologue --zone z05 -g cz -o out   # one zone (repeat --zone for more)
dr2 export prologue -g cz -o out              # every zone, one .glb each
dr2 export prologue --whole --lod -g cz -o out   # one .glb, small textures
dr2 export prologue --markers all --script prologue_safehouse -g cz -o out
dr2 export living_research --no-items --markers none -g cw -o out   # buildings only
dr2 export prologue --zone z06 --zombies -g cz -o out   # with example zombie crowds
dr2 export prologue --zone z02 --collision -g cz -o out # with the collision mesh
```

## Check it worked

In Case Zero's street, *Go to → Map area: Grumpy Dog Bowling Alley*, walk inside: the
lanes, the ball returns with their balls, the pins at the end of the lanes, the benches
and the big mural are there, with soft baked shadows.

## If something went wrong

- **The view stays at "loading…" or says the Maps view needs QtWebEngine:** the same as
  for the 3D view ([`12-troubleshooting.md`](12-troubleshooting.md)); the `dr2 level`
  commands still work.
- **Parts are missing or blurry for a while:** they are still being converted (the
  status line at the bottom of the view counts the zones shown). Far zones stay with
  their small textures until you get near.
- **The colours are darker than in the game:** the game adds its time-of-day light and
  exposure on top of the baked lighting; DR2 Studio shows the baked lighting only.
- **Open in Library says "not in the index yet":** use **Build / refresh index**.
- **The keys don't move the camera:** click once in the view, so it has the keyboard.

## Going further

- **Change the level:** tick **Edit the level** in the **Inspector** to move, add and
  delete items and whole buildings, change zombies, and add save points, doors and your
  own items:
  [`19-edit-a-level.md`](19-edit-a-level.md).
- What each level file holds, and how pieces are placed: [`formats.md`](../formats.md)
  §Levels.
- The Library lists every level piece on its own under *Models → Environments*
  ([`16-library.md`](16-library.md)).
