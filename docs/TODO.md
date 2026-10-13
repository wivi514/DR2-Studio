# Things to do (open for anyone)

Work that is understood well enough to start, but that nobody is doing right now. Each
entry says **what** it is, **why** it matters, **everything already found** (so you don't
have to rediscover it), and **where to start**. Take one, open an issue saying so, and
follow the repository's rules (CLAUDE.md: document everything, census before claims,
in-game proof).

| # | Item | Where | State |
|---|---|---|---|
| 1 | [Grow Case West's zombie type table (Case Zero's zombies in Case West)](#1-grow-case-wests-zombie-type-table) | Case West recomp + toolkit | researched, not started (user decision 2026-10-13: later, for a contributor) |

---

## 1. Grow Case West's zombie type table

### What and why

Phase 15 lets a mod use the other game's zombie types **natively**: as real types of their
own, spawned by the game's spawn areas, factories and crates, never swapped for a
"nearest" type (user's decision, `docs/phase15-kickoff.md` decision 1).

Each game's **program** (its executable) holds a fixed table of zombie type names, and it
only spawns names from that table:

* **Case Zero: 32 names**, Dead Rising 2's whole roster (`zombie_fat`, `zombie_cop`,
  `zombie_bride`, `mercenary`, `zombie_gas`, `pro_zombie_cop`…). It ships models for 12,
  so **20 names are empty slots**. A Case West type takes one of them: this direction
  works today (`dr2 mod import-zombie`, `dr2kit/mods/importzombie.py`).
* **Case West: 10 names**, all used (`zombie_fat`, `zombie_fat_female`, `zombie_skinny`,
  `zombie_skinny_female`, `zombie_gas`, `security_heavy`, `security_lab`,
  `security_light`, `security_light_hat`, `zombie_security`). **No empty slot**, so a Case
  Zero type (`zombie_cop`…) has nowhere to go. `importzombie.plan` refuses Case Zero →
  Case West with a message pointing here.

The job: make the **Case West recomp** (`../Dead_Rising_2_Case_West_Xenon_Recomp`) hold a
longer table (Case Zero's 32 is the natural target), so the toolkit can give Case Zero's
types (and new ones) a slot in Case West. This was approved by the repository owner as a
recomp change (`ARCHITECTURE.md` §Recomp integration 3) and then **deferred** on
2026-10-13: it is bigger than first thought (below).

Until it is done, the only way to bring a Case Zero zombie into Case West is to **replace**
one of Case West's 10 types, which is not native and costs that type.

### What was found (2026-10-13, both programs' generated code)

Addresses are guest addresses of each game's image (`assets/game/default_image.bin`, base
`0x82000000`); `sub_XXXXXXXX` are the recompiled functions in each recomp's `ppc/`.

**The table.** An array of `char*` to the type names:

| | Case Zero | Case West |
|---|---|---|
| Table address | `0x829DF688` | `0x829F2598` |
| Entries | 32 | 10 |
| Formed in code as | `lis 0x829E` + `addi -2424` | `lis 0x829F` + `addi 9624` |
| Right after it | Case Zero's own data | the variant table (`0x829F25C0`…: floats, then `{mask, pattern}` records such as `head*,cap_neck*,…`) |

Because data follows the table directly, Case West's table **cannot grow in place**: a
longer table has to live elsewhere (new guest memory, e.g. allocated by the recomp at
boot, or a free area of the image) and every reference must be pointed at it.

**Every reference to the table** (found by scanning all generated code for the two-
instruction address formation; the same scan finds exactly the matching five in Case Zero,
so it can match):

| Case West | Case Zero | What it does | Uses of the count |
|---|---|---|---|
| `sub_822FC948` | `sub_82300068` | **name → type number**: compares a name with each table entry (`ctr = 10` / `32`) | `li r11, 10` |
| `sub_82499870` | `sub_82490780` | uses the type number and walks the table | `cmpwi …, 10` twice; loop end `table + 40` (`10 × 4`) |
| `sub_82585158` | `sub_825B3670` | large (CW 1,231 generated lines); walks the table and the per-type bytes at `this + 700` | `cmpwi …, 10` |
| `sub_82587190` | `sub_825B5B98` | checks a type number `< 10` (`< 32`), then indexes the table | `cmpwi r4, 10` |
| `sub_82588390` | `sub_825B6FC8` | debug print of the loaded types: one byte per type at `this + 700` (CZ `+2196`), loop end `table + 40` (CZ `+128`) | loop end |

Each pair is the **same code** apart from the count and the offsets (compared with the
normalising diff described below).

**The real obstacle: per-type data inline in an object.** The object these functions work
on (`this` in `sub_82588390` / `sub_825B6FC8`; it looks like the zombie load/spawn
manager) keeps **arrays sized by the type count inside itself**:

* a byte per type at Case West `+700` / Case Zero `+2196`;
* the fields after the per-type region sit at Case West `+1812`, `+1920`, `+1924`,
  `+1928` and at Case Zero `+3352`, `+3460`, `+3464`, `+3468`: the same fields,
  **1,540 bytes further** in Case Zero, i.e. about **70 bytes more per extra type**
  (22 extra types), so there are several per-type arrays, not one.

So growing Case West to 32 types means **re-laying out that object**: making it bigger
where it is allocated, and moving every access to a field after the per-type arrays (in
these five functions and in every other function that touches the object) by the right
amount. Changing the count alone would let the arrays run over the following fields.

**A retraction.** The phase 15 notes said "the engine's limit is 32: the type is checked
against 31 (`cmplwi r5, 0x1f`, CZ `0x823000BC`, CW `0x822FC99C`)". Those addresses are
inside the name → type lookup above (CZ `sub_82300068`, CW `sub_822FC948`), and the
compared byte belongs to the *name being looked up*: a string object at `+60` of the
caller's object, whose byte at `+92` decides whether the text is stored inline (value
below 31: compare from `+60` itself) or behind a pointer (load the pointer at `+60`). It is **not** a limit on the type number. Whether
the engine has a hard limit (bit masks per type, 32-bit sets…) is **unknown**; Case
Zero's 32 is that program's table size. Check this before choosing a size.

