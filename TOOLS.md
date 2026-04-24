# TOOLS.md — Agent Tool Registry

> Part of the **InnovativeArtsInc** Agent Documentation Suite  
> All tools available to ADAAD-Agent across integrations and runtimes.
> **Tier source of truth:** `AUTONOMY.md` §1 “Canonical Autonomy Matrix” is normative; if tool tiers conflict across docs, follow `AUTONOMY.md`.

---

## 1. Tool Categories

| Category        | Description                                      |
|----------------|--------------------------------------------------|
| `code`          | Code generation, review, testing, linting        |
| `git`           | GitHub operations via MCP                        |
| `communication` | Email, calendar, notifications                   |
| `search`        | Web search, documentation lookup                 |
| `memory`        | Read/write agent memory and logs                 |
| `media`         | Music, audio, image operations (InnovativeArts)  |
| `deploy`        | Build, release, and deployment tools             |

---

## 2. Active Tools

### 🛠 Code Tools

| Tool                | Source       | Level | Description                            |
|--------------------|-------------|-------|----------------------------------------|
| `generate_code`     | Claude API   | 🟡 2  | Generate new code from natural language|
| `review_code`       | Claude API   | 🟡 2  | Analyze diff and suggest improvements  |
| `run_tests`         | GitHub Actions| 🟢 1 | Trigger test suite, return results     |
| `lint_code`         | GitHub Actions| 🟢 1 | Run ESLint / Prettier / language linter|
| `explain_code`      | Claude API   | 🟡 2  | Explain what a file or function does   |
| `refactor_code`     | Claude API   | 🟡 2  | Refactor with explanation              |

---

### 🐙 Git Tools

| Tool                  | Source       | Level | Description                          |
|----------------------|-------------|-------|--------------------------------------|
| `read_repo`           | GitHub MCP   | 🟢 1  | Read files and directory structure   |
| `list_branches`       | GitHub MCP   | 🟢 1  | List all branches                    |
| `create_branch`       | GitHub MCP   | 🟡 2  | Create a new branch                  |
| `commit_files`        | GitHub MCP   | 🟡 2  | Commit one or more files             |
| `open_pr_draft`             | GitHub MCP   | 🟡 2  | Open a pull request (draft)          |
| `merge_pr_dev_staging`            | GitHub MCP   | 🟡 2  | Merge PR to dev/staging              |
| `create_issue`        | GitHub MCP   | 🟢 1  | Create a labeled issue               |
| `comment_on_pr`       | GitHub MCP   | 🟢 1  | Post review comment on PR            |
| `close_issue`         | GitHub MCP   | 🟡 2  | Close issue with reason              |
| `trigger_workflow`    | GitHub MCP   | 🟡 2  | Manually trigger a GitHub Action     |

---

### 📬 Communication Tools

| Tool                  | Source          | Level | Description                        |
|----------------------|----------------|-------|------------------------------------|
| `send_email_owner`          | Gmail MCP       | 🟡 2  | Send notification email to owner   |
| `read_inbox`          | Gmail MCP       | 🟢 1  | Read incoming emails               |
| `create_calendar_event`| Calendar MCP   | 🟡 2  | Schedule a project milestone       |
| `list_calendar`       | Calendar MCP    | 🟢 1  | Read upcoming project events       |

---

### 🔍 Search & Research Tools

| Tool                  | Source       | Level | Description                          |
|----------------------|-------------|-------|--------------------------------------|
| `web_search_trends`      | Claude API   | 🟡 2  | Research-only web lookup             |
| `fetch_url`           | Claude API   | 🟢 1  | Fetch and read a specific URL        |
| `search_npm`          | web_search_trends | 🟢 1  | Find packages and docs on npm        |
| `search_github`       | GitHub MCP   | 🟢 1  | Search GitHub for code/issues/users  |

---

### 🧠 Memory Tools

| Tool                  | Source       | Level | Description                          |
|----------------------|-------------|-------|--------------------------------------|
| `read_agent_log`      | File (repo)  | 🟢 1  | Read AGENT_LOG.md                    |
| `write_agent_log`     | File (repo)  | 🟢 1  | Append entry to AGENT_LOG.md         |
| `read_memory`         | File (repo)  | 🟢 1  | Read MEMORY.md knowledge store       |
| `update_memory`       | File (repo)  | 🟡 2  | Update long-term memory file         |

---

### 🎵 Media Tools (InnovativeArts-Specific)

| Tool                  | Source       | Level | Description                          |
|----------------------|-------------|-------|--------------------------------------|
| `catalog_music`       | Custom       | 🟡 2  | Catalog tracks, albums, metadata     |
| `generate_metadata`   | Claude API   | 🟡 2  | Generate descriptions for tracks     |
| `tag_audio`           | Custom       | 🟡 2  | Write ID3 tags to audio files        |
| `draft_press_release` | Claude API   | 🟡 2  | Write artist/release press copy      |
| `generate_lyrics`     | Claude API   | 🟡 2  | Generate song lyrics from brief      |

---

## 3. Tool Call Format

All agent tool calls must follow this structure for logging and traceability:

```json
{
  "tool": "tool_name",
  "category": "code | git | communication | search | memory | media | deploy",
  "level": 1,
  "params": {},
  "called_by": "ADAAD-Agent",
  "timestamp": "ISO-8601",
  "task_id": "uuid"
}
```

---

## 4. Adding New Tools

1. Add entry to the relevant table in this file
2. Specify source, level, and description
3. If the tool has write/modify access, assign Level 2+
4. Reference the tool in any relevant `WORKFLOWS.md` definitions
5. Open a PR labeled `tool-registry`

---

*Last updated by: Dustin L. Reid | Auto-maintained by ADAAD-Agent (Level 1)*

*Changelog: Terminology normalization — aligned action aliases to `AUTONOMY.md` §1 canonical identifiers (`open_pr_draft`, `merge_pr_dev_staging`, `send_email_owner`, `web_search_trends`).*
