"""File formats that live inside the containers: one module per format.

Each module parses an asset's bytes into a dataclass, writes it back byte-identically,
and names whatever it can't parse (CLAUDE.md, hard-won rule 6). Format facts and how
they were verified: docs/formats.md.

Modules:
    bct   a texture (`.bct`, also the extension-less entries of `.tex` packs): the
          48-byte header, the mip/face layout, Xenos tiling
"""
