# AGENTS.md — LLM Wiki Knowledge Base

> Platform-agnostic agent instructions.
> Works with: OpenClaw, Cursor, Windsurf, GitHub Copilot, and any agent that reads AGENTS.md.

## Installation

Copy this file to your project root. The location depends on your tool:

| Tool | Where to put this file |
|------|------------------------|
| **GitHub Copilot** | `<project>/AGENTS.md` or `.github/copilot-instructions.md` |
| **Cursor** | `<project>/AGENTS.md` or `.cursor/rules/wiki.mdc` |
| **Windsurf** | `<project>/AGENTS.md` |
| **OpenClaw** | `<project>/AGENTS.md` |
| **Claude Code** | Prefer the native skill: copy `skills/wiki.md` to `.claude/skills/`. For project rules: `<project>/CLAUDE.md` |

> **Claude Code users**: the native `/wiki` skill (`.claude/skills/wiki.md`) is the preferred entry point — it operates directly without the Go binary. The CLI tool below is for daemon mode and non-Claude environments.

## Quick Start

```bash
# One-command team wiki setup
wiki-tools bootstrap <REMOTE_URL> ~/team-wiki --domain "Team Knowledge Base"

# Manual sync
wiki-tools sync ~/team-wiki

# Init new wiki
wiki-tools init <path> "<domain>"

# Start periodic sync daemon
wiki-tools serve ~/team-wiki --interval 10
```

## Mode Detection

Check `SCHEMA.md` first. The **Git 同步** field in the info table tells you the wiki mode:

| Git 同步 | Mode | Behavior |
|-----------|------|----------|
| `启用` | Git mode | Run `wiki-tools sync` after changes |
| `禁用（纯本地模式）` | Local mode | Skip all Git operations; just read/write files directly |

## Key Rules

1. **Read before writing** — always check `SCHEMA.md`, `README.md`, and recent `log.md` first
2. **Auto-sync after changes** — if Git mode, run `wiki-tools sync <path>` after any modification. If local mode, skip.
3. **Cross-reference** — every new page must link to >=2 existing pages with `[[wikilinks]]`
4. **Log everything** — append to `log.md` after every action (ingest, update, query)
5. **Raw is immutable** — NEVER modify, rename, or delete files in `raw/`. This is a hard constraint. Corrections and interpretations go in wiki pages under other directories.

## Directory Layout

| Directory | Purpose |
|-----------|---------|
| `raw/` | Immutable source material |
| `entities/` | People, projects, tools, orgs |
| `concepts/` | Ideas, terms, methodologies |
| `relations/` | Cross-references between entities |
| `queries/` | Saved search results |
| `drafts/` | Work in progress |

## CLI Tool (platform-agnostic)

`wiki-tools` is a single static Go binary — no dependencies beyond git:

| Command | Purpose |
|---------|---------|
| `wiki-tools init <path> <domain>` | Initialize wiki directory structure |
| `wiki-tools sync <path>` | Auto-commit + push any Git repo |
| `wiki-tools bootstrap <url> [path]` | One-command clone + init + config + sync |
| `wiki-tools serve <path>` | Start periodic sync daemon (replaces cron) |
| `wiki-tools list [path] [--format json] [--category CAT] [--tags TAG1,TAG2] [--include-raw]` | List all documents (raw/ excluded by default) |
| `wiki-tools search <keyword> [path] [--format json] [--no-raw]` | Full-text search across documents |
| `wiki-tools backlinks <page> [path] [--format json]` | Find all pages linking to a target |
| `wiki-tools orphans [path] [--format json]` | Detect orphan documents with no inbound links |
| `wiki-tools health [path] [--format json]` | Full health check (orphans, broken links, tags, links, empty docs, self-links) |
| `wiki-tools trace <page> [path] [--format json]` | Trace upstream/downstream dependency chain |
| `wiki-tools fix [path] [--apply] [--format json]` | Auto-fix broken links and normalize naming (dry-run by default) |
| `wiki-tools index [path] [--output FILE]` | Generate structured JSON index for frontend |

Environment variables for `wiki-tools sync` (CLI flags take priority):

| Variable | Default | Purpose |
|----------|---------|---------|
| `GIT_SYNC_NAME` | `AI Assistant` | Committer name |
| `GIT_SYNC_EMAIL` | `ai@local` | Committer email |
| `GIT_SYNC_MESSAGE` | `auto sync: {timestamp}` | Commit message template |
| `GIT_SYNC_DRY_RUN` | `0` | Set to `1` for preview mode |
| `GIT_SYNC_BRANCH` | current branch | Target branch for push |
| `GIT_SYNC_FORCE_PUSH` | `0` | Set to `1` for force-with-lease on push failure |

## Download

Prebuilt binaries available in the `dist/` directory:

| Platform | Binary |
|----------|--------|
| Windows (x64) | `wiki-tools.exe` |
| Linux (x64) | `dist/wiki-tools-linux` |
| macOS Intel | `dist/wiki-tools-darwin-amd64` |
| macOS Apple Silicon | `dist/wiki-tools-darwin-arm64` |
