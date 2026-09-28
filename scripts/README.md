# Diagnostic Scripts

Ad hoc, non-automated diagnostic utilities used during development. Not part of the pytest suite, not imported by the application, not run by CI. **Run from the repository root** (they use paths relative to the project root, e.g. `llm_fixtures.json`, `phase5_results.json`), for example:

```bash
python scripts/check_fixtures.py
python scripts/read_results.py
```

- `verify_api.py` — smoke-tests a running backend (`/api/reset`, `/api/station`, `/api/negotiate`, `/api/step`, `/api/benchmarks`) and spot-checks the LLM_NEGOTIATOR vs TELEMETRY_ONLY satisfaction gap in `phase5_results.json`. Requires the backend running locally on port 8000.
- `check_fixtures.py` — prints the `source` label (`gemini_live` / `synthetic_manual`) of every entry in `llm_fixtures.json` and a summary count. No server or API key needed.
- `read_results.py` — pretty-prints the LOW/MEDIUM/HIGH policy comparison table from `phase5_results.json`.
- `diff_results.py` — diffs `phase5_results.json` against a `phase5_final_results.json` file. **That second file does not currently exist in this repository** — this script is a template for comparing a future re-run against the current results and will raise `FileNotFoundError` until one is generated.
