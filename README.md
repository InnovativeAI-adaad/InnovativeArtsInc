# InnovativeArtsInc 🎵

> A music and creative arts platform powered by AI.  
> Part of the [@InnovativeAI-adaad](https://github.com/InnovativeAI-adaad) organization.  
> Built by **Dustin L. Reid** · [adaad.pro](http://adaad.pro)

---

## About

InnovativeArtsInc is a music repository and creative platform that combines AI-powered automation with artistic production. The project is fully integrated with the **ADAAD-Agent** autonomous AI system for development, documentation, catalog management, and marketing workflows.

## 📚 Documentation Map

Use [`DOCS_INDEX.md`](./DOCS_INDEX.md) to quickly identify which documents are normative vs informational, who should edit them, and when to use each one.

---

## 🤖 Autonomous Agent

This repository is powered by **ADAAD-Agent** — an autonomous AI agent that handles development workflows, documentation, music cataloging, and communications without requiring manual intervention for routine tasks.

| Doc | Purpose |
|-----|---------|
| [`AGENT.md`](./AGENT.md) | Agent identity, directives, and autonomy levels |
| [`AUTONOMY.md`](./AUTONOMY.md) | Detailed capability and permission boundaries |
| [`TOOLS.md`](./TOOLS.md) | Full tool registry across all integrations |
| [`MCP_SERVERS.md`](./MCP_SERVERS.md) | MCP server connections and configuration |
| [`WORKFLOWS.md`](./WORKFLOWS.md) | Automated workflow definitions |
| [`MEMORY.md`](./MEMORY.md) | Agent memory and state architecture |
| [`SECURITY.md`](./SECURITY.md) | Security policies for agent operations |

### Constitutional Governance (ADAAD v9.77.1)

| Doc | Purpose |
|-----|---------|
| [`GOVERNANCE.md`](./GOVERNANCE.md) | Constitutional subordination contract — ADAAD HUMAN-0 authority model |
| [`MCP_REGISTRY.md`](./MCP_REGISTRY.md) | Authoritative MCP server registry — Gate IAI-G2 source of truth |
| [`AGENT_LOG.md`](./AGENT_LOG.md) | HMAC-chained append-only audit ledger — all agent actions |

---

## 🚀 Getting Started

```bash
git clone https://github.com/InnovativeAI-adaad/InnovativeArtsInc.git
cd InnovativeArtsInc
```

More setup instructions coming as the project develops.

---

## 📬 Contact

- GitHub: [@InnovativeAI-adaad](https://github.com/InnovativeAI-adaad)
- Email: dustinreid82@gmail.com
- Site: [adaad.pro](http://adaad.pro)

---

*Powered by ADAAD-Agent | InnovativeAI-adaad © 2026*

## 🏗️ Sovereign Ledger Production Engine

The repository now includes a production scaffold for the **Red Dirt Revelation: The Sovereign Ledger** initiative:

- `core/` for ADAAD engine modules and agent logic
- `projects/jrt/` for audio, lyrics, metadata, visuals, and rollout assets
- `registry/` for version/provenance state
- `pipelines/` for ingestion and release automation scripts

Runtime observability artifacts for Sovereign Ledger are emitted to:
- `registry/metrics.jsonl` for stage-level completion telemetry
- `registry/dashboard_snapshot.json` for periodic queue/success/retry/failure summary snapshots

### Provenance deduplication behavior

The IP provenance hasher writes artifact entries to `registry/provenance_log.jsonl` using a stable dedup key:

- `job_id + track_id + file + sha256`

Before appending, existing JSONL rows are stream-read and indexed in-memory for O(1) duplicate checks, which prevents duplicate noise during retry/replay runs while still allowing new rows when artifact content changes (`sha256` changes).

Provenance rows now include explicit retry metadata:

- `retry_attempt` (integer, defaults to `0`)
- `is_retry` (boolean marker derived from `retry_attempt > 0`)

This keeps operations auditable for repeated runs without appending duplicate entries for unchanged artifacts.

Use `./init_engine.sh` to re-create the baseline structure in fresh environments.
