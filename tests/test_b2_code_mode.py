"""B2 offline tests: runs without router, provider API key, or network."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from b2_code_mode import (RAW_MARKER, LocalLogTools, analyze, ask, generate,
                          load_json, run_code, verify)


class FakePlanner:
    def __init__(self):
        self.calls = []

    def _ask_text(self, instructions, user_text):
        self.calls.append((instructions, user_text))
        assert RAW_MARKER not in user_text
        assert "diagnostic=synthetic_data" not in user_text
        return "Lỗi REFRESH_RACE xuất hiện nhiều nhất trong dữ liệu mô phỏng."


class TestCodeMode(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.logs = self.root / "logs"
        self.data = self.root / "results"
        generate(self.logs, num_files=60, lines_per_file=60)

    def tearDown(self):
        self.temp.cleanup()

    def test_runtime_aggregates_locally(self):
        tools = LocalLogTools(self.logs)
        result = run_code(tools)
        self.assertEqual(tools.files_read, 60)
        self.assertEqual(tools.lines_read, 3600)
        self.assertEqual(result["error_counts"][0]["code"], "REFRESH_RACE")
        self.assertNotIn(RAW_MARKER, str(result))

    def test_does_not_return_raw_logs_to_llm(self):
        analyze(self.logs, self.data)
        p = FakePlanner()
        answer = ask(self.data, p)
        self.assertIn("REFRESH_RACE", answer)
        self.assertEqual(len(p.calls), 1)
        self.assertTrue(verify(self.data))

    def test_verify_requires_real_or_fake_llm_response(self):
        analyze(self.logs, self.data)
        self.assertFalse(verify(self.data))

    def test_read_file_rejects_outside_path(self):
        tools = LocalLogTools(self.logs)
        extra = self.root / "secret.log"
        extra.write_text("PRIVATE", encoding="utf-8")
        with self.assertRaises(ValueError):
            tools.read_file(extra)


if __name__ == "__main__":
    unittest.main()
