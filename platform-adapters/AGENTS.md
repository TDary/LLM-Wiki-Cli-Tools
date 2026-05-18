# AGENTS.md — LLM Wiki Knowledge Base

> Platform-agnostic agent instructions.  
> Works with: OpenClaw, Cursor, Windsurf, GitHub Copilot, and any agent that reads AGENTS.md.

## Quick Start

```bash
# One-command team wiki setup
wiki-bootstrap <REMOTE_URL> ~/team-wiki --domain "Team Knowledge Base"

# Manual sync
git-auto-sync ~/team-wiki

# Init new wiki
wiki-init <path> "<domain>"
```

## Key Rules

1. **Read before writing** — always check `SCHEMA.md`, `README.md`, and recent `log.md` first
2. **Auto-sync after changes** — run `git-auto-sync ~/team-wiki` after any modification
3. **Cross-reference** — every new page must link to ≥2 existing pages with `[[wikilinks]]`
4. **Log everything** — append to `log.md` after every action (ingest, update, query)
5. **Raw is immutable** — never modify files in `raw/`. Corrections go in wiki pages.

## Directory Layout

| Directory | Purpose |
|-----------|---------|
| `raw/` | Immutable source material |
| `entities/` | People, projects, tools, orgs |
| `concepts/` | Ideas, terms, methodologies |
| `relations/` | Cross-references between entities |
| `queries/` | Saved search results |
| `drafts/` | Work in progress |

## CLI Tools (platform-agnostic)

All tools are pure bash, no dependencies beyond git:

| Tool | Purpose |
|------|---------|
| `git-auto-sync <path>` | Auto-commit + push any Git repo |
| `wiki-init <path> <domain>` | Initialize wiki directory structure |
| `wiki-bootstrap <url> [path]` | One-command clone + init + cron sync |

Environment variables for `git-auto-sync`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `GIT_SYNC_NAME` | `AI Assistant` | Committer name |
| `GIT_SYNC_EMAIL` | `ai@local` | Committer email |
| `GIT_SYNC_MESSAGE` | `auto sync: {timestamp}` | Commit message template |
| `GIT_SYNC_DRY_RUN` | `0` | Set to `1` for preview mode |
