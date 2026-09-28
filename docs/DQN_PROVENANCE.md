# DQN Checkpoint Provenance Investigation

Read-only investigation. No files were modified, no models retrained, no reward functions or simulator code changed, no benchmark results altered, no checkpoints renamed or deleted, no Gemini/API calls made, no git actions taken.

**Method:** for each `.pth` file, (1) recorded on-disk size/mtime, (2) grepped the entire repo (excluding `node_modules`, `.git`) for every reference to its filename, (3) loaded its raw `state_dict` with `torch.load(..., weights_only=True)` to read tensor shapes directly (this is a passive deserialization — no training step, no gradient computation, no file write), and (4) attempted (but did not persist) loading each state_dict into the current `DQN(42, 26)` class from `dqn_agent.py` to test architectural compatibility. This produced hard, reproducible evidence rather than filename-based inference.

---

## Per-checkpoint findings

### `ev_dqn_model.pth` ("v1", implicit — never explicitly numbered in the repo)

1. **Exists:** yes.
2. **Size/mtime:** 26,705 bytes; mtime 2026-02-07 18:15 (on-disk filesystem timestamp). This date is *earlier* than every other checkpoint's mtime despite the file logically being the oldest/simplest architecture — filesystem mtimes on Windows can be altered by copies/restores and are not reliable creation-order evidence. Treat this timestamp as **unreliable**, consistent with the original audit's note.
3. **Referenced:** only in `.gitignore:4` (explicitly excluded from version control) and in the audit/status docs written during this project. **No executable script references this filename.**
4. **Producing/consuming script:** none found in the current repo.
5. **State-vector dimensionality (measured directly from the checkpoint tensor shapes):** `network.0.weight` shape `(64, 20)` → **20-dimensional observation space.**
6. **Action-space dimensionality:** `network.4.weight` shape `(6, 64)` → **6 discrete actions.**
7. **Reward formulation:** **UNKNOWN** — no environment code in the current repo produces a 20-dim/6-action space (the only `ev_gym_env.py` present defines 42-dim/26-action). The training environment that produced this checkpoint no longer exists in the repository.
8. **Simulator implementation used:** **UNKNOWN** — cannot be identified; may predate `simple_ev_simulation.py`'s current interface entirely.
9. **Training configuration/hyperparameters:** **UNKNOWN** — not recoverable, no git history, no training log references this file.
10. **Benchmark results still referencing it:** **Circumstantial only.** `archive/dqn_comparison_results.json` (mtime 2026-08-30 21:35, the *earliest* of all DQN-related artifacts) contains a `DQN` policy row and is the only DQN benchmark file self-described in `README.md` as retired due to an `avg_satisfaction=0.0` bug (confirmed present in the raw data: every sampled `FIFO` run in that file has `avg_satisfaction: 0.0`). Since this archived file's timestamp predates the creation of `_v2`/`_v3`/`_v4`/`_v5`, `ev_dqn_model.pth` is the only checkpoint that could have existed when it was generated — but no field in the JSON records which checkpoint file was loaded, so this link is **inferred from timeline ordering, not proven**.
11. **Loads into current `DQN(42,26)` architecture:** **NO** — confirmed by direct test: `size mismatch for network.0.weight: [64,20] vs [64,42]`, `network.4.weight: [6,64] vs [26,64]`.
12. **Confident association with a specific experiment phase:** No. Best-supported hypothesis (not proof) is that it underlies the retired `archive/dqn_comparison_results.json` run.

**Classification: ORPHANED.**

---

### `ev_dqn_model_v2.pth`

1. **Exists:** yes.
2. **Size/mtime:** 28,021 bytes; mtime 2026-08-30 21:44.
3. **Referenced:** no source file references this filename by name anywhere in the repo (the only textual hit is a compiled `.pyc` binary artifact, which is not a genuine reference).
4. **Producing/consuming script:** none found.
5. **State-vector dimensionality (measured):** `network.0.weight` shape `(64, 25)` → **25-dimensional observation space.**
6. **Action-space dimensionality (measured):** `network.4.weight` shape `(6, 64)` → **6 discrete actions.**
7. **Reward formulation:** **UNKNOWN** — no 25-dim/6-action environment definition exists anywhere in the current repo.
8. **Simulator implementation used:** **UNKNOWN.**
9. **Training configuration:** **UNKNOWN.**
10. **Benchmark results referencing it:** none found.
11. **Loads into current `DQN(42,26)` architecture:** **NO** — confirmed: `[64,25]` vs `[64,42]`, `[6,64]` vs `[26,64]`.
12. **Confident phase association:** No.

