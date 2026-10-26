"""Challenge B1 - contextual compaction demo; only Python agent/harness, no web app."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlparse


from dotenv import load_dotenv
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
load_dotenv(ROOT / ".env")

# This example uses token estimates for LOCAL thresholding, not API billing tokens.
try:
    import tiktoken
    ENCODING = tiktoken.get_encoding("o200k_base")
except ImportError:
    ENCODING = None

SYSTEM_RULES = (
    "You are a troubleshooting agent in a SIMULATED investigation. "
    "Preserve current goal, constraints, findings, failed fixes, and the next action. "
    "Do not claim a root cause is confirmed if it has not been tested."
)


class Checkpoint(BaseModel):
    goal: str
    current_state: str
    constraints: list[str]
    findings: list[str]
    failed_attempts: list[str]
    files: list[str]
    next_action: str


class ResumeDecision(BaseModel):
    active_issue: str
    failed_attempts: list[str]
    action: Literal["inspect_locking", "increase_ttl", "rerun_tests"]
    reason: str


class Planner(Protocol):
    def compact(self, transcript: list[dict[str, str]]) -> Checkpoint: ...
    def resume(self, active_context: list[dict[str, str]]) -> ResumeDecision: ...


class OpenAIPlanner:
    """A provider-agnostic LLM planner via an OpenAI-compatible API (9Router).

    JSON shape is requested in the prompt and validated with Pydantic locally.
    This deliberately avoids relying on gateway-specific Structured Outputs support.
    """

    def __init__(self) -> None:
        from openai import OpenAI

        self.base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:20128/v1").strip()
        self.model = os.getenv("OPENAI_MODEL", "cx/gpt-6.1-sol").strip()
        self.api_mode = os.getenv("LLM_API_MODE", "chat").strip().lower()
        if self.api_mode not in ("chat", "responses"):
            raise ValueError("LLM_API_MODE must be 'chat' or 'responses'.")

        key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            # An empty key is supported only for local development when the
            # gateway is configured to allow unauthenticated requests.
            if urlparse(self.base_url).hostname not in ("localhost", "127.0.0.1", "::1"):
                raise RuntimeError("OPENAI_API_KEY must be set for a non-local router.")
            key = "local-9router"  # SDK placeholder; 9Router may require a real key.

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=key,
            timeout=120.0,
            max_retries=1,
        )

    def _ask_text(self, instructions: str, user_text: str) -> str:
        """Send one LLM request using the API format selected in .env."""
        try:
            return self._send_text(instructions, user_text)
        except Exception as exc:
            raise RuntimeError(
                f"9Router request failed (mode={self.api_mode}, model={self.model}): "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def _send_text(self, instructions: str, user_text: str) -> str:
        if self.api_mode == "chat":
            reply = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user_text},
                ],
                stream=False,
            )
            content = reply.choices[0].message.content if reply.choices else None
        else:
            reply = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=[{"role": "user", "content": user_text}],
            )
            content = reply.output_text
        if not content or not content.strip():
            raise RuntimeError(
                "LLM returned empty text. Check the 9Router logs/model compatibility "
                "or try LLM_API_MODE=responses (or chat) in .env."
            )
        return content.strip()

    def _ask_json(self, instructions: str, payload: object, schema: type[BaseModel]) -> BaseModel:
        """Ask for JSON, then *validate* it; do not assume the gateway enforces a schema."""
        schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        prompt = (
            instructions
            + "\nReturn exactly ONE valid JSON object conforming to this JSON Schema: "
            + schema_text
            + "\nNo Markdown fences, explanations, or text outside the JSON object."
        )
        content = self._ask_text(prompt, json.dumps(payload, ensure_ascii=False))
        # Be tolerant of a provider that wraps an otherwise valid JSON object.
        if content.startswith("```"):
            lines = content.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                content = "\n".join(lines[1:-1]).strip()
        try:
            return schema.model_validate_json(content)
        except ValueError as exc:
            raise RuntimeError(
                f"LLM did not return valid {schema.__name__} JSON. "
                f"First 250 characters: {content[:250]!r}"
            ) from exc

    def ping(self) -> None:
        """An actual inference call, not merely an HTTP health check."""
        answer = self._ask_text(
            "Reply with exactly OK, no extra text.",
            "Connection test: respond OK.",
        )
        print(f"9Router LLM connected. model={self.model}, mode={self.api_mode}")
        print("Model reply:", answer[:200])

    def compact(self, transcript: list[dict[str, str]]) -> Checkpoint:
        checkpoint = self._ask_json(
            (
                "Create a structured recovery checkpoint from the transcript. "
                "Keep only facts needed to continue the debugging task. "
                "Retain the exact goal, API-compatibility constraint, observed error, "
                "TTL fix that failed, relevant file paths and next planned action. "
                "Ignore repeated diagnostic INFO logs. Never invent missing facts. "
                "Write in English to match the technical transcript."
            ),
            transcript,
            Checkpoint,
        )
        assert isinstance(checkpoint, Checkpoint)
        return checkpoint

    def resume(self, active_context: list[dict[str, str]]) -> ResumeDecision:
        decision = self._ask_json(
            (
                "You are resuming the troubleshooting agent from a checkpoint. "
                "Report the active issue, failed attempts and choose the best next action. "
                "Do not repeat an already disproven fix. Do not invent test results."
            ),
            active_context,
            ResumeDecision,
        )
        assert isinstance(decision, ResumeDecision)
        return decision


def count_tokens(payload: object) -> int:
    text = json.dumps(payload, ensure_ascii=False)
    if ENCODING is not None:
        return len(ENCODING.encode(text))
    return max(1, len(text) // 4)  # Local fallback; approximate, not API usage.


def generate_history(log_lines: int = 350) -> list[dict[str, str]]:
    """Synthetic tool outputs, intentionally verbose; no authentication app exists."""
    logs = [
        "RUN_TESTS: FAIL test_concurrent_refresh; FAIL test_parallel_rotation; ",
        "OBSERVED: two concurrent refresh calls can reuse the same refresh token.",
        "TRACE: refresh flow reads and updates token state; synchronization unverified.",
    ]
    for i in range(log_lines):
        logs.append(
            f"2026-10-26T10:00:{i % 60:02d}Z INFO worker={i % 8} "
            f"request_id=req_{i:05d} refresh telemetry batch={i // 10} "
            "status=retry trace=diagnostic_only"
        )

    return [
        {"role": "system", "content": SYSTEM_RULES},
        {"role": "user", "content": (
            "Goal: Fix refresh-token race condition. "
            "Constraint: keep API backward compatible. "
            "Relevant files: auth.ts, session.ts, auth.test.ts."
        )},
        {"role": "assistant", "content": "I will run simulated tests first."},
        {"role": "user", "content": "[SIMULATED TOOL run_tests]\n" + "\n".join(logs)},
        {"role": "assistant", "content": (
            "Observation: concurrent refresh is failing. "
            "Attempt #1: increase refresh token TTL to avoid expiry collisions."
        )},
        {"role": "user", "content": (
            "[SIMULATED TOOL try_fix(increase_ttl)]\n"
            "RESULT: FAIL. test_concurrent_refresh and test_parallel_rotation still fail. "
            "Increasing token TTL did not help."
        )},
        {"role": "assistant", "content": (
            "Do not repeat the TTL experiment. Locking around refresh has not yet "
            "been inspected. Next action: inspect locking around refresh before changing code."
        )},
    ]


def save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_checkpoint(cp: Checkpoint) -> None:
    """Fail closed if task-critical facts were lost during summarization."""
    facts = " ".join([cp.goal, cp.current_state, *cp.findings]).lower()
    failures = " ".join(cp.failed_attempts).lower()
    requirements = " ".join(cp.constraints).lower()
    next_step = cp.next_action.lower()
    missing = []
    if "refresh" not in facts or "concurrent" not in facts and "race" not in facts:
        missing.append("refresh race condition")
    if "api" not in requirements or "compatib" not in requirements:
        missing.append("API compatibility constraint")
    if "ttl" not in failures or not any(word in failures for word in ["fail", "not help", "unsuccess"]):
        missing.append("failed TTL attempt")
    if "lock" not in next_step:
        missing.append("inspect locking next action")
    if missing:
        raise ValueError("Unsafe checkpoint, missing: " + ", ".join(missing))


def do_run(planner: Planner, data_dir: Path, threshold: int, log_lines: int) -> tuple[int, int]:
    history = generate_history(log_lines)
    before = count_tokens(history)
    print(f"[1/4] Approx. active tokens BEFORE: {before}")
    if before < threshold:
        raise ValueError(
            f"History has {before} estimated tokens, below threshold={threshold}. "
            "Use --log-lines 350 or lower COMPACT_THRESHOLD_TOKENS."
        )
    print(f"[2/4] Threshold reached ({threshold}): compacting with LLM...")
    checkpoint = planner.compact(history)
    validate_checkpoint(checkpoint)  # Never discard the old context if this fails.

    active_context = [
        {"role": "system", "content": SYSTEM_RULES},
        {"role": "user", "content": (
            "SESSION RESUMED. Work ONLY from this checkpoint; the original logs "
            "are archived and not available in the active context:\n"
            + checkpoint.model_dump_json(indent=2)
        )},
    ]
    after = count_tokens(active_context)
    if after >= before:
        raise ValueError("Compaction was ineffective: active context did not shrink.")

    # Save the archive separately. It is NOT passed to the resumed LLM call.
    save_json(data_dir / "archive_history.json", history)
    save_json(data_dir / "checkpoint.json", checkpoint.model_dump())
    save_json(data_dir / "active_context.json", active_context)
    save_json(data_dir / "metrics.json", {
        "estimated_tokens_before": before,
        "estimated_tokens_after": after,
        "reduction_percent": round(100 * (1 - after / before), 2),
        "threshold_tokens": threshold,
        "token_measurement": "tiktoken estimate" if ENCODING else "characters/4 fallback",
    })
    (data_dir / "resume_result.json").unlink(missing_ok=True)
    print(f"[3/4] Approx. active tokens AFTER:  {after}")
    print(f"[4/4] Reduced by {100 * (1 - after / before):.1f}%")
    print("Files written: data/archive_history.json, data/checkpoint.json, "
          "data/active_context.json, data/metrics.json")
    return before, after


def do_resume(planner: Planner, data_dir: Path) -> ResumeDecision:
    active_path = data_dir / "active_context.json"
    if not active_path.exists():
        raise FileNotFoundError("Run `python main.py run` first.")
    context = load_json(active_path)
    print("Loading ONLY active_context.json (not archive_history.json)...")
    decision = planner.resume(context)
    save_json(data_dir / "resume_result.json", decision.model_dump())
    print("Active issue:", decision.active_issue)
    print("Failed attempts:", "; ".join(decision.failed_attempts))
    print("Next action:", decision.action)
    print("Reason:", decision.reason)
    if decision.action == "inspect_locking":
        print("[SIMULATED TOOL inspect_locking] Lock inspection queued. "
              "No backend is modified in this exercise.")
    else:
        print("[WARNING] Agent did not select the expected next investigation step.")
    return decision


def do_verify(data_dir: Path) -> bool:
    files = ["checkpoint.json", "metrics.json", "active_context.json", "resume_result.json"]
    missing = [f for f in files if not (data_dir / f).exists()]
    if missing:
        print("FAIL: Missing files:", ", ".join(missing))
        return False
    cp = Checkpoint.model_validate(load_json(data_dir / "checkpoint.json"))
    decision = ResumeDecision.model_validate(load_json(data_dir / "resume_result.json"))
    metrics = load_json(data_dir / "metrics.json")
    checks = {
        "goal/constraints/failed attempts/next action preserved": True,
        "active context reduced >= 50%": metrics["reduction_percent"] >= 50,
        "agent chose inspect_locking": decision.action == "inspect_locking",
        "agent remembers failed TTL attempt": any(
            "ttl" in attempt.lower() for attempt in decision.failed_attempts
        ),
    }
    try:
        validate_checkpoint(cp)
    except ValueError:
        checks["goal/constraints/failed attempts/next action preserved"] = False
    for name, passed in checks.items():
        print(("PASS" if passed else "FAIL") + " - " + name)
    success = all(checks.values())
    print("B1 RESULT:", "PASS" if success else "FAIL")
    return success


def main() -> None:
    parser = argparse.ArgumentParser(description="Challenge B1: structured context compaction")
    parser.add_argument("command", choices=["run", "resume", "verify", "preview", "ping"])
    parser.add_argument("--log-lines", type=int, default=350)
    parser.add_argument(
        "--threshold", type=int,
        default=int(os.getenv("COMPACT_THRESHOLD_TOKENS", "2500")),
    )
    args = parser.parse_args()
    try:
        if args.command == "ping":
            OpenAIPlanner().ping()
        elif args.command == "preview":
            history = generate_history(args.log_lines)
            print("Approx. input tokens:", count_tokens(history))
            print("Threshold:", args.threshold)
            print("Compaction would trigger:", count_tokens(history) >= args.threshold)
        elif args.command == "run":
            do_run(OpenAIPlanner(), DATA_DIR, args.threshold, args.log_lines)
        elif args.command == "resume":
            do_resume(OpenAIPlanner(), DATA_DIR)
        elif args.command == "verify":
            if not do_verify(DATA_DIR):
                raise SystemExit(1)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print("ERROR:", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
