---
name: wiki
version: 1.0.3
description: 创建、查询和管理本地知识库，纯文件模式，零依赖
---

# Local Wiki Skill v0.1.0

Zero-dependency local wiki management for Claude Code. Pure Python, pure files — no Git, no network, just Python 3.9+.

## Installation

```bash
python scripts/wiki.py install ~/my-project
```

Copies this `SKILL.md` and `wiki.py` into your project's `.claude/` directory.

## What's Inside

```
local-wiki-skill/
├── SKILL.md           # Claude Code skill definition (this file)
├── AGENTS.md           # Copilot / Cursor / Windsurf / OpenClaw instructions
└── scripts/
    └── wiki.py        # Python CLI — all commands in one file
```

`python scripts/wiki.py install <project>` copies all three files to the right places for each tool.

## CLI Commands

| Command | What it does |
|---------|-------------|
| `python scripts/wiki.py install <project>` | Install skill into a project |
| `python scripts/wiki.py init [path] [domain]` | Create directory structure + templates |
| `python scripts/wiki.py sync [path]` | Confirm local-only status |
| `python scripts/wiki.py bootstrap <path>` | Bootstrap at a given path |
| `python scripts/wiki.py list [path]` | List all documents (table or JSON) |
| `python scripts/wiki.py index [path]` | Generate JSON index for frontend |

## Quick Check

Before doing anything in a wiki directory, check if `SCHEMA.md` exists. If it does, you're in a wiki. The **Git 同步** field will always say `禁用（纯本地模式）` — files are the sole source of truth.

## /wiki init

```
/wiki init [path] [domain] [--force] [--name NAME]
```

Create a new local wiki. Defaults: `path = ~/wiki`, `domain = "Wiki 知识库"`.

**How it works:** call `python scripts/wiki.py init [args]` and follow the output.

Steps the script performs:
1. Default path to `~/wiki`, domain to `"Wiki 知识库"`
2. If `SCHEMA.md` already exists and no `--force`, report and exit
3. Create 6 subdirectories: `raw/ entities/ concepts/ relations/ queries/ drafts/`
4. Write `SCHEMA.md`, `README.md`, `log.md`
5. No `.gitignore`, `.gitattributes`, or `.gitkeep` — purely local

## /wiki sync

```
/wiki sync [path]
```

Local mode — no sync needed. The script confirms files are the sole source of truth.

## /wiki bootstrap

```
/wiki bootstrap <path> [--domain DOMAIN] [--force]
```

Bootstrap a wiki at an existing or new path. Equivalent to `init` with the given path.

## /wiki list

```
/wiki list [path] [--format table|json] [--category CAT] [--pretty]
```

List all knowledge documents in the wiki. Default: table format grouped by category.

**Options:**
- `--format json` — output as JSON (with `--pretty` for indentation)
- `--category concepts` — filter to a single directory

Output includes: title, file path, category, size, last modified time, tags, wiki-link count.

## /wiki index

```
/wiki index [path] [--output index.json] [--pretty]
```

Generate a structured JSON index for frontend consumption.

Output (default `queries/index.json`):
```json
{
  "wiki": {"name": "...", "domain": "...", "created_at": "..."},
  "generated_at": "2026-05-18 14:30:00",
  "total_documents": 12,
  "categories": [
    {
      "category": "concepts",
      "category_label": "概念",
      "count": 5,
      "documents": [...]
    }
  ],
  "tags": ["AI", "tech"]
}
```

## Conventions

When reading/writing wiki pages:

1. **File names**: lowercase, hyphens (`transformer-architecture.md`)
2. **Cross-reference**: use `[[wikilinks]]` between pages
3. **Minimum links**: every new page links to >= 2 existing pages
4. **Raw is immutable**: never modify files in `raw/` — corrections go in wiki pages
5. **Always log**: append to `log.md` after every action
6. **Read first**: before writing, check `SCHEMA.md`, `README.md`, and recent `log.md`

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
