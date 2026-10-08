"""Containers: how the game packs its files.

Modules:
    big        the `.big` archive (read, edit, write; byte-identical round trip)
    xcompress  the chunk framing of compressed `.big` entries
    lzx        LZX decode (native + pure Python) and encode, one stream at a time
    vpath      virtual paths: one address for any asset at any nesting depth
    stfs       the Xbox 360 package the game ships in (for users without a recomp)
"""
