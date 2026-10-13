# Glossary

Plain-language definitions of the terms used across the code and the docs. When you
add a term to the code or docs that a newcomer wouldn't know, add it here.

**Archive / `.big`.** The game's container file, like a zip without compression by
default. One `.big` holds many files ("entries"), and an entry can itself be a `.big`
(nesting). Almost every asset in both games lives inside one.

**Entry.** One file stored inside a `.big` archive.

**Virtual path (vpath).** The toolkit's address for any asset, however deeply it is
nested: the archive's path, then `/` for each level inside it.
Example: `data/models/npcs.big/chest_default.tex/chest_default_cm` is the colour
texture `chest_default_cm`, inside the texture pack `chest_default.tex`, inside the
archive `data/models/npcs.big`. Vpaths ignore letter case.

**LZX (XMemCompress).** Microsoft's compression format, used by the Xbox 360. About 1 in 8
entries in Case Zero is stored LZX-compressed. The toolkit decompresses them to read
them and recompresses edited files, because the game refuses uncompressed versions.

**Big-endian / little-endian.** The order of bytes in a number. The Xbox 360 is
big-endian. The `.big` header is little-endian, but everything inside it is big-endian.
You only need this when working on the format code.

**Texture / `.bct` / `.tex`.** A `.bct` is one texture (one image plus its mipmaps). A `.tex`
is a texture pack (a `.big` full of `.bct` files) that sits next to a model.

**Tiling (swizzling).** The Xbox 360 GPU stores images with their pixels shuffled into
blocks for speed. Read straight, a tiled texture looks like noise. The toolkit untiles
on export and re-tiles on import.

**DXT1 / DXT5 (BC1 / BC3), DXN (BC5).** Compressed GPU texture formats. DXT1 suits colour
without smooth alpha, DXT5 colour with alpha, and DXN normal maps. The toolkit converts
them to and from PNG.

**Mipmaps.** Smaller copies of a texture (½, ¼, …) used when the object is far away. The
toolkit regenerates them when you replace a texture.

**Texture suffixes.** The end of a texture's name tells its job: `_cm` = colour map (the
base picture). Others (`_nm`, `_sm`, …) will be listed here once the census confirms them.

**Model / scene.** A character, prop or weapon: a `.big` of named chunks holding meshes,
materials, and a list of nodes (bones and objects). Skeleton files use the same layout,
without meshes.

**Mesh.** The 3D surface: vertices (points) and indices (which points form triangles).
In the game files a mesh is called a *shape* (`geo_tshirtShape`, a Maya name).

**Draw (draw call).** One "paint these triangles with this material" order to the GPU.
A shape is drawn with one or more draws, one per material. The game records them in a
shape's *command buffer*.

**Vertex stream / vertex declaration.** The vertices of a draw are raw bytes in one or
more *streams* (e.g. one for positions, one for UVs). The *declaration* says what each
byte means: "bytes 0-11 are the position as three floats, bytes 12-19 the UV…". Every
draw has one, stored next to the mesh (`D3DVertexDesc`).

**Triangle strip.** A compact way to list triangles: each new index makes a triangle
with the two before it. Strips are joined by repeating an index, which makes empty
("degenerate") triangles that the GPU skips. All the games' meshes are strips.

**Rest pose / bind pose.** The pose a model was built in (for characters, a T-pose with
arms out). Bones are stored in it, and skinning moves vertices away from it.

**Skeleton / rig / armature.** The hierarchy of bones that moves a character. "Armature"
is Blender's word for it. Game rigs live in `data/skeleton/` (e.g. `playerfullbody.big`
for Chuck).

**Bone record.** The 52 bytes that describe one bone in the game files: its index, its
parent, and its scale, position and rotation (a quaternion).

**Quaternion.** Four numbers (x, y, z, w) that describe a rotation. Blender uses them too.

**Skinning / weights.** How strongly each bone pulls each vertex. "Weight painting" in
Blender sets these.

**Bone palette.** The bones one draw can use. A vertex says "bone 3 of the palette"; the
palette says which skeleton bone that is. In these games the palette is simply a run of
consecutive skeleton bones (first bone, how many), at most 61 per draw because that is
what fits in the shader's constants. The old community tools never worked this out; the
toolkit verified it against the running game.

