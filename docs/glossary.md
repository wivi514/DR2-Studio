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

**Skeleton / rig / armature.** The hierarchy of bones that moves a character. "Armature"
is Blender's word for it. Game rigs live in `data/skeleton/` (e.g. `playerfullbody.big`
for Chuck).

**Bone record.** The 52 bytes that describe one bone in the game files: its index, its
parent, and its scale, position and rotation (a quaternion).

**Quaternion.** Four numbers (x, y, z, w) that describe a rotation. Blender uses them too.

**Skinning / weights.** How strongly each bone pulls each vertex. "Weight painting" in
Blender sets these.

**Bone palette.** A per-mesh list that maps the mesh's own small bone numbers to the
skeleton's bone numbers. The Xbox shaders can only use a limited number of bones per
draw, so big meshes get split. The old community tools never handled this fully.

**glTF / `.glb`.** An open 3D file format that Blender imports and exports natively,
skeleton and weights included. It's the toolkit's exchange format with Blender.

**XMA.** The Xbox 360's audio compression format. The toolkit decodes it for preview and
export. No free XMA encoder exists, which is why audio replacement uses special routes
(see the audio guide).

**Bink (`.bik`).** A video format, used by Case West's movies.

**`.bcs`.** The game's string bank: all UI text for one language (`str_en.bcs`, …).

**Overlay / `game_patched` / `game_mods`.** Folders the recomps check before the original
game files. A file placed there replaces the original without touching it.
`game_patched` holds the recomp's own fixes; `game_mods` (planned) holds your mods.

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
(PNG, WAV, `.glb`, JSON). The toolkit builds it into game files for your install.

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
