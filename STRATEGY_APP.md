# MiroShark Strategy

An advisory strategy-analysis workspace is available in [`strategy_app/`](strategy_app/README.md).

It accepts a question and supporting context, optionally runs or attaches a MiroShark simulation, compiles an Outcome Contract and process DAG, validates bounded criteria using Jev, executes approved atomic analysis, and presents a source-aware decision memo with alternatives, risks, next steps and SWOTMM.

The original MiroShark app remains unchanged. Start the companion from the repository root with `python -m strategy_app --env-file .env --env-file .env.strategy` after following its configuration instructions. It listens on loopback port 5100 by default. Live model and simulation calls are disabled until explicitly configured and enabled.

[Setup and boundaries](strategy_app/README.md) · [Implementation record](strategy_app/IMPLEMENTATION.md) · [Companion API](strategy_app/openapi.yaml)
