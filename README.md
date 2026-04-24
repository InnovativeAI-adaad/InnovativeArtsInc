# InnovativeArtsInc 🎵

InnovativeArtsInc is an AI-assisted music and creative operations repository for building, tracking, and releasing Sovereign Ledger artifacts with auditable automation.

## Table of Contents

- [Quick Links](#quick-links)
- [Installation and Quickstart](#installation-and-quickstart)
- [Repository Layout](#repository-layout)
- [Operational Notes](#operational-notes)
- [Contact and License](#contact-and-license)

## Quick Links

### Agent and Governance Docs

| Document | Purpose |
|---|---|
| [`AGENT.md`](./AGENT.md) | Agent identity, directives, and autonomy levels |
| [`AUTONOMY.md`](./AUTONOMY.md) | Capability and permission boundaries |
| [`TOOLS.md`](./TOOLS.md) | Tool registry across integrations |
| [`MCP_SERVERS.md`](./MCP_SERVERS.md) | MCP server connections and configuration |
| [`WORKFLOWS.md`](./WORKFLOWS.md) | Automated workflow definitions |
| [`MEMORY.md`](./MEMORY.md) | Agent memory and state architecture |
| [`SECURITY.md`](./SECURITY.md) | Security policies for agent operations |
| [`GOVERNANCE.md`](./GOVERNANCE.md) | Constitutional subordination contract (ADAAD HUMAN-0 authority model) |
| [`MCP_REGISTRY.md`](./MCP_REGISTRY.md) | Authoritative MCP server registry (Gate IAI-G2 source of truth) |
| [`AGENT_LOG.md`](./AGENT_LOG.md) | HMAC-chained append-only audit ledger for all agent actions |

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

Expected result: scaffold directories are ensured and registry baseline artifacts are created/preserved under `registry/`.

### Current non-goals

- No packaged installer yet (`pip`, `npm`, or container image).
- No single-command full production run orchestrator documented in this README yet.

## Repository Layout

The repository includes a production scaffold for the **Red Dirt Revelation: The Sovereign Ledger** initiative:

- `core/` for ADAAD engine modules and agent logic
- `projects/jrt/` for audio, lyrics, metadata, visuals, and rollout assets
- `registry/` for version/provenance state
- `pipelines/` for ingestion and release automation scripts

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

## Documentation Contribution Guidelines

Documentation updates are welcome, but policy and governance files have different contribution rules.

- Use [`DOCS_INDEX.md`](./DOCS_INDEX.md) as the authority map for document status and edit restrictions.
- **Open contribution docs** (for example, `README.md` and `DOCS_INDEX.md`) can be updated through normal pull requests.
- **HUMAN-0-governed docs** (for example, `AUTONOMY.md`, `GOVERNANCE.md`, `SECURITY.md`, and policy-governed sections noted in `DOCS_INDEX.md`) require governance review/approval for policy-impacting edits.

### Minimal PR checklist for docs updates

- [ ] Links resolve correctly (internal anchors, relative paths, and external links).
- [ ] Statements remain consistent with canonical sources (especially `AUTONOMY.md`, `MCP_REGISTRY.md`, and `GOVERNANCE.md` where applicable).
- [ ] Governance review is requested when changes touch HUMAN-0-restricted or normative governance material.
- [ ] If `AGENT.md` or `AUTONOMY.md` is touched, include a tier-diff expectation note in the PR to confirm action/tier alignment.

## Contact and License

- GitHub: [@InnovativeAI-adaad](https://github.com/InnovativeAI-adaad)
- Email: dustinreid82@gmail.com
- Site: [adaad.pro](http://adaad.pro)

*Powered by ADAAD-Agent | InnovativeAI-adaad © 2026*