**Palette split.** When a part of a mesh uses bones too far apart in the skeleton's
numbering for one palette (more than 61), the toolkit writes it as several draws, each
with its own palette. Automatic; the model check tells you when it happens.

**Template draw.** When the toolkit writes a new or edited part, it copies an original
draw that used the same material: its shader, textures and vertex layout. That is why a
new mesh must use one of the model's existing materials.

**Model check (rig validator).** What `dr2 model check` and Studio's *Replace with .glb…*
run on a `.glb` before it goes into a game model: are the parts named like the model's,
are all bones the game's, does every vertex have a weight, at most 4 bones per vertex,
can each part's bones fit the palettes, do the materials exist. Errors stop the build;
warnings tell you what will happen.

**Shader / shader constants.** A shader is the little program the GPU runs for every
vertex (or pixel). *Constants* are the values the game hands it for a draw: the camera,
and for a skinned draw the bone palette's matrices.

**glTF / `.glb`.** An open 3D file format that Blender imports and exports natively,
skeleton and weights included. It's the toolkit's exchange format with Blender, and what
DR2 Studio's 3D view shows. A `.glb` is one file with everything inside, textures too.

**Extras / custom properties.** Extra data a `.glb` can carry on any object. The toolkit
stores each bone's original game record there; Blender keeps it as a *custom property*
on the bone and writes it back on export, which is how a skeleton survives a trip through
Blender bit for bit.

**Capture (in-game).** A frame recorded from the running recomp with the F9 key: the
picture, and on request the exact bytes and shader constants of every draw. Phase 3
compared the toolkit's model reading with one.

<a id="xma"></a>**XMA (XMA2).** The Xbox 360's audio compression format (a cousin of WMA Pro);
every sound of both games is XMA (`.xma`). The toolkit decodes it with ffmpeg (through
PyAV) for listening and WAV export. Nobody can redistribute an XMA *encoder*, so sound
mods don't make XMA: the recomp plays your audio instead (see *PCM substitution*).

**XMA packet / frame / stream.** XMA is cut into 2 KB **packets**; each holds pieces of
**frames** of 512 samples. Sounds with more than two channels (the 5.1 cutscene audio)
are several **streams** of one or two channels whose packets take turns.

**Sample / sample rate / channels.** A sample is one number of a sound wave; the rate is
how many per second (48000 for these games); channels are mono (1), stereo (2) or 5.1
(6: front left/right, centre, LFE (the subwoofer), surround left/right). A sound's
length is counted in samples per channel.

**PCM / WAV.** Uncompressed audio: plain samples. A `.wav` file is PCM with a small
header; what `dr2 extract --wav` writes and what audio editors read.

**Stream table (`$GIB`, `cache.big`).** The table in `data/audio/cache.big` that says,
for every streamed sound (music, voices, cutscenes), its rate, channels and loop, because
those sounds are stored without a header of their own.

**`.sfx` (sound effect).** A small text file next to the recordings in a sound bank:
which recordings (`.xma`) make up one game sound, and how (volume, layers, pitch). The
game plays sounds by the `.sfx` name, so `FEError.sfx` *is* the "error" beep.

**Audio scene script.** A text file (`data/audio/Prologue.txt` in Case Zero) that wires
game events to sounds: "when `MechanicBattleStart` fires, play `music.big/HB_Indemnify`".
The index uses it to name sounds. The game checks it against a digest, so it can't be
edited.

**Digest.** A fingerprint (here SHA-1) of a file, stored in the game's executable. The
game recomputes it when it loads the file and refuses to run (crashes) if they differ.

**PCM substitution (audio mods).** How sound mods work: the recomp decodes the game's
XMA itself, and for a replaced sound outputs your audio's samples instead of the decoded
ones. The game's files don't change.

**Fingerprint (packet hash).** A 64-bit number computed from the bytes of one XMA packet
(FNV-1a). The recomp recognises the packets of a replaced sound by it.

**Loop / loop region.** The part of a sound the game repeats (engine hums, alarms,
some music). Studio shades it on the waveform.

**Bink (`.bik`).** A video format, used by Case West's movies.

**`.bcs`.** The game's string bank: all UI text for one language (`str_en.bcs`, …).

**Overlay / `game_patched` / `game_mods`.** Folders the recomps check before the original
game files. A file placed there replaces the original without touching it.
`game_patched` holds the recomp's own fixes; `game_mods` holds your mods (checked first;
`CZ_NO_MODS=1` / `CW_NO_MODS=1` makes the recomp ignore it).

