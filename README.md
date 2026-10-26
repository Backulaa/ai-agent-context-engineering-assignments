# Challenge B1 - Structured Context Compaction (Python only)

Scope: AI agent and harness only, without frontend, backend, Docker or database.

Based on slides 20-26 and 32-33 of *Memory, Context Engineering & Prompt Caching*.

## Setup on Windows / VS Code (PowerShell)

```powershell
mkdir challenge-b1-compaction
# If you already extracted the archive, skip creating a new folder.
cd challenge-b1-compaction
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and replace `YOUR_API_KEY_HERE` with a valid OpenAI API key. API usage is billed separately from ChatGPT subscriptions.

## Execution

```powershell
python -m unittest discover -s tests -v
python main.py preview
python main.py run
python main.py resume
python main.py verify
```

`preview` and unit tests are offline. `run` uses the LLM to generate the checkpoint, and `resume` uses the LLM to choose the next action.

## Outcomes

- `data/archive_history.json`: original long history, NOT sent to the LLM during resume.
- `data/checkpoint.json`: structured checkpoint.
- `data/active_context.json`: tiny input used by the resumed agent.
- `data/metrics.json`: token estimates before and after.
- `data/resume_result.json`: next step selected by LLM.

The threshold is deliberately tiny to make the demonstration observable. It is NOT the model's maximum context window. The local token count is an estimate and may differ from API usage.

## Safety / interpretation

This project demonstrates harness-level compaction: LLM creates an explicit checkpoint, then only that checkpoint enters the resumed model. It is not the provider-native `/responses/compact` endpoint. The logs and tools are fake, and no application, auth server or production code is modified. In a production system, sensitive logs must be redacted, checkpoint fields validated, tool permissions restricted and cost/latency monitored.
