"""PyInstaller entry point: the `dr2` command of a release."""
import sys

from dr2kit.cli.main import main

sys.exit(main())
