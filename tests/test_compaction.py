"""Tests with a fake LLM: no API key, network, or provider fees needed."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Checkpoint, ResumeDecision, do_run, do_resume, do_verify, generate_history


class FakePlanner:
    def compact(self, transcript):
        assert len(transcript) >= 5
        return Checkpoint(
            goal="Fix refresh-token race condition",
            current_state="Concurrent refresh tests failing",
            constraints=["Keep API backward compatible"],
            findings=["Two concurrent refresh calls can reuse same token"],
            failed_attempts=["Increasing token TTL did not help; tests still fail"],
            files=["auth.ts", "session.ts", "auth.test.ts"],
            next_action="Inspect locking around refresh",
        )

    def resume(self, active_context):
        raw = json.dumps(active_context)
        # The fake LLM only gets compacted checkpoint, not verbose raw log.
        assert "request_id=req_" not in raw
        assert "Increasing token TTL" in raw
        return ResumeDecision(
            active_issue="Refresh-token race condition",
            failed_attempts=["Increasing TTL failed"],
            action="inspect_locking",
            reason="TTL was already tried and the lock hasn't been checked",
        )


class TestB1(unittest.TestCase):
    def test_long_history_has_repeated_tool_logs(self):
        history = generate_history(350)
        self.assertIn("request_id=req_00000", str(history))

    def test_checkpoint_and_fresh_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            planner = FakePlanner()
            before, after = do_run(planner, data, threshold=1000, log_lines=350)
            self.assertLess(after, before / 2)
            # Separate invocation; only data on disk carries continuity.
            do_resume(planner, data)
            self.assertTrue(do_verify(data))

    def test_unsafe_checkpoint_does_not_replace_active_history(self):
        class BadPlanner(FakePlanner):
            def compact(self, transcript):
                checkpoint = super().compact(transcript)
                checkpoint.failed_attempts = []
                return checkpoint

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            with self.assertRaises(ValueError):
                do_run(BadPlanner(), data, threshold=1000, log_lines=350)
            self.assertFalse((data / "active_context.json").exists())


if __name__ == "__main__":
    unittest.main()
