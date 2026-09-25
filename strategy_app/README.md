# MiroShark Strategy

**Question → evidence → Outcome Contract → Jev validation/refinement → human approval → atomic analysis → verified decision memo.**

This is a self-contained companion in the MiroShark repository. It communicates with the existing authenticated MiroShark API; it does not replace the Flask/Vue app, alter the simulation engine, or change main's API contract. Runtime requirements: Python 3.11+; Python standard library only. The responsive frontend uses native ES modules with no frontend build step. The existing repository's AGPL license applies.

## Start

From the repository root:

```sh
cp strategy_app/.env.example .env.strategy
# Set STRATEGY_ACCESS_TOKEN to a separate random secret of at least 24 characters.
# Configure provider settings privately on your server, not in the browser or Git.
python -m strategy_app --env-file .env --env-file .env.strategy
```

Omit `--env-file .env` when that file does not exist. Environment variables already exported take precedence over files; repeated files are read in order without overwriting existing values. The configuration loader accepts literal KEY=value, optional matching quotes, and comments on their own lines. It does not evaluate shell commands or interpolate values.

Open `http://127.0.0.1:5100`, unlock with the workspace token, and use **Explore a synthetic example** to verify the complete UI, approval, persistence, report, review and export flow without provider charges. That fixed example never pretends to analyze an arbitrary question and is never used as a fallback for failed live calls.

For live analysis, supply:

| Purpose | Explicit setting | Existing MiroShark fallback |
|---|---|---|
| Planner and repair | `STRATEGY_FRONTIER_BASE_URL`, `STRATEGY_FRONTIER_API_KEY`, `STRATEGY_FRONTIER_MODEL` | `SMART_BASE_URL` / `SMART_API_KEY` / `SMART_MODEL_NAME`, then corresponding `LLM_*` settings |
| Atomic writing and synthesis | `STRATEGY_EXECUTOR_BASE_URL`, `STRATEGY_EXECUTOR_API_KEY`, `STRATEGY_EXECUTOR_MODEL` | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` |
| Typed validation | `TYPESAFE_API_KEY`, `JEV_MODEL=jev-1.13.0` | No chat-completion fallback |
| Existing simulation backend | `MIROSHARK_API_URL`, `MIROSHARK_INTERNAL_KEY` | Default URL `http://127.0.0.1:5001` |

The text providers must support `/chat/completions`, `response_format: {type: "json_object"}` and `max_tokens`. Model IDs are operator supplied, not invented defaults. This companion does not invoke MiroShark's Claude Code CLI adapter. Set explicit compatible HTTP model endpoints when your original backend uses that adapter.

Then set `STRATEGY_LIVE_ENABLED=true` and restart. Configuration presence is not a successful connection test. A live request reports authentication, API contract or provider failures without substituting a fake result.

## Use

1. Enter the question, what is known, constraints and optionally source extracts. TXT, Markdown and DOCX are supported; DOCX body paragraphs include table cells. Uploads are bounded to 1 MB, extracted text to 10,000 characters per source, eight sources and 40,000 source characters total. PDF/image OCR and arbitrary URL fetching are not included; paste a relevant extract instead. Sources are retained as user-supplied assertions, not independently verified facts.
2. Choose **Analysis only**, **Run a new simulation**, or **Use a completed simulation**. A new simulation requires explicit compute authorization. Its short question must be 8–400 characters to match MiroShark's `/ask` contract; longer detail belongs in context. Existing simulation mode is read-only and requires a completed run.
3. Inspect the generated Outcome Contract and atomic plan. Jev checks every critical dimension independently. Failed atoms return to the frontier planner for targeted repair. The fixed threshold is never lowered to get a pass. Default: three total planning versions, maximum four.
4. Approve the exact plan hash to execute. The generative worker completes each atomic task; Jev checks its output. Two local semantic retries and one frontier escalation are allowed before review. No model-generated shell, Python, SQL, network tools or business side effects are executed. The only registered code atom is an evidence inventory; additional numerical/business tools need explicit implementation and tests, not generated code execution.
5. Review the recommendation, alternatives including status quo, evidence gaps, assumptions, risks, decision triggers, next steps and all six SWOTMM sections. Noncommercial questions may mark monetization not applicable. Save your own review separately or revise the input to create another run.
6. Export Markdown or JSON. JSON includes source text and internal audit data; treat it as confidential. No reports are publicly published by this app.

## What the MiroShark integration actually does

New simulation mode follows the existing interfaces:

```text
POST /api/simulation/ask
POST /api/graph/ontology/generate       (url_docs form field with supplied text)
POST /api/graph/build
GET  /api/graph/task/{task_id}          (bounded polling)
POST /api/simulation/create            (Reddit only; prediction market disabled)
POST /api/simulation/prepare
GET  /api/simulation/{simulation_id}   (wait for ready)
POST /api/simulation/start             (1–30 rounds)
GET  /api/simulation/{id}/run-status   (wait for completed)
GET  /api/simulation/{id}/actions?limit=100&offset=0
```

