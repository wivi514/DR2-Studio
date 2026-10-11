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

**Placement.** Where the game puts a piece or an item: a position, a rotation and a
scale. Pieces are placed by `ZONE_ORGANIZATION.big`, items and doors by the level's
`.txt` file (`cItemPlacement`).

**Zombie factory / zombie area.** How the game fills a place with a crowd: a *zombie
area* (`cZombieWarehouse`, in the level file) is a set of floor shapes; a *factory*
(`cMissionZombieFactory`, in `missions.txt`) says how many zombies of which types to put
there. Single zombies at an exact spot are `cMissionSpawnZombie`.

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
