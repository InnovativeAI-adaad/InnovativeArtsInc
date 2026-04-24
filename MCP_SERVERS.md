# MCP_SERVERS.md — Model Context Protocol Server Index (Informational Only)

> Part of the **InnovativeArtsInc** Agent Documentation Suite.
> MCP enables AI agents to interact with external services through standardized tool interfaces.

> [!WARNING]
> **Authoritative source:** `MCP_REGISTRY.md` is the only enforcement surface for MCP authorization.
> If any value in this document differs from `MCP_REGISTRY.md`, treat the registry value as the immediate override for all policy and runtime decisions.

---

## 1. Purpose of This File

This document is a human-readable index of known MCP servers and integration context.
It is **non-authoritative** and must not be used for policy enforcement, allow/deny decisions,
or gate validation logic.

For all enforcement decisions (status, endpoint, permitted scopes, approval requirements, tier):
- Read `MCP_REGISTRY.md` only.
- Apply Gate IAI-G2 checks against `MCP_REGISTRY.md` only.

---

## 2. Informational Index (Non-Authoritative)

> This index intentionally omits per-server enforcement fields that can drift (for example: policy-level scope authority and allow/deny semantics).
> Resolve all such values directly from `MCP_REGISTRY.md` at decision time.

### Active MCP Servers (index snapshot)

| Server ID            | Display Name          | Endpoint (for operator awareness)            | Capability Summary (informational) |
|---------------------|-----------------------|----------------------------------------------|------------------------------------|
| `github-mcp`        | GitHub MCP            | `https://github.mcp.claude.com/mcp`          | Repository, pull request, issue, and Actions interactions aligned to registry scopes. |
| `gmail-mcp`         | Gmail MCP             | `https://gmail.mcp.claude.com/mcp`           | Mail read/send, drafts, and label read operations aligned to registry scopes. |
| `google-calendar-mcp` | Google Calendar MCP | `https://calendarmcp.googleapis.com/mcp/v1`  | Event read/create/update workflows (no delete capability in active registry record). |

---

## 3. Planned MCP Servers (Not Yet Active)

For planned/draft servers and activation status, refer to `MCP_REGISTRY.md`.
Any server not marked `status: active` in `MCP_REGISTRY.md` is unauthorized for runtime MCP calls.

---

## 4. Registering or Updating MCP Servers

When adding or changing an MCP server:

1. Update `MCP_REGISTRY.md` first (or only).
2. Complete required registration ceremony details in `MCP_REGISTRY.md`.
3. Treat this file as optional documentation index material.
4. If this file is updated, ensure wording does not introduce duplicate authority fields.

---

## 5. MCP Security Policy (Reference)

Security controls are enforced from normative policy documents and runtime gates.
This file provides guidance only:

- MCP connections must use HTTPS.
- Credentials remain in secret stores, never committed to source.
- Calls are logged with redaction where required.
- Approval and tier logic must be resolved from authoritative registry + gate policies.

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*
