"""`dr2kit.userdirs`: without platformdirs (Blender), the same folders as with it."""

import pytest

from dr2kit import userdirs


@pytest.mark.parametrize("kind", ["config", "cache", "data"])
def test_fallback_matches_platformdirs(kind):
    pytest.importorskip("platformdirs")
    assert userdirs._fallback(kind) == userdirs._dir(kind)


def test_works_without_platformdirs(monkeypatch):
    import builtins
    real = builtins.__import__

    def no_platformdirs(name, *a, **k):
        if name == "platformdirs":
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_platformdirs)
    assert userdirs.config_dir().name in ("dr2kit",)
    assert userdirs.cache_dir().parts[-2:] in (("dr2kit", "Cache"), (".cache", "dr2kit"),
                                               ("Caches", "dr2kit")) or \
        userdirs.cache_dir().name == "dr2kit"
