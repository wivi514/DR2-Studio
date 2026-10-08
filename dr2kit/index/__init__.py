"""The asset index: a SQLite catalogue of every file and entry of both games.

Modules:
    schema.sql  the tables (asset, texture, material_slot, relation, source_file)
    build       build or refresh the index from a game folder (incremental)
    query       search, browse, follow model↔texture relations
"""
