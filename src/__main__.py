#!/usr/bin/env python3
"""a8s-browser — a persistent browser session addressable as an a8s seat."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import main

if __name__ == "__main__":
    sys.exit(main())
