"""DXT (BC1/BC3/BC5) block codecs: blocks ⇄ RGBA pixels.

The games' textures are almost all block-compressed: every 4×4 pixels are stored as one
8-byte (DXT1) or 16-byte (DXT5, DXN) block. This module turns blocks into pixels and
back. It works on **little-endian** blocks laid out as rows of blocks, which is what
`dr2kit.formats.bct` gives after untiling and `swap_to_little` (the Xbox stores the
same blocks as big-endian 16-bit words).

* Decoding follows the published BC1/BC3/BC5 rules (the D3D10 spec's arithmetic, as the
  CZ recomp's ``tools/tex_decode.py`` does it).
* Encoding is a straightforward quality encoder: endpoints from the block's principal
  axis, refined by least squares, then the best index per pixel. Good, not best; a
  modder who wants the best can feed us DDS from a dedicated tool later.
* **Unchanged blocks are kept bit for bit.** `encode` takes the original blocks as a
  ``reference``: wherever the new pixels equal what the original block decodes to, the
  original block is reused. So exporting a texture to PNG and importing it unchanged
  gives back exactly the shipped bytes, and editing one corner re-encodes only the
  blocks you touched. That is the phase 2 "decode then re-encode" gate.

numpy makes this fast; without it (e.g. a bare Python), the pure-Python paths give the
same results, slowly.
"""

from __future__ import annotations

try:
    import numpy as np
except ImportError:  # pragma: no cover - the pure-Python path is tested separately
    np = None

BLOCK_BYTES = {"DXT1": 8, "DXT3": 16, "DXT5": 16, "DXN": 16, "DXT5A": 8}


# ---- decoding ---------------------------------------------------------------------------

def _rgb565_np(c):
    r = (c >> 11) & 31
    g = (c >> 5) & 63
    b = c & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1)


