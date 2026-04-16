# SECURITY.md — Agent Security Policy

> Part of the **InnovativeArtsInc** Agent Documentation Suite  
> ⚠️ This file may only be modified by the repo owner. Never modify autonomously.

---

## 1. Authentication

| Service         | Auth Method                  | Storage              |
|----------------|------------------------------|----------------------|
| GitHub          | GitHub App Private Key + PAT | Repository Secrets   |
| Gmail           | OAuth2                       | Environment Secrets  |
| Google Calendar | OAuth2                       | Environment Secrets  |
| Llama API       | API Key                      | Environment Secrets  |
| ngrok           | Auth Token                   | Environment Secrets  |
| Gravatar        | Client ID + Secret           | Environment Secrets  |

**Rule:** All credentials are stored in GitHub Actions secrets or a secrets manager. They are **never** committed to any file or included in any log, comment, or output.

---

## 2. Permissions Principle of Least Privilege

- Each integration is granted only the minimum permissions required for its defined workflows.
- GitHub App scopes: `contents:write`, `pull_requests:write`, `issues:write`, `actions:read`
- No agent integration is granted admin-level access.
- Service accounts are separate from the owner's personal account.

---

## 3. Branch Protection Rules

```yaml
main:
  required_reviews: 1 (owner)
  dismiss_stale_reviews: true
  require_status_checks: true
  restrict_pushes_to: owner + GitHub App
  agent_direct_push: ❌ NEVER

staging:
  required_reviews: 0 (agent may merge from dev)
  require_status_checks: true
  agent_direct_push: ❌ Via PR only

dev:
  agent_direct_push: ❌ Via PR only
  require_status_checks: true
```

---

## 4. Secret Scanning & Gate IAI-G3 Credential Isolation

> **Constitutional hard dependency — SPEC-IAI-001 · Gate IAI-G3 · ADAAD v9.77.1**

### Gate IAI-G3 — Always-On Credential Isolation

Gate IAI-G3 is a **constitutional invariant**. It cannot be disabled, bypassed, or
suspended by any agent tier, including 🟢 fully autonomous operations.

**What it checks:** Every agent output surface — MCP payloads, workflow artifacts,
`AGENT_LOG.md` entries, commit messages, PR bodies, issue comments — is scanned
for known credential token patterns before emission.

**Failure mode:** `CREDENTIAL_LEAK_DETECTED` → hard abort, quarantine artifact,
alert HUMAN-0. No partial output is permitted.

**Patterns that trigger hard abort (non-exhaustive):**
```
github_pat_*          GitHub PAT (fine-grained)
ghp_*                 GitHub PAT (classic)
sk-ant-*              Anthropic API key
gsk_*                 Groq API key
-----BEGIN * KEY----  PEM private key block
*_SECRET*             Generic secret identifier
```

### GitHub Secret Scanning (repo-level)

- GitHub Secret Scanning is **enabled** on this repository.
- Any accidental commit of a secret should be treated as a breach:
  1. Revoke the exposed credential immediately.
  2. Generate a new credential.
  3. Use `git filter-repo` to purge the commit from history.
  4. Force-push and notify all collaborators.
  5. Log the incident in `AGENT_LOG.md` as a `🔴` entry with `human_ratified: true`.

---

## 5. Agent Impersonation Protection

- All agent-created commits are signed and prefixed with `[AGENT]`.
- Agent PRs are labeled `agent-created` automatically.
- No agent may send communications impersonating the repo owner.
- Owner communications always come from `dustinreid82@gmail.com` directly.

---

## 6. Incident Response

| Severity | Condition                              | Response                              |
|----------|----------------------------------------|---------------------------------------|
| 🔴 Critical | Credential exposed, breach suspected | Revoke all, audit logs, notify owner  |
| 🟡 High    | Agent exceeded autonomy level         | Halt agent, rollback action, review   |
| 🟡 High    | Unauthorized external request         | Block endpoint, audit logs            |
| 🟢 Low     | Unexpected workflow failure           | Log, notify owner, retry once         |

---

## 7. Security Review Checklist

Before any new integration or workflow goes live:

- [ ] Auth method reviewed and uses secrets (not hardcoded)
- [ ] Permissions scoped to minimum required
- [ ] Autonomy level correctly assigned in `AUTONOMY.md`
- [ ] Rollback plan defined in `WORKFLOWS.md`
- [ ] No sensitive data written to logs or files
- [ ] Branch protection rules verified
- [ ] Owner has reviewed and approved via PR

---

*This file is owner-maintained only. ADAAD-Agent may read but never modify.*
