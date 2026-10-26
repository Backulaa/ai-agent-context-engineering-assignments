"""Offline tests. No 9Router connection or API token required."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from b2_code_mode import RAW_MARKER, generate, load_json
from b2_dynamic_code_mode import (
    BoundedLogTools, ProgramRejected, RestrictedRuntime, ask, execute,
    plan, strip_code_fence, validate_program, verify,
)

GOOD_PROGRAM = '''paths = tools.list_files("*.log")
counts = new_counter()
per_file = new_counter()
for path in paths:
    raw = tools.read_file(path)
    for line in raw.splitlines():
        code = extract_error_code(line)
        if code:
            counter_add(counts, code)
            counter_add(per_file, path.name)
result = make_findings(counts, per_file, tools, 5)
'''


class FakeLLM:
    model = "fake-llm-for-offline-tests"

    def __init__(self, generated=GOOD_PROGRAM):
        self.generated = generated
        self.calls = []

    def _ask_text(self, system, user):
        self.calls.append((system, user))
        assert RAW_MARKER not in system + user
        assert "diagnostic=synthetic_data" not in system + user
        if "Write a PROGRAM" in system:
            return "```python\n" + self.generated.rstrip() + "\n```"
        return "Lỗi REFRESH_RACE có số lần xuất hiện nhiều nhất trong thống kê."


class TestDynamicCodeMode(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.logs = root / "logs"
        self.data = root / "dynamic"
        generate(self.logs, num_files=60, lines_per_file=60)

    def tearDown(self):
        self.temp.cleanup()

    def test_generated_program_executes_without_exec_eval(self):
        tools = BoundedLogTools(self.logs)
        findings = RestrictedRuntime(tools).run(GOOD_PROGRAM)
        self.assertEqual(findings["files_scanned"], 60)
        self.assertEqual(findings["lines_scanned"], 3600)
        self.assertEqual(findings["error_counts"][0]["code"], "REFRESH_RACE")
        self.assertNotIn(RAW_MARKER, str(findings))

    def test_llm_plan_execute_ask_verify_end_to_end_offline(self):
        model = FakeLLM()
        plan(self.data, model)
        self.assertIn("for path", (self.data / "program.txt").read_text(encoding="utf-8"))
        findings = execute(self.data, self.logs)
        self.assertEqual(findings["files_scanned"], 60)
        answer = ask(self.data, model)
        self.assertIn("REFRESH_RACE", answer)
        self.assertTrue(verify(self.data, self.logs))
        self.assertEqual(len(model.calls), 2)
        payload = load_json(self.data / "payload_to_llm.json")
        self.assertNotIn(RAW_MARKER, str(payload))

    def test_block_unsafe_imports(self):
        p = GOOD_PROGRAM + '\nimport os\n'
        with self.assertRaises(ProgramRejected):
            validate_program(p)

    def test_block_shell_and_dynamic_exec(self):
        for code in ('import subprocess\n' + GOOD_PROGRAM,
                     'exec("print(123)")\n' + GOOD_PROGRAM,
                     'open("secret.txt")\n' + GOOD_PROGRAM):
            with self.subTest(code=code[:30]), self.assertRaises(ProgramRejected):
                validate_program(code)

    def test_block_unsafe_attribute_access(self):
        code = GOOD_PROGRAM.replace('path.name', 'path.parent')
        with self.assertRaises(ProgramRejected):
            validate_program(code)

    def test_block_infinite_loop(self):
        code = 'while True:\n    pass\n' + GOOD_PROGRAM
        with self.assertRaises(ProgramRejected):
            validate_program(code)

    def test_block_skipping_files(self):
        code = GOOD_PROGRAM.replace('raw = tools.read_file(path)', 'raw = ""')
        with self.assertRaises(ProgramRejected):
            validate_program(code)

    def test_reject_tampered_program_file(self):
        plan(self.data, FakeLLM())
        (self.data / "program.txt").write_text(GOOD_PROGRAM + "\n# alteration", encoding="utf-8")
        with self.assertRaises(ProgramRejected):
            execute(self.data, self.logs)

    def test_reject_log_symlinks_if_supported(self):
        target = self.logs / "service-000.log"
        other = self.logs / "link.log"
        try:
            other.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaises(ProgramRejected):
            BoundedLogTools(self.logs).list_files("*.log")

    def test_reject_fake_result_that_does_not_count(self):
        code = GOOD_PROGRAM.replace('counter_add(counts, code)', 'counter_add(per_file, path.name)')
        with self.assertRaises(ProgramRejected):
            RestrictedRuntime(BoundedLogTools(self.logs)).run(code)

    def test_reject_bad_generated_code_and_no_fallback(self):
        with self.assertRaises(ProgramRejected):
            plan(self.data, FakeLLM('import os\nresult = 1'))
        self.assertFalse((self.data / 'program.txt').exists())
        self.assertTrue((self.data / 'rejected_program.txt').exists())


if __name__ == "__main__":
    unittest.main()
