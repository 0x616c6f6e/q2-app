"""Compatibility entry for Music 0.2 real API integration tests (using a local fixture)."""

import argparse
from pathlib import Path
from test_ncm_ui import check

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    check(args.runner.resolve(), args.artifacts.resolve())
