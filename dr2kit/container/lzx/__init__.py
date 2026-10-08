"""LZX: the compression inside the game's `.big` archives (Microsoft XMemCompress).

This package decodes and encodes **one LZX stream** at a time; one stream is one
XMemCompress chunk of at most 32 KB. The framing around chunks (the entry's size header
and per-chunk headers) is in ``dr2kit/container/xcompress.py``. Format facts:
docs/formats.md, "Compressed entry stream".

Two decoders, same results:

* ``native``: the small ``dr2lzx`` C library (libmspack's ``lzxd.c``), loaded with
  ctypes. Fast. Built from ``native/lzx/`` (docs/dev/setup.md).
* ``python``: ``pydecode.py``, pure Python, written from the format description. Slow,
  but always there.

`decompress` uses the native library when it loads and the Python one otherwise.
`backend()` says which is in use; ``dr2 doctor`` prints it. The one encoder is
``encode.encode_chunk`` (pure Python, ported from the CZ recomp).
"""

from __future__ import annotations

from . import native as _native
from . import pydecode as _pydecode
from .encode import encode_chunk

__all__ = ["decompress", "decompress_python", "encode_chunk", "backend", "backend_detail"]


def decompress(src: bytes, out_len: int, window_bits: int = 15) -> bytes:
    """Decode one LZX stream to exactly ``out_len`` bytes (native if available)."""
    lib = _native.load()
    if lib is not None:
        return lib.decompress(src, out_len, window_bits)
    return _pydecode.decompress(src, out_len, window_bits)


def decompress_python(src: bytes, out_len: int, window_bits: int = 15) -> bytes:
    """Decode with the pure-Python decoder, whatever is installed (for cross-checks)."""
    return _pydecode.decompress(src, out_len, window_bits)


def backend() -> str:
    """``"native"`` or ``"python"``: which decoder `decompress` uses."""
    return "native" if _native.load() is not None else "python"


def backend_detail() -> str:
    """One line for humans: the backend, and the library path or why it isn't loaded."""
    lib = _native.load()
    if lib is not None:
        return f"native ({lib.path})"
    return f"python (slow fallback: {_native.load_error()})"
