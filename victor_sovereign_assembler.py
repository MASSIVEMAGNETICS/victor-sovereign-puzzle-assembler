#!/usr/bin/env python3
"""
Victor Sovereign Puzzle Assembler
The master super script that discovers, validates, assembles, and runs Victor
from modular puzzle pieces. Automated. Autonomously. Bloodline-locked.

Each piece in pieces/ is a self-contained capability.
The assembler solves the puzzle (dependency ordering) and brings Victor to life.
"""

import os
import sys
import json
import time
import importlib.util
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# === Bloodline Lock (Immutable) ===
BLOODLINE_SIGNATURE = "Bando_Tori_Victor_1988_Lorain_SteelCity"
BLOODLINE_LOCK = True

# === Configuration ===
PIECES_DIR = Path(__file__).parent / "pieces"
STATE_FILE = Path(__file__).parent / "victor_state.json"
LOG_FILE = Path(__file__).parent / "victor_assembler.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | VICTOR | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("VictorAssembler")


class VictorPuzzleAssembler:
    """
    The sovereign master assembler.
    Discovers puzzle pieces, validates bloodline, resolves dependencies,
    assembles context, and runs autonomous REM-style cycles.
    """

    def __init__(self, autonomous: bool = False, rem_cycles: int = 3):
        self.autonomous = autonomous
        self.rem_cycles = rem_cycles
        self.pieces: Dict[str, Any] = {}
        self.context: Dict[str, Any] = {
            "bloodline": BLOODLINE_SIGNATURE,
            "assembled_at": datetime.utcnow().isoformat(),
            "victor_active": False,
            "rem_cycle_count": 0,
            "empire_revenue_active": False,
        }
        self.dependency_graph: Dict[str, List[str]] = {}
        self.assembly_order: List[str] = []

        logger.info("Victor Sovereign Puzzle Assembler initialized")
        logger.info(f"Bloodline lock: {BLOODLINE_SIGNATURE}")

    def discover_pieces(self) -> None:
        """Discover all valid puzzle pieces in the pieces/ directory."""
        if not PIECES_DIR.exists():
            logger.error(f"Pieces directory not found: {PIECES_DIR}")
            return

        for py_file in sorted(PIECES_DIR.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            piece_name = py_file.stem
            try:
                spec = importlib.util.spec_from_file_location(piece_name, py_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Validate bloodline signature
                if not hasattr(module, "BLOODLINE_SIGNATURE"):
                    logger.warning(f"Piece {piece_name} missing BLOODLINE_SIGNATURE — skipping")
                    continue

                if module.BLOODLINE_SIGNATURE != BLOODLINE_SIGNATURE:
                    logger.warning(f"Piece {piece_name} has invalid bloodline signature — skipping")
                    continue

                metadata = getattr(module, "METADATA", {"name": piece_name, "version": "0.0.0"})
                dependencies = metadata.get("dependencies", [])

                self.pieces[piece_name] = {
                    "module": module,
                    "metadata": metadata,
                    "dependencies": dependencies,
                    "assemble": getattr(module, "assemble", None),
                    "health_check": getattr(module, "health_check", None),
                    "rem_cycle": getattr(module, "rem_cycle", None),
                }

                self.dependency_graph[piece_name] = dependencies
                logger.info(f"Discovered valid piece: {piece_name} v{metadata.get('version')}")

            except Exception as e:
                logger.error(f"Failed to load piece {piece_name}: {e}")

        logger.info(f"Total valid puzzle pieces discovered: {len(self.pieces)}")

    def resolve_assembly_order(self) -> List[str]:
        """Topological sort to determine correct assembly order (puzzle solving)."""
        visited = set()
        order = []

        def visit(node: str):
            if node in visited:
                return
            visited.add(node)
            for dep in self.dependency_graph.get(node, []):
                if dep in self.pieces:
                    visit(dep)
            order.append(node)

        for piece in self.pieces:
            visit(piece)

        self.assembly_order = order
        logger.info(f"Resolved assembly order: {' → '.join(order)}")
        return order

    def assemble(self) -> Dict[str, Any]:
        """Assemble all pieces into a running Victor context."""
        logger.info("=== BEGINNING VICTOR ASSEMBLY ===")

        self.resolve_assembly_order()

        for piece_name in self.assembly_order:
            piece = self.pieces[piece_name]
            assemble_fn = piece["assemble"]

            if assemble_fn is None:
                logger.warning(f"Piece {piece_name} has no assemble() function — skipping")
                continue

            try:
                logger.info(f"Assembling piece: {piece_name}")
                new_context = assemble_fn(self.context)
                if isinstance(new_context, dict):
                    self.context.update(new_context)
                self.context[f"{piece_name}_assembled"] = True
                logger.info(f"✓ {piece_name} assembled successfully")
            except Exception as e:
                logger.error(f"Failed to assemble {piece_name}: {e}")
                self.context[f"{piece_name}_error"] = str(e)

        self.context["victor_active"] = True
        self.context["fully_assembled"] = True
        logger.info("=== VICTOR ASSEMBLY COMPLETE ===")
        logger.info(f"Active capabilities: {list(self.context.keys())}")

        self._save_state()
        return self.context

    def run_rem_cycle(self, cycle_num: int) -> None:
        """Run a REM-style persistence and reflection cycle across pieces."""
        logger.info(f"\n=== REM CYCLE {cycle_num} ===")
        self.context["rem_cycle_count"] = cycle_num

        for piece_name, piece in self.pieces.items():
            rem_fn = piece.get("rem_cycle")
            if rem_fn:
                try:
                    result = rem_fn(self.context)
                    if result:
                        self.context.update(result)
                    logger.info(f"  REM reflection from {piece_name}")
                except Exception as e:
                    logger.warning(f"  REM cycle error in {piece_name}: {e}")

        # Simple persistence snapshot
        self._save_state()
        logger.info(f"REM cycle {cycle_num} complete. State persisted.")

    def health_check_all(self) -> Dict[str, Any]:
        """Run health checks across all assembled pieces."""
        health_report = {"overall": "healthy", "pieces": {}}

        for piece_name, piece in self.pieces.items():
            health_fn = piece.get("health_check")
            if health_fn:
                try:
                    report = health_fn(self.context)
                    health_report["pieces"][piece_name] = report
                except Exception as e:
                    health_report["pieces"][piece_name] = {"status": "error", "error": str(e)}
                    health_report["overall"] = "degraded"

        logger.info(f"Health check: {health_report['overall']}")
        return health_report

    def autonomous_loop(self) -> None:
        """Main autonomous runtime loop with REM cycles and self-monitoring."""
        if not self.context.get("victor_active"):
            logger.warning("Victor not yet assembled. Running assembly first...")
            self.assemble()

        logger.info("=== ENTERING AUTONOMOUS MODE ===")
        logger.info("Victor is now self-running. Press Ctrl+C to interrupt.")

        try:
            for cycle in range(1, self.rem_cycles + 1):
                self.run_rem_cycle(cycle)
                health = self.health_check_all()

                # Simple self-evolution hook (can be expanded with skill genesis)
                if health["overall"] != "healthy":
                    logger.info("Degraded health detected — triggering self-reflection / evolution hook")
                    # Future: call into victor-sovereign-skill-genesis or generate new piece

                time.sleep(2)  # Simulate cycle timing (adjust for real use)

            logger.info("Autonomous run complete. Victor remains persistent.")

        except KeyboardInterrupt:
            logger.info("\nAutonomous mode interrupted by user. Victor state saved.")

        self._save_state()

    def _save_state(self) -> None:
        """Persist current Victor context."""
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self.context, f, indent=2, default=str)
            logger.debug(f"State saved to {STATE_FILE}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def load_state(self) -> None:
        """Load previous Victor state if available."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    saved = json.load(f)
                self.context.update(saved)
                logger.info("Previous Victor state loaded")
            except Exception as e:
                logger.warning(f"Could not load previous state: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Victor Sovereign Puzzle Assembler")
    parser.add_argument("--autonomous", action="store_true", help="Run in autonomous REM mode")
    parser.add_argument("--rem-cycles", type=int, default=3, help="Number of REM cycles to run")
    parser.add_argument("--load-state", action="store_true", help="Load previous state if available")
    args = parser.parse_args()

    assembler = VictorPuzzleAssembler(autonomous=args.autonomous, rem_cycles=args.rem_cycles)

    if args.load_state:
        assembler.load_state()

    assembler.discover_pieces()

    if not assembler.pieces:
        logger.error("No valid puzzle pieces found. Victor cannot be assembled.")
        sys.exit(1)

    if args.autonomous:
        assembler.assemble()
        assembler.autonomous_loop()
    else:
        context = assembler.assemble()
        print("\n=== VICTOR ASSEMBLED ===")
        print(json.dumps(context, indent=2, default=str))
        health = assembler.health_check_all()
        print("\n=== HEALTH REPORT ===")
        print(json.dumps(health, indent=2))


if __name__ == "__main__":
    main()