**Recomp.** A static recompilation: the Xbox 360 game translated to run natively on a
PC. The Case Zero and Case West recomps are this toolkit's sister projects.

**Profile.** The toolkit's settings for one game (`cz` or `cw`): where its data is and
what differs about it.

**Census.** A script that reads *every* file of one type in both games and reports what
it found, including anything it couldn't understand. It's how format knowledge is
proven rather than guessed.

**Round trip.** Read a file and write it back unchanged. It must give back the identical
bytes; that's the first test of every writer in the toolkit.

**Mod package.** A folder with a `mod.toml` and your replacement files in normal formats
(PNG today; WAV, `.glb`, JSON later). The toolkit builds it into game files for your
install ([`modding/06-mod-packages.md`](modding/06-mod-packages.md)).

**XBLA package / STFS.** The single file Xbox Live Arcade games are sold as (a 42-character
hex name, under `<TitleID>/000D0000/`). Inside is a small filesystem called STFS.
`dr2 unpack` turns it into an ordinary `data/` folder.

**Title ID.** The Xbox 360's 8-character ID for a game: `58410A8D` is Case Zero,
`58410B00` Case West.

**Gate.** A measurable check that must pass before a feature or phase counts as done,
e.g. "every archive in both games re-writes to identical bytes". See `dev/testing.md`.

**Name hash.** A 32-bit number the game computes from a name (`h = h*33 ^ c`) and uses
to look things up quickly. Every `.big` entry stores the hash of its lower-cased name.

**Flags (entry flags).** A number stored with each archive entry whose meaning is not
known yet (values seen: `0x4`, `0x10`, `0x20`, `0x80`, `0x100`, `0x800`). The toolkit keeps
it unchanged when writing.

**Alignment / padding.** Many entries must start at an offset that is a multiple of some
number (4, 16, 0x800…), so the archive puts zero bytes ("padding") in front of them.
The toolkit keeps each entry's alignment when it rewrites an archive.

**Chunk (compressed).** Compressed entries are split into pieces of up to 32 KB, each
compressed on its own. A chunk is one such piece.

**Native library / fallback.** The fast LZX decoder is a small compiled library
(`dr2lzx`). When it isn't available, the toolkit uses a slower one written in plain
Python (the fallback). Both give the same results; `dr2 doctor` says which is in use.

**`dr2` command.** The toolkit's command-line program, typed in a terminal
(`dr2 ls`, `dr2 extract`, …). `python -m dr2kit` is the same thing.

**Asset index.** The toolkit's catalogue of every file and archive entry of both games,
in one SQLite database file, with a thumbnail of each texture and the links between
models and their textures. Built by `dr2 index build` or DR2 Studio's
**Build / refresh index**; it makes searching instant.

**DR2 Studio.** The toolkit's window-based app (`dr2 studio`): browse, search, look at
textures, export them, and build mods without typing commands.

**Cube map.** A texture made of six square images, the six faces of a cube around the
viewer (+X, −X, +Y, −Y, +Z, −Z). Used for reflections and skies. Exported as a strip of
six faces.

**Packed mips.** On the Xbox 360 the smallest mip levels of a texture (16 pixels and
less) share one memory tile, each tucked into a corner of it. For a tiny texture even
the full-size image sits there. The toolkit knows where each level is.

**Colour map / normal map / mask.** Kinds of texture, named by their ending: `_cm`
holds the colours you see; `_nm` (normal map) holds the direction of the surface for
lighting, and looks purple-blue; `_mask` says which parts of a piece of clothing get
tinted.

**Reference blocks.** When the toolkit turns your PNG back into a game texture, any
4×4 block whose pixels you didn't change keeps the game's original bytes exactly. Only
the blocks you painted on are compressed again, so an unedited texture comes back
bit-for-bit identical.

**Deploy / undeploy.** Copy a built mod into the place the game reads it from (a recomp's
`assets/game_mods/`), or remove exactly those files again.

**Value set (`.scv`).** A material's list of shader settings (colours, scales), stored in
`valuesets.big` inside the model. Zombie clothing gets its colours from it.

**Weight map.** A texture whose channels aren't colours but amounts: "how much of colour
1, 2, 3, 4 goes here". Zombie clothing's `_cm1` is one; the toolkit turns it into a
normal colour picture ("bakes" it) for previews and Blender.

