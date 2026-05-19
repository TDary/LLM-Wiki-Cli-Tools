# AGENTS.md — Local Wiki Knowledge Base

> Platform-agnostic agent instructions for local wiki management.  
> Works with: OpenClaw, Cursor, Windsurf, GitHub Copilot, and any agent that reads AGENTS.md.

## Installation

| Tool | Where to put this file |
|------|------------------------|
| **Claude Code** | `.claude/skills/wiki.md` (use `SKILL.md`) |
| **GitHub Copilot** | `AGENTS.md` in project root, or `.github/copilot-instructions.md` |
| **Cursor** | `AGENTS.md` in project root, or `.cursor/rules/wiki.mdc` |
| **Windsurf** | `AGENTS.md` in project root |
| **OpenClaw** | `AGENTS.md` in project root |

## Quick Start

All wiki operations go through `scripts/wiki.py` (Python 3.9+, zero dependencies):

```bash
# Install skill into a project
python scripts/wiki.py install <project-path>

# Create a new wiki
python scripts/wiki.py init [path] [domain]

# Sync (local mode — always a no-op, files are truth)
python scripts/wiki.py sync [path]

# Bootstrap at a path
python scripts/wiki.py bootstrap <path> --domain "My Domain"
```

## Mode

This is **pure local mode**. There is no Git, no network, no sync. Files are the sole source of truth. The `SCHEMA.md` in every wiki will say `Git 同步 | 禁用（纯本地模式）`.

## Key Rules

1. **Read before writing** — always check `SCHEMA.md`, `README.md`, and recent `log.md` first
2. **Cross-reference** — every new page must link to >=2 existing pages with `[[wikilinks]]`
3. **Log everything** — append to `log.md` after every action (ingest, update, query)
4. **Raw is immutable** — NEVER modify, rename, or delete files in `raw/`. This is a hard constraint. Corrections and interpretations go in wiki pages under other directories.
5. **No sync needed** — files are the sole source of truth

## Directory Layout

| Directory | Purpose |
|-----------|---------|
| `raw/` | Immutable source material |
| `entities/` | People, projects, tools, orgs |
| `concepts/` | Ideas, terms, methodologies |
| `relations/` | Cross-references between entities |
| `queries/` | Saved search results |
| `drafts/` | Work in progress |

## Commands Reference

| Command | Purpose |
|---------|---------|
| `python scripts/wiki.py init [path] [domain]` | Initialize wiki directory structure (default: ~/wiki) |
| `python scripts/wiki.py sync [path]` | Confirm local-only status |
| `python scripts/wiki.py bootstrap <path>` | Bootstrap wiki at a given path |
| `python scripts/wiki.py install <project>` | Install skill into a project |
| `python scripts/wiki.py list [path] [--format json] [--category CAT] [--tags TAG1,TAG2] [--include-raw]` | List all documents (raw/ excluded by default) |
| `python scripts/wiki.py search <keyword> [path] [--format json] [--no-raw]` | Full-text search across documents |
| `python scripts/wiki.py backlinks <page> [path] [--format json]` | Find all pages linking to a target |
| `python scripts/wiki.py orphans [path] [--format json]` | Detect orphan documents with no inbound links |
| `python scripts/wiki.py health [path] [--format json]` | Full health check (orphans, broken links, tags, links) |
| `python scripts/wiki.py trace <page> [path] [--format json]` | Trace upstream/downstream dependency chain |
| `python scripts/wiki.py fix [path] [--apply] [--format json]` | Auto-fix broken links and normalize naming (dry-run by default) |
| `python scripts/wiki.py index [path] [--output FILE]` | Generate structured JSON index for frontend |

## Wiki Structure

```
wiki/
├── SCHEMA.md        # Domain config and conventions
├── README.md        # Navigation index
├── log.md           # Action log
├── raw/             # Immutable source material
├── entities/        # People, projects, tools
├── concepts/        # Terms, methodologies
├── relations/       # Cross-references
├── queries/         # Search indexes
└── drafts/          # Work in progress
```
