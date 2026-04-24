# DOCS_INDEX.md — Documentation Map

This index maps governance and operational documentation by authority level, audience, and usage trigger.

## Start Here by Role

### New contributor
1. [`README.md`](./README.md) — repo orientation, quickstart, and layout.
2. [`DOCS_INDEX.md`](./DOCS_INDEX.md) — canonical map for where each policy or procedure lives.
3. [`AGENT.md`](./AGENT.md) and [`AUTONOMY.md`](./AUTONOMY.md) — identity directives and permission tiers.
4. [`WORKFLOWS.md`](./WORKFLOWS.md) and [`TOOLS.md`](./TOOLS.md) — execution flow and available tooling.
5. [`SECURITY.md`](./SECURITY.md) and [`GOVERNANCE.md`](./GOVERNANCE.md) — required security and authority constraints.

### Operator
1. [`DOCS_INDEX.md`](./DOCS_INDEX.md) — canonical routing for policy and operational docs.
2. [`MCP_REGISTRY.md`](./MCP_REGISTRY.md) then [`MCP_SERVERS.md`](./MCP_SERVERS.md) — authorized servers first, integration details second.
3. [`WORKFLOWS.md`](./WORKFLOWS.md) and [`TOOLS.md`](./TOOLS.md) — workflow/tool execution alignment.
4. [`MEMORY.md`](./MEMORY.md) — state and memory model references.
5. [`AGENT_LOG.md`](./AGENT_LOG.md) — audit trail verification for operations and incidents.

### Reviewer/auditor
1. [`DOCS_INDEX.md`](./DOCS_INDEX.md) — canonical map for review scoping.
2. [`GOVERNANCE.md`](./GOVERNANCE.md) and [`AUTONOMY.md`](./AUTONOMY.md) — constitutional authority and tier boundaries.
3. [`SECURITY.md`](./SECURITY.md) and [`MCP_REGISTRY.md`](./MCP_REGISTRY.md) — control and authorization baseline.
4. [`AGENT_LOG.md`](./AGENT_LOG.md) — immutable action evidence.
5. [`WORKFLOWS.md`](./WORKFLOWS.md) and [`TOOLS.md`](./TOOLS.md) — behavior and control-path validation.

### Owner/HUMAN-0
1. [`DOCS_INDEX.md`](./DOCS_INDEX.md) — canonical documentation control point.
2. [`GOVERNANCE.md`](./GOVERNANCE.md) — constitutional authority source.
3. [`AUTONOMY.md`](./AUTONOMY.md), [`SECURITY.md`](./SECURITY.md), and [`MCP_REGISTRY.md`](./MCP_REGISTRY.md) — normative policy and authorization controls.
4. [`AGENT.md`](./AGENT.md) and [`WORKFLOWS.md`](./WORKFLOWS.md) — agent directive and operational behavior governance.
5. [`AGENT_LOG.md`](./AGENT_LOG.md) — audit/compliance oversight and retention process checks.

| Document | Authoritativeness | Primary Audience | Edit Restrictions | Typical Usage Triggers |
|---|---|---|---|---|
| [`README.md`](./README.md) | Informational | owner / operator / agent / reviewer | Open contribution | First-time repo orientation, quick links, setup |
| [`DOCS_INDEX.md`](./DOCS_INDEX.md) | Informational | owner / operator / agent / reviewer | Open contribution | Need to find canonical docs, responsibility routing |
| [`AGENT.md`](./AGENT.md) | Normative (agent identity + directives) | owner / operator / agent / reviewer | HUMAN-0 recommended (governance-sensitive) | Agent behavior checks, identity/scope questions, directive lookup |
| [`AUTONOMY.md`](./AUTONOMY.md) | **Normative (canonical tier matrix)** | owner / operator / agent / reviewer | HUMAN-0 only for policy changes | Tier resolution, permission disputes, PR tier-diff reviews |
| [`MCP_REGISTRY.md`](./MCP_REGISTRY.md) | **Normative (MCP authorization source of truth)** | owner / operator / agent / reviewer | HUMAN-0 only for active registration | MCP registration ceremony, server activation checks, scope validation |
| [`MCP_SERVERS.md`](./MCP_SERVERS.md) | Informational (integration details) | operator / agent / reviewer | Operator-maintained; active server state must align with `MCP_REGISTRY.md` | MCP connectivity/configuration troubleshooting |
| [`WORKFLOWS.md`](./WORKFLOWS.md) | Normative (operational workflow definitions) | owner / operator / agent / reviewer | HUMAN-0 recommended for workflow policy updates | Trigger/action mapping checks, automation behavior validation |
| [`TOOLS.md`](./TOOLS.md) | Informational | operator / agent / reviewer | Operator-maintained | Tool capability lookup, runtime/tooling audits |
| [`MEMORY.md`](./MEMORY.md) | Informational (architecture) | operator / agent / reviewer | Operator-maintained | Memory model review, state persistence design checks |
| [`SECURITY.md`](./SECURITY.md) | Normative (security policy) | owner / operator / agent / reviewer | HUMAN-0 only | Incident response, secrets/permissions policy checks |
| [`GOVERNANCE.md`](./GOVERNANCE.md) | Normative (constitutional governance) | owner / reviewer / operator / agent | HUMAN-0 only | Authority disputes, constitutional interpretation, approval boundary checks |
| [`AGENT_LOG.md`](./AGENT_LOG.md) | Normative record (audit ledger) | owner / operator / reviewer / agent | Append-only policy; HUMAN-0 controls retention/process changes | Incident forensics, action traceability, compliance review |

## Quick Links

- Agent manifest: [`AGENT.md`](./AGENT.md)
- Canonical autonomy matrix: [`AUTONOMY.md`](./AUTONOMY.md)
- MCP authorization registry: [`MCP_REGISTRY.md`](./MCP_REGISTRY.md)
