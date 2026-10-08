"""Load the native LZX decoder (`native/lzx/`, built as `dr2lzx`) through ctypes.

Why ctypes: Blender's bundled Python cannot build or pip-install C extensions, but it
can load a plain shared library. So the native decoder is a small C library with one
function, and this module finds and calls it. When no library is found, dr2kit falls
back to the pure-Python decoder (`pydecode.py`): slower, never broken.

Search order (first hit wins):

1. ``DR2KIT_LZX_LIBRARY``: an explicit path to the library file.
2. ``dr2kit/container/lzx/_native/``: where release builds put a prebuilt library.
3. ``native/lzx/build/`` (and its ``Release/`` subfolder) in a source checkout: where
   ``cmake --build native/lzx/build`` puts it (docs/dev/setup.md).

Setting ``DR2KIT_LZX=python`` skips this module entirely (useful to test the fallback).
The library wraps libmspack's ``lzxd.c`` (LGPL-2.1), kept in its own library on purpose:
see THIRD_PARTY.md.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from ...errors import LzxError

ABI_VERSION = 1  # must match DR2LZX_ABI_VERSION in native/lzx/dr2lzx.c

_HERE = Path(__file__).resolve().parent
_REPO_BUILD = _HERE.parents[2] / "native" / "lzx" / "build"


def library_filename() -> str:
    """The library's file name on this OS (``libdr2lzx.so``, ``dr2lzx.dll``, …)."""
    if sys.platform == "win32":
        return "dr2lzx.dll"
    if sys.platform == "darwin":
        return "libdr2lzx.dylib"
    return "libdr2lzx.so"


def candidate_paths() -> list[Path]:
    """Every place the loader looks, in order (shown by ``dr2 doctor``)."""
    out = []
    env = os.environ.get("DR2KIT_LZX_LIBRARY")
    if env:
        out.append(Path(env))
    name = library_filename()
    out.append(_HERE / "_native" / name)
    for sub in ("", "Release", "RelWithDebInfo", "Debug"):
        out.append(_REPO_BUILD / sub / name if sub else _REPO_BUILD / name)
    return out


class NativeLzx:
    """A loaded ``dr2lzx`` library. Use `load()` rather than constructing this."""

    def __init__(self, path: Path):
        self.path = path
        lib = ctypes.CDLL(str(path))
        lib.dr2lzx_abi_version.restype = ctypes.c_int
        lib.dr2lzx_abi_version.argtypes = []
        got = lib.dr2lzx_abi_version()
        if got != ABI_VERSION:
            raise OSError(f"{path}: ABI version {got}, expected {ABI_VERSION}; rebuild it")
        fn = lib.dr2lzx_decompress
        fn.restype = ctypes.c_int
        fn.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p,
                       ctypes.c_size_t, ctypes.c_int]
        self._fn = fn
        self._lib = lib

    def decompress(self, src: bytes, out_len: int, window_bits: int = 15) -> bytes:
        """Decode one LZX stream to exactly ``out_len`` bytes, or raise `LzxError`."""
        out = ctypes.create_string_buffer(out_len or 1)
        rc = self._fn(bytes(src), len(src), out, out_len, window_bits)
        if rc != 0:
            raise LzxError(f"native LZX decoder failed (libmspack error {rc})")
        return out.raw[:out_len]


_loaded: NativeLzx | None = None
_load_error: str | None = None
_tried = False


def load() -> NativeLzx | None:
    """Return the native decoder, or None (the reason is in `load_error()`)."""
    global _loaded, _load_error, _tried
    if _tried:
        return _loaded
    _tried = True
    if os.environ.get("DR2KIT_LZX", "").lower() == "python":
        _load_error = "disabled by DR2KIT_LZX=python"
        return None
    problems = []
    for p in candidate_paths():
        if not p.is_file():
            continue
        try:
            _loaded = NativeLzx(p)
            return _loaded
        except OSError as e:  # wrong architecture, blocked by Gatekeeper, old ABI…
            problems.append(f"{p}: {e}")
    _load_error = "; ".join(problems) or "no dr2lzx library found (see docs/dev/setup.md)"
    return None


def load_error() -> str | None:
    """Why `load()` returned None, in words (None if it succeeded or wasn't tried)."""
    return _load_error