def _colour_palette_np(blocks8, force_four: bool):
    """(n, 4, 3) palettes and (n, 16) indices for the colour half of BC1/BC3 blocks."""
    c0 = blocks8[:, 0].astype(np.int32) | (blocks8[:, 1].astype(np.int32) << 8)
    c1 = blocks8[:, 2].astype(np.int32) | (blocks8[:, 3].astype(np.int32) << 8)
    p0, p1 = _rgb565_np(c0), _rgb565_np(c1)
    four = (c0 > c1) | force_four
    p2 = np.where(four[:, None], (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(four[:, None], (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)
    bits = (blocks8[:, 4].astype(np.uint32) | (blocks8[:, 5].astype(np.uint32) << 8)
            | (blocks8[:, 6].astype(np.uint32) << 16) | (blocks8[:, 7].astype(np.uint32) << 24))
    idx = (bits[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
    return pal, idx.astype(np.int64), four


def _alpha_np(blocks8):
    """(n, 16) values of BC3-alpha / BC4 / one half of BC5 blocks."""
    a0 = blocks8[:, 0].astype(np.int32)
    a1 = blocks8[:, 1].astype(np.int32)
    eight = a0 > a1
    i = np.arange(1, 7)
    pal = np.empty((len(blocks8), 8), np.int32)
    pal[:, 0], pal[:, 1] = a0, a1
    pal[:, 2:8] = np.where(eight[:, None],
                           ((7 - i) * a0[:, None] + i * a1[:, None]) // 7,
                           0)
    i5 = np.arange(1, 5)
    six = ((5 - i5) * a0[:, None] + i5 * a1[:, None]) // 5
    pal[~eight, 2:6] = six[~eight]
    pal[~eight, 6] = 0
    pal[~eight, 7] = 255
    bits = np.zeros(len(blocks8), np.uint64)
    for k in range(6):
        bits |= blocks8[:, 2 + k].astype(np.uint64) << np.uint64(8 * k)
    idx = (bits[:, None] >> (3 * np.arange(16, dtype=np.uint64))) & np.uint64(7)
    return np.take_along_axis(pal, idx.astype(np.int64), 1)


def _blocks_to_image_np(texels, bw: int, bh: int, w: int, h: int):
    """(n, 16, 4) texels of bw×bh blocks → (h, w, 4) image, cropped."""
    img = texels.reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return img[:h, :w]


def decode(fmt: str, data: bytes, width: int, height: int) -> bytes:
    """Decode rows of little-endian blocks to RGBA bytes (``width*height*4``).

    ``fmt`` is ``"DXT1"``, ``"DXT3"``, ``"DXT5"``, ``"DXN"`` or ``"DXT5A"``. DXN's two
    channels land in red and green; blue is rebuilt as the normal's Z
    (``sqrt(1 - x² - y²)``) so normal maps look like normal maps, and alpha is 255.
    """
    bw, bh = (width + 3) // 4, (height + 3) // 4
    n = BLOCK_BYTES[fmt]
    if len(data) < bw * bh * n:
        raise ValueError(f"{fmt} {width}x{height}: need {bw * bh * n} bytes, got {len(data)}")
    if np is None:
        return _decode_pure(fmt, data, width, height)
    b = np.frombuffer(data, np.uint8)[:bw * bh * n].reshape(-1, n)
    out = np.empty((len(b), 16, 4), np.int32)
    if fmt == "DXT1":
        pal, idx, four = _colour_palette_np(b, False)
        out[..., :3] = np.take_along_axis(pal, idx[..., None], 1)
        out[..., 3] = np.where((~four[:, None]) & (idx == 3), 0, 255)
    elif fmt in ("DXT3", "DXT5"):
        pal, idx, _ = _colour_palette_np(b[:, 8:], True)
        out[..., :3] = np.take_along_axis(pal, idx[..., None], 1)
        if fmt == "DXT5":
            out[..., 3] = _alpha_np(b[:, :8])
        else:
            nib = np.stack([b[:, :8] & 15, b[:, :8] >> 4], -1).reshape(-1, 16)
            out[..., 3] = nib * 17
    elif fmt == "DXN":
        x = _alpha_np(b[:, :8])
        y = _alpha_np(b[:, 8:])
        out[..., 0], out[..., 1] = x, y
        fx, fy = x / 127.5 - 1.0, y / 127.5 - 1.0
        z = np.sqrt(np.clip(1.0 - fx * fx - fy * fy, 0.0, 1.0))
        out[..., 2] = np.clip(np.round((z + 1.0) * 127.5), 0, 255)
        out[..., 3] = 255
    elif fmt == "DXT5A":
        v = _alpha_np(b)
        out[..., 0] = out[..., 1] = out[..., 2] = v
        out[..., 3] = 255
    else:
        raise ValueError(f"unknown block format {fmt}")
    return _blocks_to_image_np(out.astype(np.uint8), bw, bh, width, height).tobytes()


# ---- pure-Python decoding (same arithmetic) ------------------------------------------------

def _c565(c: int) -> tuple[int, int, int]:
    r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def _colour_block(b: bytes, force_four: bool) -> list[tuple[int, int, int, int]]:
    c0 = b[0] | b[1] << 8
    c1 = b[2] | b[3] << 8
    p0, p1 = _c565(c0), _c565(c1)
    four = c0 > c1 or force_four
    if four:
        p2 = tuple((2 * x + y) // 3 for x, y in zip(p0, p1))
        p3 = tuple((x + 2 * y) // 3 for x, y in zip(p0, p1))
    else:
        p2 = tuple((x + y) // 2 for x, y in zip(p0, p1))
        p3 = (0, 0, 0)
    pal = [p0, p1, p2, p3]
    bits = int.from_bytes(b[4:8], "little")
    out = []
    for t in range(16):
        i = (bits >> (2 * t)) & 3
        out.append((*pal[i], 0 if (not four and i == 3) else 255))
    return out


def _alpha_block(b: bytes) -> list[int]:
    a0, a1 = b[0], b[1]
    if a0 > a1:
        pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    else:
        pal = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
    bits = int.from_bytes(b[2:8], "little")
    return [pal[(bits >> (3 * t)) & 7] for t in range(16)]


def _decode_pure(fmt: str, data: bytes, width: int, height: int) -> bytes:
    import math
    bw, bh = (width + 3) // 4, (height + 3) // 4
    n = BLOCK_BYTES[fmt]
    out = bytearray(width * height * 4)
    for by in range(bh):
        for bx in range(bw):
            blk = data[(by * bw + bx) * n:(by * bw + bx + 1) * n]
            if fmt == "DXT1":
                px = _colour_block(blk, False)
            elif fmt in ("DXT3", "DXT5"):
                col = _colour_block(blk[8:], True)
                if fmt == "DXT5":
                    al = _alpha_block(blk[:8])
                else:
                    al = [((blk[t // 2] >> (4 * (t & 1))) & 15) * 17 for t in range(16)]
                px = [(c[0], c[1], c[2], a) for c, a in zip(col, al)]
            elif fmt == "DXN":
                xs, ys = _alpha_block(blk[:8]), _alpha_block(blk[8:])
                px = []
                for x, y in zip(xs, ys):
                    fx, fy = x / 127.5 - 1.0, y / 127.5 - 1.0
                    z = math.sqrt(min(1.0, max(0.0, 1.0 - fx * fx - fy * fy)))
                    px.append((x, y, min(255, max(0, round((z + 1.0) * 127.5))), 255))
            elif fmt == "DXT5A":
                px = [(v, v, v, 255) for v in _alpha_block(blk)]
            else:
                raise ValueError(f"unknown block format {fmt}")
            for t, p in enumerate(px):
                x, y = bx * 4 + (t & 3), by * 4 + (t >> 2)
                if x < width and y < height:
                    o = (y * width + x) * 4
                    out[o:o + 4] = bytes(p)
    return bytes(out)


# ---- encoding ---------------------------------------------------------------------------

def _image_to_blocks_np(rgba: bytes, width: int, height: int):
    """RGBA bytes → (n, 16, 4) int32 texels, edges padded by repeating the last pixel."""
    bw, bh = (width + 3) // 4, (height + 3) // 4
    img = np.frombuffer(rgba, np.uint8).reshape(height, width, 4)
    pad = np.pad(img, ((0, bh * 4 - height), (0, bw * 4 - width), (0, 0)), mode="edge")
    return pad.reshape(bh, 4, bw, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4).astype(np.int32)


def _to565(rgb):
    rgb = np.clip(np.round(rgb), 0, 255).astype(np.int32)
    return ((rgb[..., 0] * 31 + 127) // 255 << 11) | ((rgb[..., 1] * 63 + 127) // 255 << 5) \
        | ((rgb[..., 2] * 31 + 127) // 255)


def _encode_colour_np(px, alpha_mask=None):
    """Encode (n, 16, 3) colours as 4-colour BC1 halves: (n, 8) uint8.

    ``alpha_mask`` (n, 16) bool marks transparent texels of a DXT1 block; blocks with any
    get the 3-colour mode, with index 3 = transparent black.
    """
    n = len(px)
    pxf = px.astype(np.float64)
    mean = pxf.mean(1, keepdims=True)
    centred = pxf - mean
    cov = np.einsum("nki,nkj->nij", centred, centred)
    # Principal axis by power iteration (robust for flat blocks: falls back to grey axis).
    axis = np.ones((n, 3)) / np.sqrt(3)
    for _ in range(8):
        axis = np.einsum("nij,nj->ni", cov, axis)
        norm = np.linalg.norm(axis, axis=1, keepdims=True)
        axis = np.where(norm > 1e-9, axis / np.maximum(norm, 1e-12), np.ones((n, 3)) / np.sqrt(3))
    proj = np.einsum("nki,ni->nk", centred, axis)
    lo = mean[:, 0] + axis * proj.min(1, keepdims=True)
    hi = mean[:, 0] + axis * proj.max(1, keepdims=True)
    three = np.zeros(n, bool) if alpha_mask is None else alpha_mask.any(1)

    def palette(e0, e1, three_mode):
        c0, c1 = _rgb565_np(_to565(e0)), _rgb565_np(_to565(e1))
        p2 = np.where(three_mode[:, None], (c0 + c1) // 2, (2 * c0 + c1) // 3)
        p3 = np.where(three_mode[:, None], np.full_like(c0, 1 << 20), (c0 + 2 * c1) // 3)
        return np.stack([c0, c1, p2, p3], 1).astype(np.float64)

    def assign(pal):
        d = ((pxf[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)
        idx = d.argmin(-1)
        return idx, np.take_along_axis(d, idx[..., None], -1)[..., 0].sum(1)

    e0, e1 = hi, lo
    pal = palette(e0, e1, three)
    idx, err = assign(pal)
    # Two rounds of least-squares endpoint refinement; keep whichever is better.
    weights4 = np.array([[1, 0], [0, 1], [2 / 3, 1 / 3], [1 / 3, 2 / 3]])
    weights3 = np.array([[1, 0], [0, 1], [0.5, 0.5], [0, 0]])
    for _ in range(2):
        wts = np.where(three[:, None, None], weights3[idx], weights4[idx])  # (n,16,2)
        if alpha_mask is not None:
            wts = wts * (~alpha_mask)[..., None]
        ata = np.einsum("nki,nkj->nij", wts, wts) + np.eye(2) * 1e-6
        atb = np.einsum("nki,nkj->nij", wts, pxf)
        sol = np.linalg.solve(ata, atb)
        ne0, ne1 = sol[:, 0], sol[:, 1]
        npal = palette(ne0, ne1, three)
        nidx, nerr = assign(npal)
        better = nerr < err
        e0 = np.where(better[:, None], ne0, e0)
        e1 = np.where(better[:, None], ne1, e1)
        idx = np.where(better[:, None], nidx, idx)
        err = np.where(better, nerr, err)
    c0, c1 = _to565(e0), _to565(e1)
    # Order the endpoints for the mode: c0 > c1 means 4 colours, c0 <= c1 means 3.
    pal = palette(e0, e1, three)
    idx, _ = assign(pal)
    if alpha_mask is not None:
        idx = np.where(alpha_mask, 3, idx)
    swap4 = (~three) & (c0 < c1)
    swap3 = three & (c0 > c1)
    swap = swap4 | swap3
    c0s, c1s = np.where(swap, c1, c0), np.where(swap, c0, c1)
    remap4 = np.array([1, 0, 3, 2])
    remap3 = np.array([1, 0, 2, 3])
    idx = np.where((swap & ~three)[:, None], remap4[idx], idx)
    idx = np.where((swap & three)[:, None], remap3[idx], idx)
    # c0 == c1 in 4-colour mode would flip the block to 3-colour mode: use index 0 only.
    same = (~three) & (c0s == c1s)
    idx = np.where(same[:, None], 0, idx)
    bits = (idx.astype(np.uint64) << (2 * np.arange(16, dtype=np.uint64))).sum(1)
    out = np.empty((n, 8), np.uint8)
    out[:, 0], out[:, 1] = c0s & 255, c0s >> 8
    out[:, 2], out[:, 3] = c1s & 255, c1s >> 8
    for k in range(4):
        out[:, 4 + k] = (bits >> np.uint64(8 * k)) & np.uint64(255)
    return out


def _encode_alpha_np(vals):
    """Encode (n, 16) 0..255 values as BC4 / DXT5-alpha blocks: (n, 8) uint8."""
    n = len(vals)
    v = vals.astype(np.int32)
    a0, a1 = v.max(1), v.min(1)
    i = np.arange(8)
    w = np.array([0, 7, 1, 2, 3, 4, 5, 6])          # palette slot -> weight of a1 (/7)
    pal = ((7 - w)[None, :] * a0[:, None] + w[None, :] * a1[:, None]) // 7
    pal[:, 0], pal[:, 1] = a0, a1
    d = np.abs(v[:, :, None] - pal[:, None, :])
    idx = d.argmin(-1)
    flat = a0 == a1
    idx = np.where(flat[:, None], 0, idx)
    bits = (idx.astype(np.uint64) << (3 * np.arange(16, dtype=np.uint64))).sum(1)
    out = np.empty((n, 8), np.uint8)
    out[:, 0], out[:, 1] = a0, a1
    for k in range(6):
        out[:, 2 + k] = (bits >> np.uint64(8 * k)) & np.uint64(255)
    del i
    return out


def encode(fmt: str, rgba: bytes, width: int, height: int,
           reference: bytes | None = None) -> bytes:
    """Encode RGBA bytes as rows of little-endian blocks.

    ``reference`` (optional): the original blocks of the same size. Every block whose
    pixels equal the reference block's decoded pixels is copied from the reference
    unchanged, and only the other blocks are encoded (module docstring). DXN takes its
    X, Y from red and green.
    """
    if fmt not in ("DXT1", "DXT5", "DXN", "DXT5A"):
        raise ValueError(f"no encoder for {fmt}")
    if np is None:
        return _encode_pure(fmt, rgba, width, height, reference)
    px = _image_to_blocks_np(rgba, width, height)
    n = BLOCK_BYTES[fmt]
    out = np.empty((len(px), n), np.uint8)
    todo = np.ones(len(px), bool)
    if reference is not None:
        ref = np.frombuffer(reference, np.uint8)[:out.size].reshape(out.shape)
        same = _unchanged_np(fmt, px, ref, width, height)
        out[same] = ref[same]
        todo = ~same
    if todo.any():
        out[todo] = _encode_blocks_np(fmt, px[todo])
    return out.tobytes()


def _encode_blocks_np(fmt: str, px):
    """Encode (n, 16, 4) texels into (n, block bytes) blocks."""
    if fmt == "DXT1":
        mask = px[..., 3] < 128
        return _encode_colour_np(px[..., :3], mask if mask.any() else None)
    if fmt == "DXT5":
        return np.hstack([_encode_alpha_np(px[..., 3]), _encode_colour_np(px[..., :3])])
    if fmt == "DXN":
        return np.hstack([_encode_alpha_np(px[..., 0]), _encode_alpha_np(px[..., 1])])
    return _encode_alpha_np(px[..., 0])


def _unchanged_np(fmt, px, ref, width, height):
    """(n,) bool: which reference blocks decode to exactly the new pixels."""
    bw, bh = (width + 3) // 4, (height + 3) // 4
    # Decode the reference at the padded size so each block's 16 texels are compared.
    dec = np.frombuffer(decode(fmt, ref.tobytes(), bw * 4, bh * 4), np.uint8)
    dec = dec.reshape(bh, 4, bw, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4).astype(np.int32)
    # Only the texels inside the image count (edge blocks were padded on encode).
    ys, xs = np.divmod(np.arange(16), 4)
    by, bx = np.divmod(np.arange(bw * bh), bw)
    inside = ((by[:, None] * 4 + ys[None]) < height) & ((bx[:, None] * 4 + xs[None]) < width)
    chans = {"DXN": [0, 1], "DXT5A": [0]}.get(fmt, [0, 1, 2, 3])
    diff = (dec[..., chans] != px[..., chans]).any(-1) & inside
    return ~diff.any(1)


def _encode_pure(fmt, rgba, width, height, reference):
    """Pure-Python encoder: bounding-box endpoints (lower quality, same block rules)."""
    bw, bh = (width + 3) // 4, (height + 3) // 4
    out = bytearray()
    ref_dec = None
    if reference is not None:
        ref_dec = _decode_pure(fmt, reference, bw * 4, bh * 4)

    def texels(bx, by):
        t = []
        for k in range(16):
            x = min(bx * 4 + (k & 3), width - 1)
            y = min(by * 4 + (k >> 2), height - 1)
            o = (y * width + x) * 4
            t.append(tuple(rgba[o:o + 4]))
        return t

    def colour_half(t, three):
        live = [p for p in t if not (three and p[3] < 128)] or t
        lo = [min(p[i] for p in live) for i in range(3)]
        hi = [max(p[i] for p in live) for i in range(3)]

        def q(c):
            return (((c[0] * 31 + 127) // 255) << 11) | (((c[1] * 63 + 127) // 255) << 5) \
                | ((c[2] * 31 + 127) // 255)
        c0, c1 = q(hi), q(lo)
        if three and c0 > c1 or (not three and c0 < c1):
            c0, c1 = c1, c0
        p0, p1 = _c565(c0), _c565(c1)
        if three:
            pal = [p0, p1, tuple((a + b) // 2 for a, b in zip(p0, p1))]
        else:
            pal = [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)),
                   tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]
        bits = 0
        for k, p in enumerate(t):
            if three and p[3] < 128:
                i = 3
            elif c0 == c1 and not three:
                i = 0
            else:
                i = min(range(len(pal)), key=lambda j: sum((p[c] - pal[j][c]) ** 2 for c in range(3)))
            bits |= i << (2 * k)
        return bytes((c0 & 255, c0 >> 8, c1 & 255, c1 >> 8)) + bits.to_bytes(4, "little")

    def alpha_half(vals):
        a0, a1 = max(vals), min(vals)
        pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
        bits = 0
        for k, v in enumerate(vals):
            i = 0 if a0 == a1 else min(range(8), key=lambda j: abs(v - pal[j]))
            bits |= i << (3 * k)
        return bytes((a0, a1)) + bits.to_bytes(6, "little")

    n = BLOCK_BYTES[fmt]
    for by in range(bh):
        for bx in range(bw):
            t = texels(bx, by)
            if fmt == "DXT1":
                blk = colour_half(t, any(p[3] < 128 for p in t))
            elif fmt == "DXT5":
                blk = alpha_half([p[3] for p in t]) + colour_half(t, False)
            elif fmt == "DXN":
                blk = alpha_half([p[0] for p in t]) + alpha_half([p[1] for p in t])
            elif fmt == "DXT5A":
                blk = alpha_half([p[0] for p in t])
            else:
                raise ValueError(f"no encoder for {fmt}")
            if ref_dec is not None:
                chans = {"DXN": 2, "DXT5A": 1}.get(fmt, 4)
                same = True
                for k in range(16):
                    x, y = bx * 4 + (k & 3), by * 4 + (k >> 2)
                    if x >= width or y >= height:
                        continue
                    o = (y * bw * 4 + x) * 4
                    if tuple(ref_dec[o:o + chans]) != t[k][:chans]:
                        same = False
                        break
                if same:
                    i = (by * bw + bx) * n
                    blk = reference[i:i + n]
            out += blk
    return bytes(out)
