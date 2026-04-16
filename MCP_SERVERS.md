# MCP_SERVERS.md — Model Context Protocol Server Registry

> Part of the **InnovativeArtsInc** Agent Documentation Suite  
> MCP enables AI agents to interact with external services through standardized tool interfaces.

---

## 1. What is MCP?

Model Context Protocol (MCP) is an open standard that allows AI agents to connect to external services — GitHub, Gmail, databases, APIs — through a unified interface. Each MCP server exposes a set of **tools** the agent can call autonomously.

---

## 2. Active MCP Servers

### 🔗 GitHub MCP
```yaml
name: github-mcp
url: https://api.github.com/mcp
auth: GitHub App (InnovativeAI-adaad)
tools:
  - read_repository
  - create_branch
  - commit_files
  - open_pull_request
  - merge_pull_request
  - create_issue
  - comment_on_issue
  - list_workflows
  - trigger_workflow
scope: InnovativeAI-adaad/*
```

### 📧 Gmail MCP
```yaml
name: gmail-mcp
url: https://gmail.mcp.claude.com/mcp
auth: OAuth2 (owner account)
tools:
  - send_email
  - read_inbox
  - search_emails
  - create_draft
scope: agent notifications only
permitted_recipients:
  - dustinreid82@gmail.com
```

### 📅 Google Calendar MCP
```yaml
name: google-calendar-mcp
url: https://calendarmcp.googleapis.com/mcp/v1
auth: OAuth2 (owner account)
tools:
  - list_events
  - create_event
  - update_event
  - delete_event
scope: InnovativeArtsInc project calendar
```

---

## 3. Planned MCP Servers (Not Yet Active)

| Server          | Purpose                              | Status     |
|----------------|--------------------------------------|------------|
| Slack MCP       | Team notifications & commands        | 🔜 Planned |
| Notion MCP      | Project docs & knowledge base        | 🔜 Planned |
| Stripe MCP      | Payment & subscription tracking      | 🔜 Planned |
| Spotify MCP     | Music catalog integration            | 🔜 Planned |
| AWS MCP         | Cloud infrastructure management      | 🔜 Planned |
| Vercel MCP      | Frontend deployment automation       | 🔜 Planned |
| Supabase MCP    | Database reads for agent context     | 🔜 Planned |

---

## 4. Adding a New MCP Server

To register a new MCP server with the ADAAD-Agent:

1. Add an entry to this file under **Active MCP Servers**
2. Specify: `name`, `url`, `auth`, `tools`, `scope`
3. Add the server to `TOOLS.md` tool registry
4. Set any Level 2+ tools as requiring owner notification in `AUTONOMY.md`
5. Test with a Level 1 read operation before enabling write operations
6. Open a PR with label `mcp-config` for owner review

---

## 5. MCP Security Policy

```
- All MCP connections must use HTTPS.
- OAuth tokens and API keys are stored in environment secrets — never in code.
- Each MCP server is scoped to minimum required permissions.
- MCP tool calls are logged in AGENT_LOG.md with server, tool, and parameters.
- Sensitive parameters (passwords, keys) are redacted in logs.
- MCP servers with write access require Level 2+ authorization.
```

---

## 6. Using MCP in Agent Code

```javascript
// Example: Calling GitHub MCP from agent runtime
const response = await fetch("https://api.anthropic.com/v1/messages", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "claude-sonnet-4-20250514",
    max_tokens: 1000,
    messages: [{ role: "user", content: "Open a PR for the latest changes" }],
    mcp_servers: [
      {
        type: "url",
        url: "https://api.github.com/mcp",
        name: "github-mcp"
      }
    ]
  })
});
```

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*