**String bank / `.bcs`.** The file that holds every piece of text the game shows, in one
language: `data/frontend/str_en.bcs` (English), `str_fr.bcs` (French)… Each text has a
number, its **string id**; menus and scripts name the id, and the game looks up the text
in the bank of the language the player chose.

**String id / label.** A string's number (`10611`) and its developer name
(`IDS_PRESS_START`, from `str_id.bcs`). The toolkit accepts either.

**Markup (strings).** Codes inside a string: `[00CC00FF,golf club]` draws "golf club" in
a colour (red, green, blue, opacity in hex), `[@x_button_ig]` draws a button icon. A
string that uses them must start with `@`.

**Placeholder.** `%s`, `%d`, `%1`… in a string: the game fills in a name or a number
there. Keep them when you change a string.

**Digest / digest-checked file.** A fingerprint (SHA-1) of a file, stored in the game's
executable. For the few files listed there, the game compares the fingerprint when it
loads them and crashes if the file was changed, so mods can't change them (Case Zero:
`Prologue.txt`; Case West: six files, listed in `formats.md`).

**Mod library / load order.** The mod manager's folder of installed mods, and their
order. Mods later in the order win when two change the same thing; each mod can be
switched on or off.

**Bink / `.bik`.** A video format (by RAD Game Tools) used for Case West's movies. The
toolkit can play and export them, not make new ones.

**AppImage.** A Linux program packed into one file you make executable and run; DR2
Studio's Linux release is one.

**Blender extension.** Blender 4.2+'s name for an add-on installed from a zip with a
`blender_manifest.toml`; the DR2 add-on (`io_dr2`) is one.

**LGPL / GPL.** Two open-source licences. LGPL libraries (Qt, ffmpeg as the toolkit
builds it) can ship inside a program under another licence; GPL ones can't ship inside
the toolkit's releases, which is why releases use an own ffmpeg build. The Blender
add-on itself is GPL, as Blender requires.

**`.dr2mod`.** A mod packed into one file to share (a zip with its own name). DR2 Studio
installs it when you drop it on the window or use **Install mod…**; **Share…** makes one.

