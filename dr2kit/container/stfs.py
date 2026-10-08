"""Unpack the Xbox 360 package (STFS/SVOD "XContent") the games are sold in.

Why: the toolkit must not depend on a recomp to get game data. The recomps don't run on
macOS, and a modder may only have the XBLA package (a ~0.8-1.2 GB file with a
hash-like name, under ``<TitleID>/000D0000/``). ``dr2 unpack <package> <folder>`` turns
it into the same ``data/`` tree a recomp has (docs/modding/02-game-data.md).

The package is not a simple archive. STFS stores data in 0x1000-byte blocks with hash
tables interleaved every 170 blocks (and second- and third-level tables above those),
and each file is a linked list of blocks, so a file's bytes are not contiguous.
`block_index_to_offset` does the arithmetic that skips the tables. SVOD (used by some
larger titles) keeps the data in a sibling ``<name>.data/`` folder; it is supported so
such a package doesn't fail silently, though neither DR2 package uses it.

Origin: ported from the CZ recomp's ``tools/extract_stfs.py`` (same author), which
implemented the format from the description in Xenia-Canary's
``xcontent_container_device.cc`` (BSD), consulting UnleashedRecomp's
``install/xcontent_file_system.cpp`` (GPLv3) as a format reference only; no code was
copied from either. Verified: unpacking each game's package gives files byte-identical
to the recomp's ``assets/game/data`` (tests/test_gamedata.py).
"""

from __future__ import annotations

import mmap
import struct
from pathlib import Path

from ..errors import FormatError

BLOCK_SIZE = 0x1000
# A hash table block covers 170 data blocks; a level-1 table covers 170 level-0 tables
# (170*170 = 28900); a level-2 table covers 170 of those (4,913,000).
BLOCKS_PER_HASH_LEVEL = (170, 28900, 4913000)
END_OF_CHAIN = 0xFFFFFF
ENTRIES_PER_DIR_BLOCK = BLOCK_SIZE // 0x40

CONTENT_TYPES = {
    0x00000001: "Saved Game",
    0x00000002: "Marketplace Content",
    0x00000003: "Publisher",
    0x00001000: "Xbox 360 Title",
    0x00002000: "IPTV Pause Buffer",
    0x00004000: "Installed Game",
    0x00005000: "Xbox Original Game",
    0x00007000: "Game on Demand",
    0x00009000: "Avatar Item",
    0x00010000: "Profile",
    0x00020000: "Gamer Picture",
    0x00030000: "Theme",
    0x00040000: "Cache File",
    0x00050000: "Storage Download",
    0x00060000: "Xbox Saved Game",
    0x00070000: "Xbox Download",
    0x00080000: "Game Demo",
    0x00090000: "Video",
    0x000A0000: "Game Title",
    0x000B0000: "Installer",
    0x000C0000: "Game Trailer",
    0x000D0000: "Arcade Title",
    0x000E0000: "XNA",
    0x000F0000: "License Store",
    0x00100000: "Movie",
    0x00200000: "TV",
    0x00300000: "Music Video",
}

PACKAGE_MAGICS = {b"CON ": "CON", b"LIVE": "LIVE", b"PIRS": "PIRS"}

# Offsets inside the container header (see the struct layout in the Xenia reference).
OFF_HEADER_SIZE = 0x340          # be u32, end of XContentHeader
OFF_METADATA = 0x344             # XContentMetadata begins here
OFF_CONTENT_TYPE = OFF_METADATA + 0x00   # be u32
OFF_METADATA_VERSION = OFF_METADATA + 0x04
OFF_CONTENT_SIZE = OFF_METADATA + 0x08   # be u64
OFF_EXECUTION_INFO = OFF_METADATA + 0x10  # 24 bytes: media id, version, base version, title id, platform, ...
OFF_VOLUME_DESCRIPTOR = OFF_METADATA + 0x35
OFF_VOLUME_TYPE = OFF_METADATA + 0x65    # be u32: 0 = STFS, 1 = SVOD
# Display name (unicode, 0x80 bytes per locale, 9 locales) lives in the metadata tail.
OFF_DISPLAY_NAME = 0x411