**Classification: ORPHANED.**

---

### `ev_dqn_model_v3.pth`

1. **Exists:** yes.
2. **Size/mtime:** 28,021 bytes (byte-identical file size to v2); mtime 2026-08-30 21:58 (14 minutes after v2).
3. **Referenced:** none, anywhere.
4. **Producing/consuming script:** none found.
5. **State-vector dimensionality (measured):** `(64, 25)` → same 25-dim observation space as v2.
6. **Action-space dimensionality (measured):** `(6, 64)` → same 6-action space as v2.
7. **Reward formulation:** **UNKNOWN**, same reasoning as v2.
8. **Simulator implementation used:** **UNKNOWN.**
9. **Training configuration:** **UNKNOWN.** (Identical architecture and file size to v2 suggests this is very plausibly a second training run — perhaps continued/re-run training — against the *same*, now-lost 25-dim/6-action environment definition, rather than an architecture change. This is a reasonable inference from the measured shapes, not a filename-based assumption.)
10. **Benchmark results referencing it:** none found.
11. **Loads into current `DQN(42,26)` architecture:** **NO** — identical mismatch pattern to v2.
12. **Confident phase association:** No.

**Classification: ORPHANED.**

---

### `ev_dqn_model_v4.pth`

1. **Exists:** yes.
2. **Size/mtime:** 37,557 bytes (byte-identical size to v5); mtime 2026-08-30 22:17 (17 minutes before v5).
3. **Referenced:** **YES — genuine, active reference found:** `controlled_scenarios.py:22`, `def load_dqn(sim, model_path="ev_dqn_model_v4.pth")`. This is a real, executable default parameter in a standalone script, not documentation.
4. **Producing/consuming script:** *Consumed* by `controlled_scenarios.py` (a standalone manual-scenario demo script — not part of `pytest`, not imported by `experiment_comparison.py`, `app.py`, or any other active pipeline; it has its own `if __name__ == "__main__"` block and is only run directly by a developer). No script in the current repo is confirmed to have *produced* this specific file (see point 9).
5. **State-vector dimensionality (measured):** `network.0.weight` shape `(64, 42)` → **42-dimensional observation space — matches the current `ev_gym_env.py` exactly.**
6. **Action-space dimensionality (measured):** `network.4.weight` shape `(26, 64)` → **26 discrete actions — matches the current `ev_gym_env.py` exactly.**
7. **Reward formulation:** Because the architecture matches the *current* `ev_gym_env.py` (42-dim/26-action, including the value-hoarding-fix reward shaping at `ev_gym_env.py:56-95`), this checkpoint is plausibly a product of the same reward design as v5 — but this cannot be proven, since no training script or log is tied specifically to "v4" by name; `dqn_agent.py`'s training loop (`dqn_agent.py:153,155`) hardcodes its save filename as `"ev_dqn_model_v5.pth"` only, never `"_v4"`. The most defensible explanation is that an earlier copy of `dqn_agent.py` (since overwritten, no history preserved) saved to `_v4.pth`, and was later edited to save to `_v5.pth` for a subsequent run — but this is inferred, not documented anywhere.
8. **Simulator implementation used:** Consistent with the *current* `simple_ev_simulation.py` + `ev_gym_env.py` pair (dimension match confirms this), unlike v1–v3.
9. **Training configuration/hyperparameters:** **UNKNOWN in detail** (no `_v4`-specific script/log exists), but the weights are numerically **distinct** from v5 (directly measured: max absolute weight difference of 4.12 on the hidden layer, confirming this is a genuinely different trained checkpoint, not a duplicate or copy of v5).
10. **Benchmark results referencing it:** none found — `phase5_results.json`'s DQN row is generated via `experiment_comparison.py`, which imports `DQNAgent` from `dqn_agent.py` but (per the original Phase 1 audit) has no explicit filename-loading call visible in the reviewed portion of that script tying it to any specific checkpoint by name; only `simple_ev_simulation.py:213` hardcodes a load, and that loads v5, not v4.
11. **Loads into current `DQN(42,26)` architecture:** **YES — confirmed, loads without error.**
12. **Confident phase association:** **Partial.** It is confidently tied to the *current* environment/architecture generation (same as v5) via direct shape verification, and to `controlled_scenarios.py` via direct file reference — but not to a specific dated experiment phase or a specific benchmark JSON.