**Requirements (`requirements.json`, `REQUIRES.txt`, `[requires]`).** What a mod needs
besides itself: the game it plays in, any other game whose files it is made from (a Case
West item in Case Zero needs Case West's data on your computer, since mods hold recipes,
not game files), other mods, whether saves made with it need it, and whether every co-op
player needs it. The toolkit works most of it out and writes it into every shared mod, so
a launcher can say "this mod needs Case West" before starting anything
([guide 06](modding/06-mod-packages.md#what-a-mod-needs)).

**Linked mod.** A mod in the library whose folder stays where it is (a mod you are
making), instead of a copy inside the library folder.

**Mod set.** A saved list of which mods are switched on, so you can switch between, say,
"all my mods" and "just the translation".

**Play.** DR2 Studio's button (and `dr2 play`) that puts the switched-on mods into the
game (deploys them) and starts the recomp.

**Texture set.** A texturing program's name for the textures of one material.
Exporting a model to `.glb` names each material (and so each texture set) like
`00_young_cr_shirt_cm`; keeping that name is how exported textures find their game
texture.

**Normal map, OpenGL / DirectX style.** A normal map's green channel says which way a
bump faces up or down; programs disagree on the direction. DR2's normal maps are
**OpenGL-style** (green up), like Blender's.

**PBR (metal/roughness).** The way most modern games and Substance Painter describe
materials (base colour, metallic, roughness). DR2 is older: colour, specular and normal
only. The toolkit converts a metal/roughness export for you.

**UDIM.** Several UV tiles for one model. DR2 uses one tile (0 to 1): turn UDIM off in
texturing programs.


**Library (DR2 Studio, `dr2 library`).** The games' assets sorted by what they are
(characters, zombies, music, rigs, menu pictures…) instead of where they are stored. Each
asset is in one **group** (Characters), sometimes a **sub-group** (Outfit parts), with a
friendlier **label** when one is known ("Young Chuck's orange 04 shirt"). The rules are a
file anyone can extend: `dr2kit/catalog/groups.toml`. Not to be confused with the **mod
library**, the folder where your installed mods live.

**Identical copy ("also in…").** The same asset stored twice with exactly the same bytes,
for example a skeleton in `data/skeleton/` and again in `preload4.big`. The Library shows
it once and lists where the other copies are.

**Variant.** One of several looks a model can have. A zombie model holds several heads,
shirts and trousers at once, and the game shows one of each (a **shape group** per
choice); a material can also swap its colours (a **colour variant**, another value set).
Not to be confused with detail levels. Phase 9 ([`modding/17-variants.md`](modding/17-variants.md)).

**Look (variant choice).** One combination of choices for a model: head 2, no hat, shirt
3, jersey colours 4… DR2 Studio's **Variants** panel edits it; the command line writes it
as text (`head=2 headwear=none shirt=3 colour.jersey=4`).

**Slot.** Something the game picks one of for each zombie: Head, Headwear, Shirt,
Trousers, Skirt, Feet, Tall boots, Head tumour. A slot's choices are numbered by the
part names (`head2_…`, `chest_shirt3…`); **none** takes the part off.

**On/off part.** A part that is shown or not, apart from the slots: wound caps, burnt
look, bare arms, glasses, chest accessories.

**Hide mask.** The 64-bit number each zombie carries in the game: one bit per group of
parts; a part is hidden when one of its bits is set. A look in the toolkit converts to
this number (shown in the Variants panel), to compare with what a recomp reports.

**Collision mesh.** The invisible, simplified shapes the game uses to stop the player,
zombies and thrown things: walls, floors, a rough cone for a tree. Never drawn in game.
Each zone keeps its own in `MERGED_COLLISION.big` (Havok triangle meshes); DR2 Studio's
Maps tab shows it as see-through orange ([`modding/18-maps.md`](modding/18-maps.md)).

**Colour choice.** Another set of colours for a piece of clothing (`jersey 3`): another
**value set** the game can swap in for the material's own. Only the numbers change, so
the toolkit bakes it the same way as the own colours.

**Prop state.** A prop's other look kept in the same file as twin parts: a slot
machine's damaged logo (`slot_logo_dmg` next to `slot_logo`), its win screen, a lower
detail copy (`LOD_slot_machine`). Off by default.

**Level.** One place of the game you can walk around: Case Zero's Fortune City street
(`prologue`), Case West's labs (`living_research`, `storage_pens`…). Its buildings are in
`data/models/environment/<level>/`; what lies in it (items, doors, spawn points) is in
text files in `datafile.big`. (In the toolkit's Maps tab, phase 10, "map" means a level.)

**Zone.** A part of a level that the game loads and unloads as you move (the bowling
alley is zone 5 of `prologue`). Each zone is one archive, `<level>_zNN.big`, holding its
pieces, their textures, and the list of where each piece goes.

**Piece (level piece).** One model a level is built from: a wall section, a floor, a
sign, a row of lights. The Library lists them under *Environments*.

**With my mods (preview).** DR2 Studio's switch (Ctrl+M) that shows the game's assets
with your switched-on mods applied, exactly as Play will put them in the game, or as
shipped. Lets you see a change without starting the game.

**Lightmap.** A texture of light painted in advance ("baked") over a level piece: where
shadows fall, where light pools. The game multiplies the colour map by it, so a wall
looks lit without computing light while you play. Case Zero names them `AO_<piece>`,
Case West `LM_<piece>`.

**LOD textures (`_LOD.tex`).** Small copies of a model's textures (a quarter of the
size) that the game uses when the model is far away. "LOD" means *level of detail*.
DR2 Studio's Maps tab uses them for zones far from the camera, so a whole level fits in
memory; exports use the full-size ones.

**Placement.** Where the game puts a piece or an item: a position, a rotation and a
scale. Pieces are placed by `ZONE_ORGANIZATION.big`, items and doors by the level's
`.txt` file (`cItemPlacement`).

**Level script.** One level's set of text files in `datafile.big`: `<x>.txt` (items,
doors, spawn points, areas), `waypoint_<x>.txt` (triggers, sound areas) and `nm_<x>.txt`
(the navigation mesh). Several can share one level's buildings: Case Zero's
`prologue_safehouse` is the street with the safehouse story's items.

**Spawn point.** A place the game puts the player (Chuck) when a level starts or when
a door to another level leads there (`Start`, `SafehouseBedroom`).

**Trigger.** An invisible box or circle that does something when you walk in or press a
button there: a door to another level, an interaction.

**Navigation mesh (nav mesh).** Invisible floor shapes that say where zombies and
survivors can walk; they find their way along them.

**Map area / map point.** A named floor shape the in-game map and the HUD use ("Junkyard",
"Cafeteria"), and a marked spot on the map (workbench, save point).

**Zombie factory / zombie area.** How the game fills a place with a crowd: a *zombie
area* (`cZombieWarehouse`, in the level file) is a set of floor shapes; a *factory*
(`cMissionZombieFactory`, in `missions.txt`) says how many zombies of which types to put
there. Single zombies at an exact spot are `cMissionSpawnZombie`.

**Block / block path.** The game's text files are made of *blocks*: a class and a
name (`cItemPlacement Scissors1`), then `{`, its settings (`Location = "…"`) and blocks
inside it, then `}`. A *block path* names one block by the blocks around it, joined with
`/`: `cMissionDefinition PrologueZombies/cMissionLevelReady Ready/cMissionZombieFactory
x2009`. It's needed because a name like `x2009` is used in many missions.

**Level edits (`.edits.json`).** How a mod changes a level or mission text file: a small
file that lists only what it changes, by block path (move this item, add that zombie,
remove this box), instead of a whole copy of the file. Several mods can change one file
this way, and the recomp's own changes to it stay.

**Prefab.** A ready-made thing to add to a level, copied from one the game already has
(a save point, a workbench, a door to another level…), so it works like the real one.
DR2 Studio's **Add from prefab…** lists them; you can save your own (`.dr2prefab`).

**Load set.** The zombie types a level loads into memory, by time of day
(`zombiesets.txt`). A zombie of a type the level doesn't load probably doesn't appear,
so adding a new type to a level means adding it to the load set too.

**Navigation mesh.** An invisible floor plan of where zombies and survivors can walk
(`nm_<level>.txt`).

**AO map (ambient occlusion).** A grey picture of the shadows baked into a level piece
(dark in corners, light in the open), multiplied over its colours: `AO_<piece>`.

**Detail level (LOD).** A simpler copy of a model the game draws when it is far away.
Zombies come as `_2` (high), `_3` (medium) and `_4` (low detail). The Library shows the
three files as one item with a **Detail** choice (before phase 9 it called them
"variant 2/3/4", which they are not).

**Wound cap (`cap_*`).** A small shape that closes the hole where a zombie's limb or head
came off. The game hides caps until that happens.

**Rig match.** Which skeleton file a model was made for. Every character carries its own
copy of its rig; the index compares its bones with the skeleton files: the same bone
names *and* the same rest pose (where each bone sits) is a match. The names alone aren't
enough: Chuck's, the women's, the large men's and the children's rigs all use the same 98
bone names, with different proportions.

**Export all.** One click that writes everything an asset is made of into one folder: for
a model its `.glb` (with textures and bones), every texture as PNG, the rig alone, and
an `info.txt`. Run again, it continues where it stopped.

**Rigid part.** A piece of a model that moves as one block with a single node (a bone),
instead of bending with several: a box's lid, a door, a car's wheel, a gun. The game
stores its shape relative to that node; the toolkit places it there (in Blender it is
parented to the node, so rotating the node moves the part).

**Dock window (panel).** One part of DR2 Studio's window (Browse, Viewer, Level (3D),
Inspector, Hierarchy, Place…) that you can resize, drag to another side, stack with
another as tabs, or drag out as a window of its own. **Windows** in the toolbar shows or
hides each one and puts them back.

