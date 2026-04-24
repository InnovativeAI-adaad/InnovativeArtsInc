# MCP_REGISTRY.md — MCP Server Registration Registry

> **Standard:** SPEC-IAI-003 | ADAAD v9.77.1
>
> **Documentation map:** [`DOCS_INDEX.md`](./DOCS_INDEX.md)
>
> **Invariant IAI-INV-001:** No MCP server may transition to `status: active` without
> `registered_by: HUMAN-0`. ArchitectAgent may draft records; only HUMAN-0 ratification
> promotes to active.
>
> **Invariant IAI-INV-002:** `permitted_scopes` must be exhaustive and enumerated.
> Wildcard (`*`) scopes are a Hard-class violation.

---

## Active Servers (Gate IAI-G2 authorized)

---

### SERVER: github-mcp
```yaml
server_id:               github-mcp
display_name:            GitHub MCP
url:                     https://github.mcp.claude.com/mcp
status:                  active
permitted_scopes:
  - contents:read
  - contents:write
  - pull_requests:read
  - pull_requests:write
  - issues:read
  - issues:write
  - actions:read
tier_minimum:            🟡
human_approval_required: false
registered_by:           HUMAN-0
registration_date:       2026-04-16T00:00:00Z
notes:                   Primary repo operations. Direct push to main is prohibited per SECURITY.md branch protection rules.
```

---

### SERVER: gmail-mcp
```yaml
server_id:               gmail-mcp
display_name:            Gmail MCP
url:                     https://gmail.mcp.claude.com/mcp
status:                  active
permitted_scopes:
  - messages:read
  - messages:send
  - drafts:create
  - labels:read
tier_minimum:            🟡
human_approval_required: false
registered_by:           HUMAN-0
registration_date:       2026-04-16T00:00:00Z
notes:                   Notifications and summaries only. May not send communications impersonating owner. See SECURITY.md §5.
```

---

### SERVER: google-calendar-mcp
```yaml
server_id:               google-calendar-mcp
display_name:            Google Calendar MCP
url:                     https://calendarmcp.googleapis.com/mcp/v1
status:                  active
permitted_scopes:
  - events:read
  - events:create
  - events:update
tier_minimum:            🟡
human_approval_required: false
registered_by:           HUMAN-0
registration_date:       2026-04-16T00:00:00Z
notes:                   Scheduling and reminders only. No deletion of existing owner events without 🔴 ratification.
```

---

## Planned Servers — HUMAN-0 Registration Ceremony Required

> ⚠️ FINDING-IAI-001: The following servers are **not authorized** for any MCP call
> until HUMAN-0 completes the registration ceremony on ADAADell and sets
> `status: active`. Any call against these servers triggers `MCP_UNREGISTERED_SERVER`
> hard abort.

---

### SERVER: spotify-mcp (DRAFT — not active)
```yaml
server_id:               spotify-mcp
display_name:            Spotify API
url:                     TBD
status:                  planned
permitted_scopes:        TBD — must be enumerated at registration ceremony
tier_minimum:            TBD
human_approval_required: true
registered_by:           PENDING HUMAN-0
registration_date:       TBD
notes:                   Music catalog management. Scope definition required before registration.
```

---

### SERVER: stripe-mcp (DRAFT — not active)
```yaml
server_id:               stripe-mcp
display_name:            Stripe
url:                     TBD
status:                  planned
permitted_scopes:        TBD — must be enumerated at registration ceremony
tier_minimum:            🔴
human_approval_required: true
registered_by:           PENDING HUMAN-0
registration_date:       TBD
notes:                   Financial operations. Unconditionally 🔴. All calls require HUMAN-0 ratification.
```

---

### SERVER: vercel-mcp (DRAFT — not active)
```yaml
server_id:               vercel-mcp
display_name:            Vercel
url:                     TBD
status:                  planned
permitted_scopes:        TBD — must be enumerated at registration ceremony
tier_minimum:            🟡
human_approval_required: true
registered_by:           PENDING HUMAN-0
registration_date:       TBD
notes:                   Deployment operations. Production deploys are unconditionally 🔴.
```

---

### SERVER: supabase-mcp (DRAFT — not active)
```yaml
server_id:               supabase-mcp
display_name:            Supabase
url:                     TBD
status:                  planned
permitted_scopes:        TBD — must be enumerated at registration ceremony
tier_minimum:            🟡
human_approval_required: true
registered_by:           PENDING HUMAN-0
registration_date:       TBD
notes:                   Database operations. Schema migrations are unconditionally 🔴.
```

---

### SERVER: slack-mcp (DRAFT — not active)
```yaml
server_id:               slack-mcp
display_name:            Slack
url:                     TBD
status:                  planned
permitted_scopes:        TBD — must be enumerated at registration ceremony
tier_minimum:            🟡
human_approval_required: true
registered_by:           PENDING HUMAN-0
registration_date:       TBD
notes:                   Messaging and notifications. May not impersonate owner.
```

---

## Registration Ceremony Protocol

To promote a server from `planned` to `active`, HUMAN-0 must:

1. Review the draft record and enumerate `permitted_scopes` exhaustively (no wildcards).
2. Set `tier_minimum` based on scope risk classification.
3. Set `human_approval_required: true | false`.
4. Set `registered_by: HUMAN-0` and `registration_date: [ISO-8601]`.
5. Set `status: active`.
6. Commit the change to this file with a GPG-signed commit on ADAADell.
7. Log the ceremony in `AGENT_LOG.md` as a `🔴` entry with `human_ratified: true`.

ArchitectAgent may update draft records; only a GPG-signed commit from HUMAN-0 activates a server.

---

*MCP_REGISTRY.md is the authoritative server authorization surface. Gate IAI-G2 reads only this file.*
