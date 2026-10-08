"""``python -m dr2kit`` runs the ``dr2`` command (handy when the script isn't on PATH)."""
import sys

from .cli.main import main

if __name__ == "__main__":  # guard: worker processes re-import this module (census --reencode)
    sys.exit(main())
