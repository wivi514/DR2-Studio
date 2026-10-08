"""Exceptions shared by every dr2kit module.

Why a shared hierarchy: front ends (the CLI, DR2 Studio) catch `Dr2Error` to show a
readable message instead of a traceback, while bugs (anything else) still surface as
tracebacks. A reader that cannot parse something raises `FormatError` naming *what* and
*where*; it never returns partial data silently (CLAUDE.md, hard-won rule 6).
"""


class Dr2Error(Exception):
    """Base class for every error the toolkit raises on purpose."""


class FormatError(Dr2Error):
    """A file or entry does not match the format we know.

    The message names the file (or virtual path) and the check that failed, so the
    report is useful on its own.
    """


class LzxError(FormatError):
    """A compressed stream could not be decoded, or decoded to the wrong length."""


class GameNotFoundError(Dr2Error):
    """No data folder could be found for a game profile."""


class VPathError(Dr2Error):
    """A virtual path does not lead to an entry (missing name, or not an archive)."""
