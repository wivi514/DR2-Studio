"""Mod packages: a folder of editable files → patched game archives.

A mod is a folder holding ``mod.toml`` and a ``replace/`` tree that mirrors the game's
virtual paths (docs/ARCHITECTURE.md §Mod package format; modder guide:
docs/modding/06-mod-packages.md)::

    red_apron/
      mod.toml
      replace/data/models/npcs.big/boss_mechanic.tex/mech_apron_cm.png

Modules:
    manifest  read and check ``mod.toml``; list the overrides a mod carries
    build     turn the overrides into whole replacement files (re-pack, re-compress)
    deploy    copy a build into a recomp's ``assets/game_mods/`` (or anywhere)
"""