def u24le(b):
    """STFS stores block numbers as 3-byte little-endian."""
    return b[0] | (b[1] << 8) | (b[2] << 16)


def block_index_to_offset(base_offset, block_index):
    """Byte offset of data block `block_index`, skipping interleaved hash tables.

    For each hash level, every `levelBase` blocks inserts one more table block ahead of
    us; the +1 in the division is because the table precedes the range it covers, so
    block 0 already sits behind one level-0 table. Mirrors Xenia's arithmetic exactly —
    it is easy to get off by one table here and the failure mode is silent garbage.
    """
    block = block_index
    for level_base in BLOCKS_PER_HASH_LEVEL:
        block += (block_index + level_base) // level_base
        if block_index < level_base:
            break
    return base_offset + (block << 12)


def block_index_to_hash_block_number(block_index):
    if block_index < BLOCKS_PER_HASH_LEVEL[0]:
        return 0
    block = (block_index // BLOCKS_PER_HASH_LEVEL[0]) * (BLOCKS_PER_HASH_LEVEL[0] + 1)
    block += (block_index // BLOCKS_PER_HASH_LEVEL[1]) + 1
    if block_index < BLOCKS_PER_HASH_LEVEL[1]:
        return block
    return block + 1


def hash_entry_info(data, base_offset, block_index):
    """The `info` word of a block's hash entry. Low 24 bits = the NEXT block number."""
    table_off = base_offset + (block_index_to_hash_block_number(block_index) << 12)
    entry_off = table_off + (block_index % BLOCKS_PER_HASH_LEVEL[0]) * 0x18
    return struct.unpack_from(">I", data, entry_off + 0x14)[0]


class Package:
    """An open XContent package. Use as a context manager, or call `close()`.

    ``files`` maps each path inside the package (``data/datafile.big``) to
    ``(size, start_block, block_count)``; `read` returns a file's bytes.
    """

    def __init__(self, path):
        path = str(path)
        self.path = path
        self._handles = []
        self.fh = open(path, "rb")
        self._handles.append(self.fh)
        self.data = mmap.mmap(self.fh.fileno(), 0, access=mmap.ACCESS_READ)
        self._handles.insert(0, self.data)
        magic = self.data[0:4]
        if magic not in PACKAGE_MAGICS:
            raise FormatError(f"not an XContent package (magic {magic!r})")
        self.package_type = PACKAGE_MAGICS[magic]

        self.header_size = struct.unpack_from(">I", self.data, OFF_HEADER_SIZE)[0]
        self.content_type = struct.unpack_from(">I", self.data, OFF_CONTENT_TYPE)[0]
        self.content_size = struct.unpack_from(">Q", self.data, OFF_CONTENT_SIZE)[0]
        exec_info = self.data[OFF_EXECUTION_INFO:OFF_EXECUTION_INFO + 24]
        self.media_id = struct.unpack_from(">I", exec_info, 0)[0]
        self.version = struct.unpack_from(">I", exec_info, 4)[0]
        self.base_version = struct.unpack_from(">I", exec_info, 8)[0]
        self.title_id = struct.unpack_from(">I", exec_info, 12)[0]
        self.platform = exec_info[16]
        self.disc_number = exec_info[18]
        self.volume_type = struct.unpack_from(">I", self.data, OFF_VOLUME_TYPE)[0]
        name = self.data[OFF_DISPLAY_NAME:OFF_DISPLAY_NAME + 0x80]
        self.display_name = name.decode("utf-16-be", "replace").split("\0")[0]

        # path -> (size, start_block, block_count)
        self.files = {}
        if self.volume_type == 0:
            self._read_stfs()
        elif self.volume_type == 1:
            self._read_svod()
        else:
            raise FormatError(f"unknown volume type {self.volume_type}")

    # -- STFS ---------------------------------------------------------------
    def _read_stfs(self):
        vd = self.data[OFF_VOLUME_DESCRIPTOR:OFF_VOLUME_DESCRIPTOR + 0x24]
        if vd[0] != 0x24:
            raise FormatError(f"bad STFS volume descriptor length {vd[0]:#x}")
        flags = vd[2]
        if not (flags & 0x01):
            # Read-write packages put the active hash table at a +1 offset per block
            # range; we only ever see read-only retail content, and guessing wrong
            # would read hash tables as data. Refuse rather than produce garbage.
            raise FormatError("package is not read-only format; unsupported")
        table_block_count = struct.unpack_from("<H", vd, 3)[0]
        table_block_index = u24le(vd[5:8])
        self.total_blocks = struct.unpack_from(">I", vd, 0x1C)[0]

        # Data starts at the first 0x1000 boundary at/after the header.
        self.base_offset = ((self.header_size + BLOCK_SIZE - 1) // BLOCK_SIZE) * BLOCK_SIZE

        dir_names = {}          # directory entry ordinal -> "path/"
        entry_count = 0
        for _ in range(table_block_count):
            off = block_index_to_offset(self.base_offset, table_block_index)
            block = self.data[off:off + BLOCK_SIZE]
            if len(block) < BLOCK_SIZE:
                raise FormatError("directory block past end of file")
            for j in range(ENTRIES_PER_DIR_BLOCK):
                e = block[j * 0x40:(j + 1) * 0x40]
                if e[0] == 0:
                    break
                eflags = e[40]
                name = e[0:eflags & 0x3F].decode("utf-8", "replace")
                parent = struct.unpack_from(">H", e, 50)[0]
                base = dir_names.get(parent, "")
                if eflags & 0x80:       # directory
                    dir_names[entry_count] = base + name + "/"
                else:
                    self.files[base + name] = (
                        struct.unpack_from(">I", e, 52)[0],   # length
                        u24le(e[47:50]),                      # start block
                        u24le(e[44:47]),                      # allocated blocks
                    )
                entry_count += 1
            table_block_index = hash_entry_info(
                self.data, self.base_offset, table_block_index) & 0xFFFFFF
            if table_block_index == END_OF_CHAIN:
                break

    def _read_stfs_file(self, size, start_block, block_count):
        out = bytearray()
        remaining = size
        block = start_block
        for _ in range(block_count):
            if block == END_OF_CHAIN or remaining == 0:
                break
            n = min(BLOCK_SIZE, remaining)
            off = block_index_to_offset(self.base_offset, block)
            out += self.data[off:off + n]
            remaining -= n
            block = hash_entry_info(self.data, self.base_offset, block) & 0xFFFFFF
        if remaining:
            raise FormatError(f"block chain ended {remaining} bytes short")
        return bytes(out)

    # -- SVOD ---------------------------------------------------------------
    def _read_svod(self):
        # Data lives in <package>.data/ as ordered fragment files.
        data_dir = Path(self.path + ".data")
        if not data_dir.is_dir():
            raise FormatError(f"SVOD package needs {data_dir}/ (missing)")
        self.svod_files = []
        for frag in sorted(data_dir.iterdir()):
            fh = frag.open("rb")
            self._handles.append(fh)
            m = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            self._handles.insert(0, m)
            self.svod_files.append(m)

        dd = self.data[OFF_VOLUME_DESCRIPTOR:OFF_VOLUME_DESCRIPTOR + 0x24]
        enhanced_gdf = bool(dd[0x19] & 0x40)
        self.svod_start_block = u24le(dd[0x1D:0x20])
        first = self.svod_files[0]
        REF = b"MICROSOFT*XBOX*MEDIA"
        if enhanced_gdf and first[0x2000:0x2000 + len(REF)] == REF:
            self.svod_base_offset, magic_off, self.svod_layout = 0, 0x2000, "egdf"
        elif first[0x12000:0x12000 + len(REF)] == REF:
            self.svod_base_offset, magic_off = 0x10000, 0x12000
            self.svod_layout = "xsf" if first[0x2000:0x2003] == b"XSF" else "unknown"
        elif first[0xD000:0xD000 + len(REF)] == REF:
            self.svod_base_offset, magic_off, self.svod_layout = 0xB000, 0xD000, "single"
        else:
            raise FormatError("SVOD: no GDF magic found in first fragment")

        root_block = struct.unpack_from("<I", first, magic_off + 0x14)[0]
        stack = [("", root_block, 0)]
        while stack:
            base, block, ordinal = stack.pop()
            ord_off = ordinal * 4
            off, idx = self._svod_block_offset(block + ord_off // 0x800)
            off += ord_off % 0x800
            frag = self.svod_files[idx]
            node_l, node_r, data_block, length, attrs, name_len = struct.unpack_from(
                "<HHIIBB", frag, off)
            name = frag[off + 14:off + 14 + name_len].decode("utf-8", "replace")
            if node_l:
                stack.append((base, block, node_l))
            if node_r:
                stack.append((base, block, node_r))
            full = base + name
            if attrs & 0x10:                 # directory
                if length:
                    stack.append((full + "/", data_block, 0))
            else:
                self.files[full] = (length, data_block, 0)

    def _svod_block_offset(self, block):
        BLOCKS_PER_L0, HASHES_PER_L1 = 0x198, 0xA1C4
        BLOCKS_PER_FILE, MAX_FILE = 0x14388, 0xA290000
        true_block = block - self.svod_start_block * 2
        if self.svod_layout == "egdf":
            true_block += 2
        file_block = true_block % BLOCKS_PER_FILE
        idx = true_block // BLOCKS_PER_FILE
        l0 = file_block // BLOCKS_PER_L0 + 1
        off = l0 * 0x1000 + (l0 // HASHES_PER_L1 + 1) * 0x1000
        if self.svod_layout == "single":
            off += self.svod_base_offset
        off += file_block * 0x800
        if off >= MAX_FILE:
            off = off % MAX_FILE + 0x2000
            idx += 1
        return off, idx

    def _read_svod_file(self, size, start_block, _):
        out = bytearray()
        remaining, block = size, start_block
        while remaining > 0:
            off, idx = self._svod_block_offset(block)
            n = min(0x800, remaining)
            out += self.svod_files[idx][off:off + n]
            remaining -= n
            block += 1
        return bytes(out)

    # -----------------------------------------------------------------------
    def close(self) -> None:
        """Release the file handles and memory maps."""
        for h in self._handles:
            h.close()
        self._handles = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def read(self, path: str) -> bytes:
        """The bytes of one file inside the package (KeyError if absent)."""
        size, start, count = self.files[path]
        if self.volume_type == 0:
            return self._read_stfs_file(size, start, count)
        return self._read_svod_file(size, start, count)

    def describe(self) -> str:
        """Header facts for people: title ID, display name, content type, file count."""
        ct = CONTENT_TYPES.get(self.content_type, "?")
        return "\n".join([
            f"package     : {Path(self.path).name} ({self.package_type})",
            f"display name: {self.display_name!r}",
            f"content type: {self.content_type:#010x} ({ct})",
            f"title id    : {self.title_id:08X}   media id: {self.media_id:08X}",
            f"version     : {self.version} (base {self.base_version})  disc {self.disc_number}",
            f"volume      : {'STFS' if self.volume_type == 0 else 'SVOD'}",
            f"content size: {self.content_size:,} bytes",
            f"files       : {len(self.files)}",
        ])


def unpack(package: str | Path, out_dir: str | Path, only: list[str] | None = None,
           progress=None) -> tuple[int, int]:
    """Extract every file (or just ``only``) of ``package`` into ``out_dir``.

    Returns ``(file_count, byte_count)``. ``progress(path, size)`` is called per file.
    Paths are written under ``out_dir`` exactly as stored (``data/...``), using
    pathlib so it works the same on Windows, Linux and macOS.
    """
    out_dir = Path(out_dir)
    total = 0
    with Package(package) as pkg:
        wanted = only or sorted(pkg.files)
        for name in wanted:
            if name not in pkg.files:
                raise FormatError(f"{package}: no file {name!r} in the package")
            blob = pkg.read(name)
            dest = out_dir.joinpath(*name.split("/"))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            total += len(blob)
            if progress:
                progress(name, len(blob))
    return len(wanted), total
