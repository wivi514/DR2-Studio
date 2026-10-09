"""Converters between the game's formats and formats people edit.

Modules:
    png      a small pure-Python PNG reader/writer (Pillow used when present)
    dxt      DXT1/DXT5/DXN block codecs, numpy + pure-Python
    texture  `.bct` ⇄ image: untile, decode, encode, re-tile, mip rebuild
    gltf     scenes ⇄ glTF binary (`.glb`): skeleton, meshes, skin, materials
    model    a model's vpath → `.glb`, its textures found by name
"""