**Classification: PARTIALLY VERIFIED** (architecturally current and has one genuine, active code reference — not orphaned in the strict sense — but its training provenance and its relationship to v5, e.g. "earlier checkpoint of the same run" vs. "separate run," is not documented anywhere and had to be reconstructed from timestamps and weight comparison).

---

### `ev_dqn_model_v5.pth` (the checkpoint the audit already identified as canonical)

1. **Exists:** yes.
2. **Size/mtime:** 37,557 bytes; mtime 2026-08-30 22:34 (latest of all five checkpoints).
3. **Referenced:** `dqn_agent.py:153` and `:155` (training loop save target), `simple_ev_simulation.py:213` (`self.dqn_agent.model.load_state_dict(torch.load("ev_dqn_model_v5.pth", ...))`).
4. **Producing script:** `dqn_agent.py`'s `__main__` training loop (`dqn_agent.py:113-156`), confirmed by the exact matching save-filename string.
5. **State-vector dimensionality (measured):** `(64, 42)` → **42-dim, matches `ev_gym_env.py`'s `observation_space = spaces.Box(..., shape=(42,))` (`ev_gym_env.py:27-29`) exactly.**
6. **Action-space dimensionality (measured):** `(26, 64)` → **26 actions, matches `ev_gym_env.py`'s `action_space = spaces.Discrete(1 + 5*5)` (`ev_gym_env.py:23`) exactly.**
7. **Reward formulation:** `ev_gym_env.py:56-95` — charging-reward-per-active-EV, queue-hoarding penalty, port-speed-match bonus/penalty; explicit comment at `ev_gym_env.py:89-90` documents "Remove base assignment reward to fix value-hoarding exploit," matching the README's and Phase 1 audit's account of the value-hoarding problem.
8. **Simulator implementation used:** `simple_ev_simulation.py` (current version) via `ev_gym_env.py`'s `EVChargingEnv` wrapper — confirmed by direct import chain.
9. **Training configuration:** `gamma=0.95`, `epsilon` 1.0→0.05 decay 0.9995, `lr=0.001`, `batch_size=32`, 100 episodes, target-network sync each episode (`dqn_agent.py:31-36, 120-148`) — these are read directly from the current `dqn_agent.py`, which is the same file whose `__main__` block produces this exact filename, so this is a **direct, not inferred**, hyperparameter record.
10. **Benchmark results referencing it:** `phase5_results.json`'s `DQN` policy row is produced by `experiment_comparison.py` (imports `DQNAgent`); since `simple_ev_simulation.py:213` is the only active load path for any DQN checkpoint and it hardcodes v5, this is the best-supported link in the whole investigation, though — as the original audit already noted — no explicit run manifest inside `phase5_results.json` itself names the checkpoint file.
11. **Loads into current `DQN(42,26)` architecture:** **YES — confirmed, loads without error** (re-verified in this investigation, not just assumed from the earlier audit).
12. **Confident phase association:** **Yes** — this is the only checkpoint with a direct, verifiable line from training script → saved file → loader code → current environment dimensions, all matching exactly.