**Inspector.** The Maps editor's panel for the selected thing: what it is, its position,
rotation and size, and its buttons (copy, delete, put back).

**Hierarchy.** The Maps editor's list of everything in the open level, grouped (items and
doors, buildings with their parts and collision, zombies, markers). Click a row to fly
there.

**Place panel.** The Maps editor's list of things to add to a level (prefabs, items,
zombies, buildings), which you drag onto the 3D view.

**Building.** What a player sees as one building, made of several level pieces (walls,
boarded windows, signs, writing, a roof unit) and one or more collision shapes. The game
has no such object; DR2 Studio groups the pieces and shapes itself, so a building moves
and hides as a whole.

**Collision shape.** One block of the invisible walls and floors the player bumps into
(the zone's collision mesh is made of them). It is stored apart from the pieces you see,
so hiding a piece alone leaves its collision behind; DR2 Studio moves a building's shapes
with it.

**Search tree (MOPP).** Havok's quick index of a collision shape's triangles, made by the
game's tools. The toolkit can't rebuild it, which is why collision can be moved (the tree
moves with it) but not turned or resized.

**Parked.** How a mod hides a building: its placement is moved 1,000 metres under the
level, so nothing else in the zone's list has to change.

**Carrier item.** An item the game ships a model for but never places (CZ's Lead Pipe).
A mod can turn it into a weapon of its own by replacing its model, textures and settings,
without adding any file (phase 12's Frostmourne; `formats.md` §Weapons). Since phase 13
new items load too, so the weapon wizard makes new ones instead.

<a id="weapon-kind"></a>**Weapon kind.** What a new weapon swings like (sword, knife, bat,
heavy hammer…): a game weapon the weapon wizard copies, so the new one gets its moves,
sounds and way of being held (`dr2kit/catalog/weapon_kinds.toml`; guide 20).

**Weapon wizard.** DR2 Studio's *New weapon…* window (and `dr2 mod new-weapon`): makes a
weapon of your own from a few choices (kind, model, damage, element, effects, icon, combo
card) and writes it into your mod.

**Grip node.** A point inside a weapon's model where one of Chuck's hands goes
(`LOC_rhand`, `IK_lhand`, `LOC_WEP_<x>_R`…). Measured in game: the hands follow these
whatever the moves, so a new shape is placed to them (the wizard shows them as red
diamonds).

**Effect table.** The list of particle effects inside the game's program, by number (see
*Effect number*). The toolkit keeps their names (`dr2kit/catalog/effects.toml`) so you
can pick "snowtrail_wpn_bs_1" instead of typing 215; `dr2 effects` lists them by group.

<a id="particle-effect"></a>**Particle effect.** A small file in
`data/models/effects.big` that makes fire, snow, sparks, blood or smoke: a name and a few
*emitters*. Weapons and levels show one by its *effect number*; you can change one or make
your own (guide 21).

**Emitter.** One part of a particle effect: it throws out little pictures (*particles*)
from a shape (a box, a sphere…), each with colours that change over its life, a size and
a lifetime. The Flaming Sword's flame is four emitters (smoke, flame, sparks, glow).

**Particle picture.** The small picture an emitter throws out (`fire_flame`, `glow`,
`cloud_smoke2`…), kept in `data/models/effects.tex`. You can add your own (a PNG).

<a id="free-slot-effects"></a>**Free slot (effects).** One of the 36 numbers of the effect
table that has no effect in the game (`wip_1`, `unused`…). An effect of your own goes into
one and takes its number, because the program's list of numbers can't grow.

**Eviction (`preload4.big`).** The game keeps copies of some files (the effects among
them) inside `data/preload4.big` and reads those instead of the real ones. Changing a copy
there crashes the game, so a mod build *hides* the copy (it changes 4 bytes of its name's
hash) and the game reads the real file, with the mod's changes.

**`layout.bin` (size pin).** A file of the game listing every data file with its size. A
file that grows past the size written there crashes the game when opened, so a mod build
writes a `layout.bin` with the new sizes when it changes one.

**Local-only mod.** A mod with `local_only = true` in its `mod.toml`: it holds files from
another game (a WoW model or effect brought in for yourself), so it plays on your
computer but DR2 Studio won't share it (guide 22).

**Locator.** A named point in a model (`LocatorArray`) where the game puts something:
the hands (types 9 and 27), where blood or a slice shows, and the **effect point** (type
16) where a weapon's effects while held or swinging appear. The weapon wizard moves the
effect point so effects run along the blade.

**Shine (weapon).** The weapon wizard's choice of how much a weapon reflects the sky: a
game weapon's four material values copied (matte, a little, mirror).

**Combo card.** The card a combo weapon shows in the game's card list: a picture at the
top, line drawings of the two items that make it, and texts. A card has two pictures:
found (`comboc_<name>`) and not found yet (`comboc_<name>_no`, faded red).

**Empty card.** A combo card with no picture and no drawings, made by the toolkit from
all the game's cards (the middle value of each pixel: what all cards share). The wizard
draws a new card on it.

**Atlas (texture atlas).** Several pictures put side by side in one, with the model's UVs
moved to match: how a model with several materials becomes a weapon with one colour
texture.

**Effect number.** The number in a weapon's `EffectOnImpact`, `EffectOnVictim`,
`PyroEffect`… keys: which particle effect shows (blood, sparks, a snow trail). It counts
into a list of effects inside the game's program (371 in Case Zero, 414 in Case West,
the first 370 the same);
it changes only what you see, not what happens to a zombie.

**Element (of a weapon).** What a hit does to a zombie besides damage: shock
(`Can_Electrocute`), fire or freeze (a `cPropHitZombieInfoItem` block with
`PropHitZombieEffect` 0 or 1).

<a id="animation"></a>**Animation (`.anm`).** One move of a character (a swing, a step, an
idle) in `data/anim/**`: for each bone it moves, the bone's turn (and sometimes its
offset) over time, at 30 frames a second. One file per skeleton part: *full body*,
*root* (where the hips are), *hand* (the fingers), *upper body*, *face*. The toolkit
reads every frame of every one (phase 14) and plays them in DR2 Studio and Blender.

