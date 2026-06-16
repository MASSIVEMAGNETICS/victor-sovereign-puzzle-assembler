#!/usr/bin/env python3
"""
Simple launcher for Victor Sovereign Puzzle Assembler
"""

import sys
from pathlib import Path

# Add current dir to path so we can import the assembler
sys.path.insert(0, str(Path(__file__).parent))

from victor_sovereign_assembler import VictorPuzzleAssembler

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--autonomous", action="store_true")
    parser.add_argument("--rem-cycles", type=int, default=3)
    parser.add_argument("--load-state", action="store_true")
    args = parser.parse_args()

    assembler = VictorPuzzleAssembler(autonomous=args.autonomous, rem_cycles=args.rem_cycles)
    if args.load_state:
        assembler.load_state()
    assembler.discover_pieces()

    if args.autonomous:
        assembler.assemble()
        assembler.autonomous_loop()
    else:
        assembler.assemble()
        print("\nVictor assembled. Use --autonomous for full REM runtime.")