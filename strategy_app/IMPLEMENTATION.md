# Strategy Analysis implementation record

## Authorized scope
Build a separate strategy workspace in J182Razor/MiroShark on feat/jev-strategy-analysis. Accept a question or idea, use the supplied JEV-able workflow framework and actual MiroShark interfaces, and present a strategic analysis. Preserve the original application and main branch.

## Architecture decision
A standard-library Python companion (HTTP, SQLite, static ES modules) invokes MiroShark's authenticated API. It avoids modifying the simulation engine, its Flask route contract, or the Vue application. Providers are server configured. No model-generated code or arbitrary tool execution is permitted. The application is advisory and single-operator, not multi-tenant SaaS.

## Source contract
The supplied report, Jev as a Probabilistic Decision Layer: Deep Research, Architecture, and SOP for JEV-able Workflows, is the architecture basis. Outcome Contract, process DAG, typed validators, bounded targeted refinement, lower-tier execution, runtime verification and human review are retained. The 0.95 default is a provisional score threshold. There is no audited reliability claim and no hidden confidence averaging. Original document/private business books are not distributed with the application.

## Implementation sequence and gates
1. Deterministic contracts and DAG: validate unique IDs, dependencies, source IDs, executor allowlist, no business side effects, confidence vector and repair invariants. Verify failing tests, then passing tests.
2. Provider and MiroShark adapters: exact native TypeSafe request/response contract; OpenAI-compatible planner/executor; actual graph/prepare/start/poll/observations interfaces. Test fake network transports, malformed replies, no mutation retries, and safe URL handling.
3. Durable orchestration: persist runs/events in SQLite; separate planning approval from execution; bound jobs, API calls, retries, iterations and elapsed time. Test cancellation, restart interruption, revision provenance, missing credentials, and demo isolation.
4. Workspace: question/context/evidence intake, model readiness, history, live stages, plan approval, report and evidence tabs, review queue, Markdown/JSON exports. Use native text rendering, not untrusted HTML.
5. Verification: full companion pytest suite, Python compilation, JavaScript syntax, local desktop/mobile browser flow with explicitly synthetic providers. Review security and source fidelity. Push tested files using GitHub Git data APIs and read back hashes.

## Environment limitations and rulings
The connector can read/write GitHub, but the local container cannot resolve GitHub and cannot clone/install dependencies. Ruling: reconstruct only the new companion files locally, test those files, and add them to the exact main tree through the GitHub API. Do not claim the upstream suite ran or a live provider test passed. Base commit: faf7e0f83bf9034f3ebd40eef0eb87651d70d2b7.

## Review focus
Missing evidence must not turn into claimed fact. Raw scores must not turn into a reliability promise. Missing or invalid model responses must fail closed. Repair must not change the original objective or permissions. Cancellation and failures must not silently trigger duplicate simulations. Provider tokens must never reach the browser, public errors or logs.

## Verification performed
- 51 companion tests passed with `python -m pytest strategy_app/tests -q`. Tests use synthetic provider transports, never a live API key.
- `python -m compileall -q strategy_app` and `node --check strategy_app/static/app.js` passed.
- System Chromium through Playwright exercised unlock, a synthetic run, plan approval, completed memo, all five tabs, human review, mobile history, revision, and lock at 1440x1000 and 390x844. No page/console errors or horizontal mobile overflow were observed.
- Browser navigation to localhost was blocked by administrator policy. No policy was disabled. Browser QA instead injected the actual static assets into an offline document and connected fetch to the actual WSGI application in-process. Network delivery/CSP were checked separately, not represented as browser network coverage.
- A nonblocking OS file lease prevents two instances from recovering/executing against the same data directory.
- The original repository's tests and live Jev/frontier/executor/MiroShark calls were not run. Those require the upstream runtime and configured provider credentials. Synthetic browser results are not evidence of model quality or calibration.