### How it was found (to reproduce)

* The table: the names' pointer array in the image (`tools/crossgame_table.py` finds each
  game's table from the code that builds its address; the result is in
  `dr2kit/profiles/crossgame.toml`).
* The references: a scan of each recomp's `ppc/ppc_recomp.*.cpp` for a register set to
  the high half (`ctx.rN.s64 = -2103508992` for `0x829F0000`) followed, within 80 lines,
  by `+ 9624` on that register (Case Zero: `-2103574528` and `-2424`).
* The pair comparison: the generated bodies with addresses, labels, function names and
  `lis` values blanked, then a line diff; the remaining differences are the counts and
  the object offsets listed above.

### Where to start

1. **Find the object**: who allocates it (its size in the allocation call, Case West vs
   Case Zero), and its type (vtable, constructor). `sub_82588390`'s caller and the code
   that writes `this + 700` are good entry points.
2. **Map every per-type array** in it: offset, element size, count. Compare the Case West
   and Case Zero constructors field by field; Case Zero's layout is the reference for 32.
3. **Census every access** to the object at or after `+700` in Case West: every function
   taking it (by call graph from the five above and the constructor), every `lwz`/`stw`/
   `lbz`/`stb` with an offset in that range. A change is only safe when this census names
   every site (a site missed is a silent memory overwrite).
4. **Choose the method** and write it down: re-allocate the object bigger and patch each
   offset (C++ overrides of the affected functions in the Case West runtime, as its other
   `runtime/cpu/*.cpp` hooks do), or point the per-type arrays at separately allocated
   memory. Follow the Case West recomp's own CLAUDE.md: an off switch
   (`CW_NO_ZOMBIE_TABLE_GROWTH=1`), a gotcha entry, one change per commit.
5. **Prove it**: headless boot and a save load in Case West with the table grown and no
   mod (nothing changes); then a Case Zero type in a new slot (`dr2 mod import-zombie
   --from cz -g cw`, after making `importzombie.plan` accept it), spawned by retyping a
   crowd (`missions.txt`), seen walking and attacking in game.
6. **Then the toolkit**: lift the refusal in `importzombie.plan`, add Case West's grown
   table to `profiles/crossgame.toml` (or a profile key), extend `dr2 census --import` to
   plan Case Zero's types into Case West, update guide 23.

**Related and also open:** Case West's **level table** (10 slots, only `w_mall` empty)
needs growing for more than one Case Zero map in Case West (phase 15 decision 3). It has
not been examined; it may have the same kind of inline per-level data.

Docs that hold the rest: `docs/formats.md` §"Zombie types: a table in each executable",
`docs/phase15-kickoff.md` §"Zombies" and §Status, `docs/ARCHITECTURE.md` §Recomp
integration 3.