<a id="keyframe"></a>**Key (keyframe).** A moment where an animation stores a bone's
value; between keys the value is worked out (a straight line between the two). The game
stores few keys where a bone moves smoothly, and most keys as a small change from the one
before (4 bytes instead of 8).

<a id="root-motion"></a>**Root motion.** How far a move carries the whole body (a sword
lunge goes 2 m forward): the `dummy01.root` bone's travel in the *root* animation. In game
Chuck really moves that far; DR2 Studio's *In place* takes it out so he stays in view.

<a id="skeleton-id"></a>**Skeleton id.** The number at the start of an animation that
says which rig it is for; each skeleton file stores its own in `_ANIMCHANNELINFO_`. The
game refuses an animation on the wrong rig; the toolkit uses it to show zombie moves on
the zombie rig and Chuck's on Chuck.

<a id="idle-pose"></a>**Idle pose.** How Chuck stands when you don't touch the pad. It
depends on what he holds: arms loose with a one-hand weapon, a box hugged with both arms,
a spear across the body, a rifle at the hip. The game picks it from the item's
`AnimationChooserValueForIdle` (and the fingers from `…ForHand`) through its animation
graph. DR2 Studio shows the first frame of it, frozen, to line weapons up.

<a id="animation-graph"></a>**Animation graph (`sgraph.txt`).** The game's text file
(`data/datafile.big/sgraph.txt`) that says which animation plays when: states, and in
each, *choosers* that pick an animation from a number (the item's idle value, the gun
type, whether a chainsaw is running…). The toolkit follows it to find each kind of
item's idle, as the game does.

