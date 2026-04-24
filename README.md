# InnovativeArtsInc 🎵

InnovativeArtsInc is an AI-assisted music and creative operations repository for building, tracking, and releasing Sovereign Ledger artifacts with auditable automation.

## Table of Contents

- [Quick Links](#quick-links)
- [Installation and Quickstart](#installation-and-quickstart)
- [Repository Layout](#repository-layout)
- [Operational Notes](#operational-notes)
- [Contact and License](#contact-and-license)

## Quick Links

`DOCS_INDEX.md` is the canonical documentation map for governance and operational navigation: [`DOCS_INDEX.md`](./DOCS_INDEX.md).

| Document | Use |
|---|---|
| [`AGENT.md`](./AGENT.md) | Agent directives |
| [`AUTONOMY.md`](./AUTONOMY.md) | Permission tiers |
| [`MCP_REGISTRY.md`](./MCP_REGISTRY.md) | Authorized MCP servers |
| [`MCP_SERVERS.md`](./MCP_SERVERS.md) | MCP integration details |
| [`WORKFLOWS.md`](./WORKFLOWS.md) | Workflow definitions |
| [`TOOLS.md`](./TOOLS.md) | Tool inventory |
| [`MEMORY.md`](./MEMORY.md) | Memory/state model |
| [`SECURITY.md`](./SECURITY.md) | Security policy |
| [`GOVERNANCE.md`](./GOVERNANCE.md) | Governance policy |
| [`AGENT_LOG.md`](./AGENT_LOG.md) | Audit ledger |

## Installation and Quickstart

### Prerequisites

- Bash-compatible shell
- Git
- Python 3.11+ (for pipeline/test scripts)

### Install

```bash
git clone https://github.com/InnovativeAI-adaad/InnovativeArtsInc.git
cd InnovativeArtsInc
```

### Minimal quickstart (runs now)

```bash
./init_engine.sh
```

#### Verify initialization

Run these checks to confirm required registry artifacts were created:

```bash
test -f registry/version_manifest.json && echo "✓ version_manifest.json present"
test -f registry/provenance_log.jsonl && echo "✓ provenance_log.jsonl present"
test -f registry/metrics.jsonl && echo "✓ metrics.jsonl present"
test -f registry/dashboard_snapshot.json && echo "✓ dashboard_snapshot.json present"
```

If any command exits non-zero, rerun:

```bash
./init_engine.sh
```

#### Reset mode (`--reset`)

`init_engine.sh` supports one flag: `--reset`.

```bash
./init_engine.sh --reset
```

⚠️ Warning: `--reset` reinitializes registry artifacts (for example, baseline files under `registry/` are recreated), so use it only when you intentionally want a fresh registry state.

Expected result: scaffold directories are ensured and registry baseline artifacts are created/preserved under `registry/`.

### Current non-goals

- No packaged installer yet (`pip`, `npm`, or container image).
- No single-command full production run orchestrator documented in this README yet.

## Repository Layout

Current checked-in layout (fresh clone):

- `core/agents`, `core/gatekeeper`, `core/governance`
- `services/*` modules (for example: `ar_orchestrator`, `creative_planner`, `growth_ops`, `media_conductor`, `media_generation`, `release_pipeline`, `rights_ledger`)
- `pipelines/*`
- `projects/jrt/metadata/*` (currently `incidents`, `jobs`, `schema`)
- `registry/*`

Note: `./init_engine.sh` can scaffold additional directories at runtime that may not be present in a fresh clone.

## Operational Notes

### Telemetry outputs

Runtime observability artifacts are emitted to:

- `registry/metrics.jsonl` for stage-level completion telemetry
- `registry/dashboard_snapshot.json` for periodic queue/success/retry/failure summary snapshots

Expected `registry/metrics.jsonl` record shape:

```json
{
  "job_id": "job-123",
  "stage": "ip_agent.run",
  "duration_ms": 152,
  "result": "success",
  "fitness_score": 1.0,
  "timestamp": "2026-04-24T12:00:00+00:00",
  "uniqueness_validation_time_ms": 245,
  "novelty_index": 0.87,
  "similarity_guardrail_pass": true
}
```

Notes:

- `uniqueness_validation_time_ms`, `novelty_index`, and `similarity_guardrail_pass` are optional telemetry fields emitted by the IPAgent uniqueness audit stage (`ip_agent.uniqueness_audit`).
- Existing metric producers can omit these optional fields without breaking telemetry ingestion.

### Provenance behavior and deduplication

The IP provenance hasher writes artifact entries to `registry/provenance_log.jsonl` using a stable deduplication key:

- `job_id + track_id + file + sha256`

Before appending, existing JSONL rows are stream-read and indexed in memory for O(1) duplicate checks. This avoids duplicate entries during retry/replay runs while still allowing new rows when artifact content changes (`sha256` changes).

Provenance rows include retry metadata:

- `retry_attempt` (integer, defaults to `0`)
- `is_retry` (boolean marker derived from `retry_attempt > 0`)

This keeps repeated runs auditable without appending duplicate entries for unchanged artifacts.

## Contact and License

- GitHub: [@InnovativeAI-adaad](https://github.com/InnovativeAI-adaad)
- Email: dustinreid82@gmail.com
- Site: [adaad.pro](http://adaad.pro)

*Powered by ADAAD-Agent | InnovativeAI-adaad © 2026*