**Classification: VERIFIED** (re-confirmed; the Phase 1 audit's conclusion holds).

---

## A. Provenance Table

| Checkpoint | Size | State/Action dims (measured) | Loads into current `DQN(42,26)`? | Referenced by active code? | Reward/training config recoverable? | Classification |
|---|---|---|---|---|---|---|
| `ev_dqn_model.pth` | 26,705 B | 20 / 6 | No | No | No | **ORPHANED** |
| `ev_dqn_model_v2.pth` | 28,021 B | 25 / 6 | No | No | No | **ORPHANED** |
| `ev_dqn_model_v3.pth` | 28,021 B | 25 / 6 | No | No | No | **ORPHANED** |
| `ev_dqn_model_v4.pth` | 37,557 B | 42 / 26 | **Yes** | **Yes** — `controlled_scenarios.py:22` (standalone script) | Partial — architecture/env inferred current, exact hyperparameters not logged | **PARTIALLY VERIFIED** |
| `ev_dqn_model_v5.pth` | 37,557 B | 42 / 26 | **Yes** | **Yes** — `dqn_agent.py` (produces), `simple_ev_simulation.py:213` (consumes, canonical interactive/benchmark path) | Yes — direct from current `dqn_agent.py` | **VERIFIED** |

---

## B. Checkpoints currently safe to retain

All five. Retaining is safe regardless of classification — none are large (26–38 KB each), none pose a security risk, and "orphaned" here means *undocumented*, not *broken* or *dangerous*. No deletions were made or are being recommended in this investigation.

## C. Checkpoints referenced by active code

- **`ev_dqn_model_v5.pth`** — the only checkpoint loaded by the interactive simulation path (`simple_ev_simulation.py:213`), which is what feeds the "DQN" row in benchmark experiments run through `experiment_comparison.py`.
- **`ev_dqn_model_v4.pth`** — referenced only by `controlled_scenarios.py`, a standalone, manually-run demo script that is not part of the automated test suite, not imported by `app.py`, and not part of the benchmark pipeline. "Active" in the sense that the code path exists and would run if invoked directly, but it is not part of the product or the benchmark story.

## D. Historical/orphaned checkpoints

`ev_dqn_model.pth`, `ev_dqn_model_v2.pth`, `ev_dqn_model_v3.pth` — no current code references them, and their measured architectures (20/6 and 25/6 dims) do not match any environment definition present in the repository today. Their training code and environment definitions have been lost (no git history exists to recover them). They represent genuine earlier iterations of the project, not mistakes — the dimension progression (20/6 → 25/6 → 42/26) is consistent with an environment that was incrementally expanded over the project's history (more visible queue slots, more port telemetry, larger action space), which is a normal and defensible research trajectory, not evidence of a broken pipeline.

## E. Should any checkpoint be mentioned in the final README?

Yes — **`ev_dqn_model_v5.pth` only**, as the checkpoint actually used for the "DQN" comparisons shown in the benchmark tables and referenced from the interactive app. It should be described exactly as the existing README already does: an experimental baseline with a documented value-hoarding failure mode, using the current 42-state/26-action environment. `_v4.pth` does not need README mention (it only backs a standalone dev-utility script). `ev_dqn_model.pth`, `_v2`, `_v3` should **not** be mentioned as if they were part of the current, working system — if the README or resume materials want to acknowledge iteration history, a single sentence such as "earlier DQN environment formulations (smaller observation/action spaces) were superseded during development; only the current 42-dim/26-action version, `ev_dqn_model_v5.pth`, is evaluated in the results below" would be accurate and would not overstate or understate the project's history.

## F. Is the DQN section technically defensible as currently documented?

**Yes, for what it currently claims.** The README already frames DQN narrowly and honestly: "experimental baseline only," with a specific, code-supported failure mode (value-hoarding — directly corroborated by the reward-shaping comment in `ev_gym_env.py:89-90`). This investigation did not find anything that contradicts that framing. The one gap is that the README doesn't currently acknowledge that four other checkpoints exist on disk with no documented lineage — a technically rigorous reviewer who lists the directory would find `_v1` through `_v4` and could reasonably ask "which one produced these numbers, and what are the others?" This investigation answers that question in `docs/DQN_PROVENANCE.md` now existing; nothing further needs to change in the DQN experimental results themselves.

## G. Recommended next task

Add a brief, factual note to `README.md`'s existing "RL Findings" section (or the Project Structure listing) stating that `ev_dqn_model_v5.pth` is the sole checkpoint used in the reported results, and pointing to `docs/DQN_PROVENANCE.md` for the full checkpoint history — a small documentation addition, no code or benchmark changes, directly closes the gap identified in Section F above. This is a 5–10 minute, zero-risk doc task and does not require approval.

---

*Investigation complete. No files were modified, retrained, deleted, or renamed. All `torch.load` calls performed in this investigation were read-only deserializations into throwaway in-memory objects (via a scratch script outside the repository) and did not write to, move, or alter any checkpoint file.*