Every request carries the server-side `x-miroshark-internal-key`. Graph and simulation IDs are persisted immediately after receipt, including late responses after local cancellation. Mutation requests are not automatically retried after an uncertain network outcome. A local cancellation stops subsequent analysis calls; it does **not** guarantee an already started remote graph/simulation was stopped. Inspect/stop that work in MiroShark using the saved IDs before resubmitting.

The simulation evidence is explicitly a sample: first 100 action records requested, with a 24,000-character text bound. Truncation and coverage are visible. It is not a complete census of agent behavior. A simulation is hypothetical exploration, not verified customer behavior or a reliable probability of commercial success. The model-generated seed is explicitly labeled as unverified background.

The round cap is not an agent-count or dollar-spend cap. Internal MiroShark model calls/cost are not included in the companion's model-request counter. Confirm backend spend controls before allowing new simulations. There are two local workers, at most four active/queued tasks, an 80-attempt companion model budget per run, a 30-minute active-phase timeout and bounded poll loops. Human approval wait time is excluded. Original MiroShark work may outlive the local timeout.

## Confidence and framework fidelity

Architecture basis: the user-supplied **Jev as a Probabilistic Decision Layer: Deep Research, Architecture, and SOP for JEV-able Workflows**. This repository contains an original implementation, not a copy of the private report or business-book library.

| Framework requirement | Implementation |
|---|---|
| Outcome Contract with success/failure, constraints, evidence and permissions | `contracts.py`, `prompts.py`, plan approval UI |
| Smallest independently executable components and dependency DAG | Typed atoms, topological validation, explicit input/source IDs and postconditions |
| Jev separate from open-ended generation | Native TypeSafe adapter in `providers.py`; frontier/executor HTTP adapters remain separate |
| Narrow independent validation dimensions | `PLAN_CHECKS` and `OUTPUT_CHECKS`; raw dimension vectors and versioned events |
| Structured repair without policy drift | Immutable Outcome Contract, unaffected-atom comparison, changed dependency descendants and hard iteration cap |
| Lower-tier execution plus postchecks | `engine.py`, bounded retries, one escalation, human review on persistent failure |
| Confidence calibration is empirical, not assumed | Raw 0.95 gate clearly provisional; no runtime reliability certificate or per-strategy success probability |
| Auditability and exception handling | SQLite runs/events, source hashes, model/schema/prompt versions, persisted remote IDs and explicit interrupted state |

The decision gate uses the **minimum** critical raw score, not an average or a product of supposedly independent probabilities. There is no claim that a 0.95 score means 95% correctness. This release stays advisory and does not apply a learned calibration profile.

An evaluation utility computes Brier score, ten-bin ECE, accepted-case coverage/precision and the lower endpoint of a two-sided 95% Wilson interval from externally labeled cases:

```sh
python -m strategy_app.calibration /path/to/held-out-cases.jsonl \
  --validator atomicity-v1 --model jev-1.13.0 --threshold 0.95
```

Each JSONL row must contain `{"score": 0.97, "label": true}` (use real held-out labels, not this illustration). Evaluate one fixed validator/domain/model version at a time. Do not recycle the same holdout to optimize thresholds and then claim independent validation. Results are evaluation evidence, not an automatic production certificate. No calibration dataset is bundled or fabricated.

## Security and deployment boundaries

Single-operator workspace: all authenticated users share its history. It is **not** a multi-tenant, internet-hardened SaaS. Provider keys never go to the browser or stored analysis inputs. The workspace token stays in page memory, not localStorage, URLs or cookies. API access fails closed, cross-origin requests are rejected, responses have a restrictive CSP, dynamic output is rendered as text and uploads have decompression/XML limits. This reduces risks; it is not an independent security audit.

The CLI is a local development server and binds to loopback by default. For remote use, place a production WSGI server behind a TLS reverse proxy and your own identity/access boundary. Use **one process** because the in-process work queue is not distributed; multiple threads are supported. For an environment that already has Gunicorn installed, an example is:

```sh
# Export the environment securely first; do not put tokens on command lines.
gunicorn --workers 1 --threads 8 --bind 127.0.0.1:5100 'strategy_app.server:create_app()'
```

The SQLite directory is operator-private; no disk encryption is supplied. Back it up according to your retention policy. An external lock prevents two app instances sharing one data directory. After a process restart, unfinished runs are marked interrupted and are not replayed; approved-but-not-executed work must be reviewed. Live API state, simulation services, proxy configuration, backups and production access control require deployment testing in your environment.

## Tests

```sh
python -m pytest strategy_app/tests -q
python -m compileall -q strategy_app
node --check strategy_app/static/app.js
```

Pytest is a development dependency; it is not needed to run the app. Tests cover contracts, confidence gates, repair invariants, source categories, provider schemas, API sequencing, auth, uploads, approvals, cancellation, persistence and synthetic end-to-end orchestration. Network adapters are tested against fake transports, not falsely reported as live Jev/MiroShark results.

Compatibility review baseline: MiroShark commit `faf7e0f83bf9034f3ebd40eef0eb87651d70d2b7`. Existing application files are unchanged. No new routes were registered in the original Flask backend, so its `backend/openapi.yaml` remains unchanged. The companion API has its own `openapi.yaml`.