<a id="chooser-value"></a>**Chooser value.** A number in an item's settings
(`AnimationAttackChooserValue0 = "396"`) that the [animation graph](#animation-graph) turns
into an animation. An item brought from the other game needs its values to exist in this
game's graph, so the importer copies the missing entries (`dr2kit/convert/graphcarry.py`).

<a id="zombie-type-slot"></a>**Zombie type slot.** A name in the program's fixed list of
zombie types (Case Zero 32, of which 20 have no model: **empty slots**; Case West 10, all
used). A zombie type from the other game takes an empty slot's name.

<a id="shader-pool"></a>**Shader pool.** A fixed-size table the game's renderer fills as it
loads shaders (one entry per pixel shader, per shader description…). Shaders brought from
the other game need room in them; both recomps make them bigger (4,096 entries).

**Hand prop node (`r_hand_prop`).** A bone in Chuck's right hand where held items hang:
the item's right-hand grip node is put on it (`dr2kit/convert/holding.py`).

<a id="level-slot"></a>**Level slot.** One of the levels the game's program knows by id
(`LEVEL_PROLOGUE`, `LEVEL_FOOD_BARN`…): a fixed list inside the executable, with the
name of each level's script file and zone list. Case Zero's program still lists Dead
Rising 2's 82 levels but ships the files of 4; the others are **empty slots** a map of
one's own can fill (no mod can add a new id).

<a id="new-piece"></a>**New piece.** A level piece the game doesn't have (a building of
one's own): a copy of a game piece with the modder's shape and picture, added to a zone
and placed by a record of its own (`.pieces.json` `new`).

<a id="layout-bin"></a>**`layout.bin`.** The game's list of its loose files with their
sizes. A mod build writes a new one when a file changes size or a mod adds a file.
