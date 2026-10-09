"""PyInstaller entry point: DR2 Studio (the windowed executable of a release)."""
import sys

from dr2kit.studio.app import main

sys.exit(main(sys.argv[1:]))
