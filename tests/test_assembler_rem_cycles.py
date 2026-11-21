import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import victor_sovereign_assembler as assembler_module


class AssemblerRemCycleAccountingTests(unittest.TestCase):
    def _run(self, rem_cycles, initial_state=None):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "victor_state.json"
            if initial_state is not None:
                state_path.write_text(json.dumps(initial_state), encoding="utf-8")

            assembler = assembler_module.VictorPuzzleAssembler(
                autonomous=True,
                rem_cycles=rem_cycles,
            )
            with patch.object(assembler_module, "STATE_FILE", state_path):
                if initial_state is not None:
                    assembler.load_state()
                assembler.discover_pieces()
                # Match run_victor.py: assemble after optional state restore.
                assembler.assemble()
                with patch.object(assembler_module.time, "sleep", return_value=None):
                    assembler.autonomous_loop()
                persisted = json.loads(state_path.read_text(encoding="utf-8"))
            return assembler.context, persisted

    def test_fresh_run_counts_exactly_the_requested_cycles(self):
        context, persisted = self._run(rem_cycles=3)
        for state in (context, persisted):
            self.assertEqual(state["rem_cycle_count"], 3)
            self.assertEqual(state["rem_cycles_completed"], 3)
            self.assertEqual(state["last_rem"], 3)
            self.assertEqual(
                sorted(key for key in state["memory_store"] if key.startswith("rem_")),
                ["rem_1", "rem_2", "rem_3"],
            )

    def test_resume_continues_cumulative_counter_without_resetting_to_local_index(self):
        initial_state = {
            "victor_active": True,
            "fully_assembled": True,
            "rem_cycle_count": 5,
            "rem_cycles_completed": 5,
            "last_rem": 5,
            "memory_store": {"rem_5": {"consolidated": True}},
        }
        context, persisted = self._run(rem_cycles=2, initial_state=initial_state)
        for state in (context, persisted):
            self.assertEqual(state["rem_cycle_count"], 7)
            self.assertEqual(state["rem_cycles_completed"], 7)
            self.assertEqual(state["last_rem"], 7)
            self.assertEqual(
                sorted(key for key in state["memory_store"] if key.startswith("rem_")),
                ["rem_5", "rem_6", "rem_7"],
            )


if __name__ == "__main__":
    unittest.main()
