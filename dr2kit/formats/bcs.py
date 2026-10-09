"""String banks (`.bcs`): every piece of text the games show, by number.

Why this exists: menus, subtitles, case-file text, item descriptions and tutorials are
not in the layouts or scripts; those name a **string id** and the game looks the text up
in the bank of the current language, ``data/frontend/str_<lang>.bcs``. Changing what the
game says means editing a bank; this module reads and writes them, and converts them to
JSON a modder can edit (`to_json` / `from_json`, `apply`).

Layout (little-endian, like the ``.big`` index; checked on all 8 banks of both games)::

    u32 n
    u32 ids[n]        strictly increasing (1 .. 99999)
    u32 offsets[n]    from the start of the file; the first is 4 + 8n
    strings           UTF-8, NUL-terminated, in id order, back to back
    zero padding      to a size shared by every bank of the game (below)

Measured facts (docs/formats.md §Strings; CLAUDE.md rule 7, both games):

* Every bank of a game has the **same ids** (CZ 7,599, CW 2,469) and the **same file
  size** (CZ 441,496 B, CW 120,418 B): each is zero-padded to the size of the largest,
  ``str_lg``. `StringBank.size` keeps that size so an unedited bank writes back
  byte-identical; an edited bank is padded to it when it fits and written unpadded
  when it doesn't. Unpadded and larger banks load in game: the CZ recomp's
  ``gen_pc_options.py`` and KB/M tools have shipped rebuilt banks of other sizes.
* ``str_en/fr/it/es/ja/ko`` are the six languages; ``str_id`` holds each string's
  **label** (``IDS_START_DEMO``), ``str_lg`` legal and pre-language-select text (CZ
  recomp, localization-and-bootskip-plan.md). `labels` reads ``str_id``.
* **Markup**: ``[RRGGBBAA,text]`` colours ``text``; ``[@name]`` draws an icon (a button,
  a map icon). Every string that uses either starts with ``@`` (all 8 banks, both
  games): the ``@`` turns markup on. `markup_problems` checks an edited string for it.
  ``%s`` / ``%d`` / ``%0`` … are filled in by the game: keep them.
* The last id of CZ's banks is 99999, labelled
  ``IDS_LAST_LETTER_OF_LAST_STRING_IS_ALWAYS_MISSING`` (its text: "Yeap, its always
  missing."). A string added after it would be the last one, so `apply` refuses new ids
  above the game's last id.

Every reader check names the file and what failed (rule 6): offsets that don't follow
each other, text that isn't UTF-8, non-zero bytes in the padding.
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field

from ..errors import FormatError

JSON_FORMAT = "dr2kit strings v1"
LANGUAGES = ("en", "fr", "it", "es", "ja", "ko")     # what a player can pick
LABEL_BANK = "str_id"                                # IDS_* names
MAX_ID = 0xFFFFFFFF
_MARKUP = re.compile(r"\[(?:[0-9A-Fa-f]{8},|@)")
_PLACEHOLDER = re.compile(r"%[-+0#]*\d*(?:\.\d+)?[sdifuxX]|%\d")


@dataclass
class StringBank:
    """A parsed bank: ``strings`` maps id → text, in id order; ``size`` the stored file
    size (the padding target, 0 for none)."""
    strings: dict[int, str] = field(default_factory=dict)
    size: int = 0

    @classmethod
    def parse(cls, data: bytes, where: str = "<bcs>") -> "StringBank":
        """Read a bank. Raises `FormatError` naming ``where`` and the failed check."""
        if len(data) < 4:
            raise FormatError(f"{where}: {len(data)} bytes, too short for a string bank")
        n = struct.unpack_from("<I", data, 0)[0]
        header = 4 + 8 * n
        if header > len(data):
            raise FormatError(f"{where}: {n} strings need a {header}-byte table, "
                              f"file has {len(data)} bytes")
        ids = struct.unpack_from(f"<{n}I", data, 4)
        offs = struct.unpack_from(f"<{n}I", data, 4 + 4 * n)
        strings: dict[int, str] = {}
        pos = header
        last = -1
        for k, (i, off) in enumerate(zip(ids, offs)):
            if i <= last:
                raise FormatError(f"{where}: id {i} (string {k}) does not follow {last}")
            if off != pos:
                raise FormatError(f"{where}: string {k} (id {i}) at {off:#x}, expected "
                                  f"{pos:#x} (strings are back to back in id order)")
            end = data.find(b"\0", off)
            if end < 0:
                raise FormatError(f"{where}: string {k} (id {i}) has no end (NUL)")
            try:
                strings[i] = data[off:end].decode("utf-8")
            except UnicodeDecodeError as e:
                raise FormatError(f"{where}: id {i} is not UTF-8 ({e})") from None
            pos = end + 1
            last = i
        if any(data[pos:]):
            raise FormatError(f"{where}: {len(data) - pos} bytes after the last string "
                              f"are not all zero (unknown data)")
        return cls(strings, len(data) if pos < len(data) else 0)

    def to_bytes(self) -> bytes:
        """Write the bank (ids sorted), zero-padded to ``size`` when the text fits."""
        ids = sorted(self.strings)
        n = len(ids)
        blob = bytearray()
        offs = []
        for i in ids:
            if not 0 <= i <= MAX_ID:
                raise FormatError(f"string id {i} is out of range")
            offs.append(4 + 8 * n + len(blob))
            text = self.strings[i]
            if "\0" in text:
                raise FormatError(f"string {i} contains a NUL character")
            blob += text.encode("utf-8") + b"\0"
        out = struct.pack(f"<I{n}I{n}I", n, *ids, *offs) + bytes(blob)
        if len(out) < self.size:
            out += bytes(self.size - len(out))
        return out

    @property
    def last_id(self) -> int:
        return max(self.strings) if self.strings else 0


def bank_name(vpath: str) -> str:
    """``data/frontend/str_en.bcs`` → ``str_en``."""
    return vpath.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()


def to_json(bank: StringBank, vpath: str, labels: dict[int, str] | None = None) -> str:
    """The bank as editable JSON: ``{"format", "bank", "strings": {"<id>": text}}``,
    plus ``"labels"`` (id → ``IDS_…`` name, from ``str_id``) when given."""
    doc: dict = {"format": JSON_FORMAT, "bank": vpath,
                 "strings": {str(i): t for i, t in bank.strings.items()}}
    if labels:
        doc["labels"] = {str(i): labels[i] for i in bank.strings if i in labels}
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def from_json(text: str, where: str = "<json>",
              by_label: dict[str, int] | None = None) -> dict[int, str]:
    """The ``strings`` of a JSON file written by `to_json` (or by hand: a mod override
    holds only the strings it changes). A key is an id (``"3"``) or, when ``by_label``
    (``IDS_…`` → id) is given, a label (``"IDS_START_DEMO"``). Raises `FormatError`
    saying what is wrong."""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise FormatError(f"{where}: not valid JSON ({e})") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("strings"), dict):
        raise FormatError(f'{where}: needs a "strings" object ({{"<id>": "text"}})')
    if doc.get("format", JSON_FORMAT) != JSON_FORMAT:
        raise FormatError(f"{where}: format {doc['format']!r}, expected {JSON_FORMAT!r}")
    out: dict[int, str] = {}
    for k, v in doc["strings"].items():
        if not isinstance(v, str):
            raise FormatError(f"{where}: string {k!r} must be text, got {type(v).__name__}")
        key = str(k).strip()
        if by_label and key.upper() in by_label:
            key = str(by_label[key.upper()])
        if not key.isdigit():
            raise FormatError(f"{where}: {k!r} is not a string id (a number such as "
                              f'"3"; find ids with dr2 strings search)')
        out[int(key)] = v
    return out


def markup_problems(text: str) -> list[str]:
    """What the game will show wrong in ``text``: markup without the leading ``@``,
    unbalanced brackets."""
    out = []
    if _MARKUP.search(text) and not text.startswith("@"):
        out.append("uses [..] markup but doesn't start with @, so the brackets are shown "
                   "as text (start it with @)")
    if text.startswith("@") and text.count("[") != text.count("]"):
        out.append(f"{text.count('[')} '[' but {text.count(']')} ']'")
    return out


def apply(bank: StringBank, changes: dict[int, str], where: str = "") -> tuple[StringBank, list[str]]:
    """``bank`` with ``changes`` applied (new ids allowed below the last id). Returns
    the new bank and notes for the modder (markup, placeholders, added ids)."""
    notes = []
    pre = f"{where}: " if where else ""
    new = dict(bank.strings)
    last = bank.last_id
    added = []
    for i, text in sorted(changes.items()):
        if i not in new:
            if i >= last:
                raise FormatError(f"{pre}id {i} is not in the bank, and new ids must be "
                                  f"below its last id {last} (the game drops the last "
                                  f"letter of the last string)")
            added.append(i)
        else:
            old = set(_PLACEHOLDER.findall(new[i]))
            now = set(_PLACEHOLDER.findall(text))
            if old != now:
                notes.append(f"{pre}id {i}: the original fills in {sorted(old) or 'nothing'}, "
                             f"yours {sorted(now) or 'nothing'}; the game may show garbage "
                             f"or crash")
        notes += [f"{pre}id {i}: {p}" for p in markup_problems(text)]
        new[i] = text
    if added:
        notes.append(f"{pre}{len(added)} new id(s) ({', '.join(map(str, added[:5]))}"
                     f"{'…' if len(added) > 5 else ''}); nothing shows them until a layout "
                     f"or script names them")
    return StringBank(new, bank.size), notes


def labels(label_bank: StringBank) -> dict[int, str]:
    """id → ``IDS_…`` label, from a parsed ``str_id.bcs``."""
    return dict(label_bank.strings)
