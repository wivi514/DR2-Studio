# Adding a format

The steps every file format goes through in this toolkit, in order. They were written
while doing the `.big` container in phase 1; `.bct` textures (phase 2) will be the next
format through them, and this page will be refined then.

Each step ends with something you can check. Don't start a step before the previous
one's check passes.

## 1. Find every file of the type, in both games

Before reading a single byte, know the population: how many files of this type exist,
where, and in which game. `dr2 census` already lists every extension and every content
kind (the first bytes after decompression) for both games:

```
dr2 census -q > census.txt
```

Look for your type under "entry extensions" and "content by extension". For example,
`.bct` textures turned out to also hide, without an extension, inside every `.tex` pack.

**Check:** you can say "N files in CZ, M in CW, found in these archives".

## 2. Write down what you know in `formats.md` first

Add (or update) the format's section in [`../formats.md`](../formats.md): the layout as
far as known, the byte order of each structure (it can change inside one file:
CLAUDE.md rule 1), and a status (❓ / 🟡 / ✅). Every claim says how it was checked.

## 3. Write the reader

`dr2kit/formats/<name>.py` (or `dr2kit/container/` for containers). Follow
`container/big.py`:

- A module docstring with *what*, *why*, the key facts, and a link to `formats.md`.
- Parse into a dataclass. Keep **everything** you'd need to write the file back,
  including fields you don't understand (`flags` in `.big`: meaning unknown, preserved).
- Check consistency before trusting anything (sizes add up, offsets inside the file)
  and raise `FormatError` naming the file and the failed check. Never return half a
  result, and never skip silently (rule 6).
- Constants get names and a comment saying how the value is known.

## 4. Add it to the census

Count what the reader sees in `dr2kit/census.py`: values of each header field, unusual
cases, and anything that failed to parse, added to `rep.problems`. Run it on both games:

```
dr2 census
```

**Check:** zero problems in both games, or each one named and explained. A structural
constant seen in one family of files belongs to that family until a second family agrees
(rule 7): the census is how you find out.

## 5. Update `formats.md` with the census results

Totals for both games, value histograms, and the status. If a census contradicts an
earlier claim, **keep the old claim and mark it retracted**, saying what was wrong and
how it was found (see the `.bct` magic retraction in `formats.md`).

## 6. Write the writer, and the round-trip gate

The writer's first test: `parse(data).to_bytes() == data` for every file of the type in
both games. Put that check in the census. Unit tests cover edits on synthetic data
(change one field, write, read back).

**Check:** round trip identical for every file in both games.

## 7. Unit tests

`tests/test_<name>.py`. Build inputs in code. Include at least one input laid out *by
hand from the spec* (so reader and writer can't share a mistake) and the damaged-input
cases. See [`testing.md`](testing.md).

## 8. Converter and CLI

Conversion to a format people can edit (PNG, glTF, WAV, JSON) goes in `dr2kit/convert/`.
Expose it through the `dr2` command (a `cmd_<name>` in `dr2kit/cli/main.py`, no format
logic there).

## 9. Docs

- [`code-tour.md`](code-tour.md): the new module.
- A modder guide in [`../modding/`](../modding/README.md) when modders can now do
  something new.
- [`../glossary.md`](../glossary.md): new terms.
- [`../devlog.md`](../devlog.md): what you did and learned.

## 10. GUI viewer (phase 2 on)

A viewer for the type in DR2 Studio. The page on Studio's structure (`studio.md`) is
written in phase 2.
