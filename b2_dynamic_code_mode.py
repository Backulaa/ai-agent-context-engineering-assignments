"""B2 upgrade: LLM-authored Python-subset program, safely interpreted locally.

The LLM generates the program text, but the program NEVER runs via Python
exec/eval/subprocess. We parse its AST and interpret a strict allowlist of
operations against read-only, bounded log tools. This is a deliberately small
Code Mode teaching harness, NOT an OS-level security sandbox.

Requires the existing main.py and b2_code_mode.py next to this file.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any

from main import OpenAIPlanner, ROOT, load_json, save_json
from b2_code_mode import (
    DATA_DIR as FIXED_DATA_DIR, ERROR_PATTERN, LOG_DIR, QUESTION, RAW_MARKER,
    SYSTEM as ANSWER_SYSTEM, LocalLogTools, build_model_prompt,
    estimate_tokens, run_code as trusted_reference,
)

DYNAMIC_DIR = ROOT / "b2_dynamic_data"
# No log lines or raw file excerpts appear in these prompts.
CODE_SYSTEM = """You are a Code Mode agent. Write a PROGRAM, not an explanation.
You cannot see raw log data. You only know there are local synthetic .log files
with lines such as: 'ERROR code=EXAMPLE_CODE'.

Respond ONLY with Python code (optional ```python fences). NO imports,
functions, classes, print, eval, open, or filesystem calls. Use ONLY this tiny
language and these safe APIs:
- tools.list_files("*.log") -> list of local log paths
- tools.read_file(path) -> local text (never sent to you)
- raw.splitlines() -> text lines (local only)
- extract_error_code(line) -> error code string or None
- new_counter() -> counter
- counter_add(counter, code_or_path_name) -> update counter
- make_findings(counts, per_file, tools, top_k) -> safe structured dict; top_k=1..10

You may use assignment, for-loops, and `if code:`. End with a final assignment
to `result = make_findings(...)`. Track errors by code AND count errors per
file. Do not include or output the raw logs.

Example VALID PROGRAM (you may adapt top_k 1..10):
paths = tools.list_files("*.log")
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
"""
CODE_QUESTION = "Phân tích toàn bộ .log: lỗi nào xuất hiện nhiều nhất, số lần, top 5 file chứa nhiều lỗi?"

MAX_SOURCE_BYTES = 9_000
MAX_AST_NODES = 120
MAX_FILES = 150
MAX_FILE_BYTES = 120_000
MAX_TOTAL_BYTES = 8_000_000
MAX_LINES = 25_000
MAX_OPS = 150_000
MAX_SECONDS = 15.0
ALLOWED_NODES = (
    ast.Module, ast.Assign, ast.Expr, ast.For, ast.If, ast.Name,
    ast.Load, ast.Store, ast.Call, ast.Attribute, ast.Constant,
)
ALLOWED_VARIABLES = {"paths", "counts", "per_file", "path", "raw", "line", "code", "result"}
ALLOWED_GLOBALS = {"tools", "new_counter", "counter_add", "extract_error_code", "make_findings"}
SAFE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
SAFE_FILE_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}\.log$")


class ProgramRejected(ValueError):
    """Invalid generated program: fail closed before interpreting anything."""


def strip_code_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if len(lines) < 3 or lines[-1].strip() != "```" or lines[0].strip() not in ("```", "```python"):
            raise ProgramRejected("Only a single Python code fence is accepted")
        value = "\n".join(lines[1:-1]).strip()
    return value


def validate_program(source: str) -> ast.Module:
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ProgramRejected("Generated source too large")
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise ProgramRejected(f"Invalid Python syntax: {exc.msg}") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES:
        raise ProgramRejected("Program has too many AST nodes")
    for node in nodes:
        if not isinstance(node, ALLOWED_NODES):
            raise ProgramRejected(f"Forbidden Python construct: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in (ALLOWED_VARIABLES | ALLOWED_GLOBALS):
            raise ProgramRejected(f"Unapproved variable or function: {node.id!r}")
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise ProgramRejected("Only simple assignments to variable names are allowed")
            if node.targets[0].id not in ALLOWED_VARIABLES:
                raise ProgramRejected("Cannot overwrite tools or helper functions")
        if isinstance(node, ast.For):
            if not isinstance(node.target, ast.Name) or node.target.id not in {"path", "line"}:
                raise ProgramRejected("Only for path / for line loops are supported")
            if node.orelse:
                raise ProgramRejected("for-else is not supported")
        if isinstance(node, ast.If):
            if not isinstance(node.test, ast.Name) or node.test.id != "code" or node.orelse:
                raise ProgramRejected("Only `if code:` is allowed")
        if isinstance(node, ast.Attribute):
            if node.attr not in {"list_files", "read_file", "splitlines", "name"}:
                raise ProgramRejected(f"Forbidden attribute access: {node.attr}")
        if isinstance(node, ast.Call) and node.keywords:
            raise ProgramRejected("Keyword arguments are not supported")
        if isinstance(node, ast.Constant) and not (type(node.value) in (str, int)):
            raise ProgramRejected("Only string/integer literals are allowed")
    if not tree.body or not isinstance(tree.body[-1], ast.Assign) or (
        tree.body[-1].targets[0].id != "result"
    ):
        raise ProgramRejected("Last statement must be `result = make_findings(...)`")
    # Verify the LLM created an actual tool-using aggregation, not an answer it invented.
    callnames = []
    for node in nodes:
        if isinstance(node, ast.Call):
            f = node.func
            callnames.append(f"{f.value.id}.{f.attr}" if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                             else f.id if isinstance(f, ast.Name) else "UNSUPPORTED")
    required = {"tools.list_files", "tools.read_file", "raw.splitlines", "extract_error_code",
                "new_counter", "counter_add", "make_findings"}
    if not required.issubset(callnames) or len([n for n in nodes if isinstance(n, ast.For)]) < 2:
        raise ProgramRejected("Program must aggregate logs using the required tools and loops")
    last_call = tree.body[-1].value
    if not (isinstance(last_call, ast.Call) and isinstance(last_call.func, ast.Name)
            and last_call.func.id == "make_findings"):
        raise ProgramRejected("Last result must come from make_findings")
    return tree


class BoundedLogTools(LocalLogTools):
    """Read only local log dir; reject links, huge files, and excess reads."""

    def __init__(self, log_dir: Path):
        super().__init__(log_dir)
        self._read_names: set[str] = set()

    def list_files(self, pattern: str = "*.log") -> list[Path]:
        paths = super().list_files(pattern)
        if len(paths) == 0 or len(paths) > MAX_FILES:
            raise ProgramRejected(f"Expected 1..{MAX_FILES} log files")
        if any(p.is_symlink() for p in paths):
            raise ProgramRejected("Symbolic link log files are forbidden")
        return paths

    def read_file(self, path: Path) -> str:
        if not isinstance(path, Path) or path.is_symlink():
            raise ProgramRejected("read_file requires an approved non-symlink path")
        resolved = path.resolve()
        if not resolved.is_relative_to(self.log_dir) or resolved.suffix != ".log":
            raise ProgramRejected("Attempt to read outside approved logs")
        if path.name in self._read_names:
            raise ProgramRejected("Each log file may be read only once")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ProgramRejected("Log file too large")
        if self.bytes_read + path.stat().st_size > MAX_TOTAL_BYTES:
            raise ProgramRejected("Total log read budget exceeded")
        text = super().read_file(path)
        self._read_names.add(path.name)
        if self.lines_read > MAX_LINES:
            raise ProgramRejected("Line count budget exceeded")
        return text


class RestrictedRuntime:
    """Tiny AST interpreter. NEVER execs Python or exposes Python built-ins."""

    def __init__(self, tools: BoundedLogTools):
        self.tools = tools
        self.env: dict[str, Any] = {}
        self.ops = 0
        self.start = time.monotonic()

    def tick(self) -> None:
        self.ops += 1
        if self.ops > MAX_OPS or time.monotonic() - self.start > MAX_SECONDS:
            raise ProgramRejected("Execution budget exceeded")

    def expr(self, node: ast.AST) -> Any:
        self.tick()
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id == "tools":
                return self.tools
            if node.id not in self.env:
                raise ProgramRejected(f"Variable is not initialized: {node.id}")
            return self.env[node.id]
        if isinstance(node, ast.Attribute):
            if node.attr == "name" and isinstance(node.value, ast.Name) and node.value.id == "path":
                value = self.expr(node.value)
                if isinstance(value, Path):
                    return value.name
            raise ProgramRejected("Only path.name may be accessed as a value")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                obj, method = node.func.value.id, node.func.attr
                if obj == "tools" and method == "list_files" and len(node.args) == 1:
                    pattern = self.expr(node.args[0])
                    if pattern != "*.log":
                        raise ProgramRejected("Only tools.list_files('*.log') is allowed")
                    return self.tools.list_files(pattern)
                if obj == "tools" and method == "read_file" and len(node.args) == 1:
                    return self.tools.read_file(self.expr(node.args[0]))
                if obj == "raw" and method == "splitlines" and len(node.args) == 0:
                    raw = self.expr(node.func.value)
                    if type(raw) is not str:
                        raise ProgramRejected("raw.splitlines requires text")
                    return raw.splitlines()
            if not isinstance(node.func, ast.Name):
                raise ProgramRejected("Unapproved function/method call")
            name = node.func.id
            if name == "new_counter" and not node.args:
                return Counter()
            if name == "extract_error_code" and len(node.args) == 1:
                line = self.expr(node.args[0])
                if type(line) is not str:
                    raise ProgramRejected("extract_error_code requires a log line")
                match = ERROR_PATTERN.search(line)
                return match.group(1) if match else None
            if name == "counter_add" and len(node.args) == 2:
                ctr, key = (self.expr(x) for x in node.args)
                if not isinstance(ctr, Counter) or type(key) is not str or not (
                    SAFE_CODE_RE.fullmatch(key) or SAFE_FILE_RE.fullmatch(key)
                ):
                    raise ProgramRejected("counter_add requires a safe code or log filename")
                ctr[key] += 1
                return None
            if name == "make_findings" and len(node.args) == 4:
                counts, per_file, tools, top_k = (self.expr(x) for x in node.args)
                if not isinstance(counts, Counter) or not isinstance(per_file, Counter) or tools is not self.tools:
                    raise ProgramRejected("make_findings requires two counters and tools")
                if type(top_k) is not int or not 1 <= top_k <= 10:
                    raise ProgramRejected("top_k must be 1..10")
                return {
                    "dataset": "synthetic local log data",
                    "files_scanned": tools.files_read,
                    "lines_scanned": tools.lines_read,
                    "error_events": sum(counts.values()),
                    "error_counts": [{"code": k, "count": v} for k, v in
                                     sorted(counts.items(), key=lambda item: (-item[1], item[0]))],
                    "top_5_files": [{"file": k, "errors": v} for k, v in
                                    sorted(per_file.items(), key=lambda item: (-item[1], item[0]))[:top_k]],
                    "note": "Counts only; does not prove root cause.",
                }
            raise ProgramRejected(f"Unapproved helper call: {name}")
        raise ProgramRejected(f"Expression not supported: {type(node).__name__}")

    def statements(self, body: list[ast.stmt]) -> None:
        for stmt in body:
            self.tick()
            if isinstance(stmt, ast.Assign):
                self.env[stmt.targets[0].id] = self.expr(stmt.value)
            elif isinstance(stmt, ast.Expr):
                if not (isinstance(stmt.value, ast.Call)
                        and isinstance(stmt.value.func, ast.Name)
                        and stmt.value.func.id == "counter_add"):
                    raise ProgramRejected("Only counter_add may be used as a statement")
                self.expr(stmt.value)
            elif isinstance(stmt, ast.If):
                if bool(self.expr(stmt.test)):
                    self.statements(stmt.body)
            elif isinstance(stmt, ast.For):
                iterable = self.expr(stmt.iter)
                name = stmt.target.id
                if name == "path" and (not isinstance(iterable, list) or not all(isinstance(x, Path) for x in iterable)):
                    raise ProgramRejected("for path must iterate log paths")
                if name == "line" and (not isinstance(iterable, list) or not all(type(x) is str for x in iterable)):
                    raise ProgramRejected("for line must iterate raw.splitlines()")
                for value in iterable:
                    self.tick()
                    self.env[name] = value
                    self.statements(stmt.body)
            else:
                raise ProgramRejected(f"Unapproved statement: {type(stmt).__name__}")

    def run(self, source: str) -> dict[str, Any]:
        tree = validate_program(source)
        self.statements(tree.body)
        findings = self.env.get("result")
        if type(findings) is not dict or not findings.get("error_counts"):
            raise ProgramRejected("Program must produce non-empty structured findings")
        total_files = len(self.tools.list_files("*.log"))
        if findings["files_scanned"] != total_files or findings["lines_scanned"] == 0:
            raise ProgramRejected("Program did not read all log files")
        if RAW_MARKER in json.dumps(findings) or "diagnostic=synthetic_data" in json.dumps(findings):
            raise ProgramRejected("Raw logs leaked into output")
        return findings


def digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def plan(data_dir: Path = DYNAMIC_DIR, planner: Any | None = None, question: str = CODE_QUESTION) -> str:
    """One LLM call. No log files are read/sent while generating code."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("program.txt", "program_meta.json", "findings.json", "payload_to_llm.json", "answer.json", "audit.json", "metrics.json"):
        (data_dir / filename).unlink(missing_ok=True)
    save_json(data_dir / "codegen_payload.json", {"system": CODE_SYSTEM, "user": question})
    if planner is None:
        planner = OpenAIPlanner()
    raw = planner._ask_text(CODE_SYSTEM, question)
    source = strip_code_fence(raw)
    try:
        validate_program(source)
    except ProgramRejected as exc:
        (data_dir / "rejected_program.txt").write_text(source, encoding="utf-8")
        raise ProgramRejected(f"LLM program rejected: {exc}. See b2_dynamic_data/rejected_program.txt") from exc
    (data_dir / "rejected_program.txt").unlink(missing_ok=True)
    (data_dir / "program.txt").write_text(source + "\n", encoding="utf-8")
    save_json(data_dir / "program_meta.json", {
        "source": "llm_generated_program",
        "model": getattr(planner, "model", "test_double"),
        "sha256": digest(source),
        "question": question,
    })
    print("LLM generated Python-subset program; AST allowlist: ACCEPTED")
    print("Saved: b2_dynamic_data/program.txt (NEVER execute it with `python program.txt`)")
    print("Program SHA-256:", digest(source))
    return source


def execute(data_dir: Path = DYNAMIC_DIR, log_dir: Path = LOG_DIR,
            b2_data_dir: Path = FIXED_DATA_DIR) -> dict[str, Any]:
    """Parse + interpret approved program. Logs stay local; no LLM call here."""
    program_path = data_dir / "program.txt"
    meta = load_json(data_dir / "program_meta.json")
    source = program_path.read_text(encoding="utf-8").strip()
    if meta["sha256"] != digest(source):
        raise ProgramRejected("Generated program was modified since validation; rerun plan")
    tools = BoundedLogTools(log_dir)
    findings = RestrictedRuntime(tools).run(source)
    user_text = build_model_prompt(meta["question"], findings)
    payload = {"system": ANSWER_SYSTEM, "user": user_text}
    if RAW_MARKER in json.dumps(payload) or "diagnostic=synthetic_data" in json.dumps(payload):
        raise ProgramRejected("Raw logs leaked into payload")
    # Estimate raw baseline locally; no provider request contains raw content.
    baseline = estimate_tokens(ANSWER_SYSTEM + "\n" + meta["question"])
    for path in tools.list_files("*.log"):
        baseline += estimate_tokens(path.read_text(encoding="utf-8"))
    generation_tokens = estimate_tokens(CODE_SYSTEM + "\n" + meta["question"])
    answer_tokens = estimate_tokens(ANSWER_SYSTEM + "\n" + user_text)
    metrics = {
        "files_read_locally": tools.files_read,
        "lines_processed_locally": tools.lines_read,
        "bytes_read_locally": tools.bytes_read,
        "naive_raw_context_estimated_tokens": baseline,
        "codegen_input_estimated_tokens": generation_tokens,
        "answer_input_estimated_tokens": answer_tokens,
        "two_request_input_estimated_tokens": generation_tokens + answer_tokens,
        "estimated_input_reduction_percent": round(100 * (1 - (generation_tokens + answer_tokens) / baseline), 2),
        "token_measurement": "local estimate only; excludes outputs and request wrappers",
        "program_sha256": digest(source),
        "raw_logs_sent_to_llm": False,
    }
    save_json(data_dir / "findings.json", findings)
    save_json(data_dir / "payload_to_llm.json", payload)
    save_json(data_dir / "metrics.json", metrics)
    save_json(data_dir / "audit.json", {
        "runtime": "restricted_AST_interpreter_no_exec_eval",
        "allowed_tools": ["list_files", "read_file", "extract_error_code", "counter_add", "make_findings"],
        "program_sha256": digest(source),
        "files_read": tools.files_read,
        "raw_logs_in_model_input": False,
    })
    (data_dir / "answer.json").unlink(missing_ok=True)
    print(f"Runtime interpreted LLM program; read {tools.files_read} files / {tools.lines_read} lines LOCALLY")
    print(f"Raw-log input estimate: {baseline} tokens")
    print(f"Two LLM request input estimate: {generation_tokens + answer_tokens} tokens")
    print(f"Estimated input reduction: {metrics['estimated_input_reduction_percent']:.2f}%")
    print("Structured findings saved; raw log lines were not sent to the model")
    return findings


def ask(data_dir: Path = DYNAMIC_DIR, planner: Any | None = None) -> str:
    payload = load_json(data_dir / "payload_to_llm.json")
    if RAW_MARKER in json.dumps(payload) or "diagnostic=synthetic_data" in json.dumps(payload):
        raise ProgramRejected("Refusing to transmit raw log text")
    if planner is None:
        planner = OpenAIPlanner()
    reply = planner._ask_text(payload["system"], payload["user"])
    save_json(data_dir / "answer.json", {"response": reply, "via": "9router_or_test_planner"})
    print("\n9Router Agent answer (structured findings ONLY):\n")
    print(reply)
    return reply


def verify(data_dir: Path = DYNAMIC_DIR, log_dir: Path = LOG_DIR) -> bool:
    required = ["program.txt", "program_meta.json", "codegen_payload.json", "findings.json",
                "payload_to_llm.json", "metrics.json", "answer.json", "audit.json"]
    missing = [name for name in required if not (data_dir / name).exists()]
    if missing:
        print("B2 DYNAMIC RESULT: FAIL - missing:", ", ".join(missing))
        return False
    try:
        source = (data_dir / "program.txt").read_text(encoding="utf-8").strip()
        meta = load_json(data_dir / "program_meta.json")
        codegen = load_json(data_dir / "codegen_payload.json")
        findings = load_json(data_dir / "findings.json")
        payload = load_json(data_dir / "payload_to_llm.json")
        metrics = load_json(data_dir / "metrics.json")
        answer_data = load_json(data_dir / "answer.json")
        audit = load_json(data_dir / "audit.json")
        validate_program(source)
        expected = trusted_reference(LocalLogTools(log_dir))
        by_code = {x["code"]: x["count"] for x in findings["error_counts"]}
        expected_codes = {x["code"]: x["count"] for x in expected["error_counts"]}
        top = expected["error_counts"][0]["code"]
        answer_text = answer_data.get("response", "")
        checks = {
            "LLM-generated program validated by restricted AST": meta["source"] == "llm_generated_program" and meta["sha256"] == digest(source),
            "runtime processed at least 50 files": metrics["files_read_locally"] >= 50,
            "runtime counts match trusted offline reference": by_code == expected_codes,
            "raw marker absent from both model inputs": RAW_MARKER not in json.dumps(payload) and RAW_MARKER not in json.dumps(codegen),
            "raw diagnostic absent from both model inputs": "diagnostic=synthetic_data" not in json.dumps(payload) and "diagnostic=synthetic_data" not in json.dumps(codegen),
            "runtime did not exec/eval code": audit["runtime"] == "restricted_AST_interpreter_no_exec_eval",
            "two-request estimated input reduction >= 80%": metrics["estimated_input_reduction_percent"] >= 80,
            "answer obtained and includes top error": bool(answer_text.strip()) and top in answer_text,
        }
    except (ValueError, TypeError, KeyError, OSError, ProgramRejected, IndexError) as exc:
        print("B2 DYNAMIC RESULT: FAIL -", type(exc).__name__, exc)
        return False
    for label, okay in checks.items():
        print(("PASS" if okay else "FAIL") + " - " + label)
    success = all(checks.values())
    print("B2 DYNAMIC RESULT:", "PASS" if success else "FAIL")
    return success


def main() -> None:
    parser = argparse.ArgumentParser(description="B2 dynamic Code Mode through local 9Router")
    parser.add_argument("command", choices=["plan", "execute", "ask", "verify", "all"])
    args = parser.parse_args()
    if args.command in {"plan", "all"}:
        plan()
    if args.command in {"execute", "all"}:
        execute()
    if args.command in {"ask", "all"}:
        ask()
    if args.command in {"verify", "all"} and not verify():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
