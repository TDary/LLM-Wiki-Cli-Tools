---
name: wiki
version: 1.1.1
description: 创建、查询和管理本地知识库，纯文件模式，零依赖
---

# Local Wiki Skill v1.1.1

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
| `python scripts/wiki.py search <keyword> [path]` | Full-text search across documents |
| `python scripts/wiki.py backlinks <page> [path]` | Find all pages linking to a target |
| `python scripts/wiki.py orphans [path]` | Detect orphan documents with no inbound links |
| `python scripts/wiki.py health [path]` | Run full health check on wiki |
| `python scripts/wiki.py trace <page> [path]` | Trace upstream/downstream dependency chain |
| `python scripts/wiki.py fix [path]` | Auto-fix broken links and normalize naming |
| `python scripts/wiki.py index [path]` | Generate JSON index for frontend |
| `python scripts/wiki.py rename <old> <new> [path]` | Rename document and update all wikilinks |
| `python scripts/wiki.py tags [path]` | List all tags with counts and documents |
| `python scripts/wiki.py stats [path]` | Knowledge base statistics overview |
| `python scripts/wiki.py wps-auth` | WPS OAuth authorization (first-time setup) |
| `python scripts/wiki.py import [path]` | Batch import WPS cloud documents |

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
/wiki list [path] [--format table|json] [--category CAT] [--tags TAG1,TAG2] [--include-raw] [--pretty]
```

List all knowledge documents in the wiki. Default: table format grouped by category.

**Options:**
- `--format json` — output as JSON (with `--pretty` for indentation)
- `--category concepts` — filter to a single directory
- `--tags AI,tech` — filter by tags (comma-separated, matches any)
- `--include-raw` — include `raw/` directory (excluded by default, as raw files are immutable)

Output includes: title, file path, category, size, last modified time, tags, wiki-link count.

## /wiki search

```
/wiki search <keyword> [path] [--format table|json] [--no-raw] [--regex] [--pretty]
```

Full-text search across all wiki documents. Case-insensitive substring matching on both titles and body content.

**Options:**
- `--format json` — output as JSON (with `--pretty` for indentation)
- `--no-raw` — exclude `raw/` directory from search results
- `--regex` — treat keyword as a regular expression pattern

Output includes: document title, file path, matching lines with line numbers.

## /wiki backlinks

```
/wiki backlinks <page> [path] [--format table|json] [--pretty]
```

Find all documents that link to a given page via `[[wikilinks]]`.

**Options:**
- `<page>` — target page name (e.g., `transformer-architecture` or `transformer-architecture.md`)
- `--format json` — output as JSON (with `--pretty` for indentation)

Output includes: source document title, file path, line number, and line content.

## /wiki orphans

```
/wiki orphans [path] [--format table|json] [--pretty]
```

Detect orphan documents — files that have no inbound `[[wikilinks]]` from other documents. Excludes system files (`SCHEMA.md`, `README.md`, `log.md`).

**Options:**
- `--format json` — output as JSON (with `--pretty` for indentation)

Output includes: orphan document list with suggestions for linking them into the wiki graph.

## /wiki health

```
/wiki health [path] [--format table|json] [--pretty]
```

Run a comprehensive health check on the wiki. Checks for:

- **Orphan documents** — no inbound `[[wikilinks]]`
- **Broken links** — `[[wikilinks]]` pointing to non-existent pages
- **Untagged documents** — missing frontmatter `tags`
- **Low-link documents** — fewer than 2 outbound `[[wikilinks]]`
- **Empty documents** — content under 50 bytes (stub/placeholder pages)
- **Self-referential links** — `[[wikilinks]]` pointing to the document itself
- **Custom checks** — user-defined external commands from SCHEMA.md

**Configurable weights:** Add a `## 健康检查` section with a YAML block to SCHEMA.md:

```yaml
weights:
  orphan: 3
  broken_link: 5
  no_tag: 1
  low_link: 2
  empty_doc: 2
  self_link: 1
```

**Custom external checks:** Add a `## 自定义检查` section with a YAML block:

```yaml
checks:
  - name: 链接格式
    command: "grep -rn '\\[\\[.*\\]\\' --include='*.md' | grep -v 'entities\\|concepts'"
    description: 检查链接格式是否正确
    weight: 1
```

Each custom check runs with a 5-second timeout. stdout lines become issue items.

Output includes a health score (0-100) and actionable suggestions.

## /wiki fix

```
/wiki fix [path] [--apply] [--interactive|-i] [--format table|json] [--pretty]
```

Structural self-healing: detect and auto-fix broken wikilinks and naming inconsistencies.

**Checks:**
- **Broken links** — `[[wikilink]]` pointing to non-existent pages, auto-suggest closest match
- **Naming normalization** — underscores → hyphens in wikilinks (e.g., `[[unity_ugui]]` → `[[unity-ugui]]`)

**Options:**
- `--apply` — actually apply fixes (default is dry-run preview)
- `--interactive`, `-i` — confirm each fix individually (y/n/s to skip remaining by type)
- `--format json` — output as JSON (with `--pretty` for indentation)

Default mode is dry-run: shows what would be fixed without making changes.

## /wiki trace

```
/wiki trace <page> [path] [--format table|json] [--pretty]
```

Trace the full upstream and downstream dependency chain of a document via `[[wikilinks]]`.

- **Upstream** — what this page references (directly and transitively)
- **Downstream** — what pages reference this page (directly and transitively)

Supports detecting circular references (visited nodes are skipped). Max depth: 10 levels.

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

## /wiki rename

```
/wiki rename <old-name> <new-name> [path] [--apply] [--format table|json] [--pretty]
```

Rename a document and globally update all `[[wikilink]]` references pointing to it.

**Actions (in order):**
1. Update all `[[wikilinks]]` in other documents that reference the old name
2. Update the `# heading` inside the document itself
3. Rename the file

**Options:**
- `--apply` — actually perform the rename (default is dry-run preview)
- `--format json` — output as JSON (with `--pretty` for indentation)

Default mode is dry-run: shows what would change without making modifications.

## /wiki tags

```
/wiki tags [path] [--format table|json] [--sort count|name] [--pretty]
```

List all tags in the wiki with usage counts and associated documents.

**Options:**
- `--sort count` — sort by usage count, descending (default)
- `--sort name` — sort alphabetically by tag name
- `--format json` — output as JSON (with `--pretty` for indentation)

## /wiki stats

```
/wiki stats [path] [--format table|json] [--pretty]
```

Knowledge base overview statistics.

**Output includes:**
- Document count by category
- Tag statistics (unique tags, total uses)
- Link density (links per document)
- Orphan document count and percentage
- Total file size
- Latest modification timestamp

## /wiki wps-auth

```
/wiki wps-auth
```

One-time WPS OAuth authorization. Opens a browser for the user to authorize the app, then saves the token locally for subsequent API calls.

**Prerequisites:**
Create `scripts/wps_config.json` with your WPS Open Platform app credentials:

```json
{
  "app_id": "your_app_id",
  "app_secret": "your_app_secret",
  "redirect_uri": "http://localhost:8899/callback"
}
```

**How it works:**
1. Reads app credentials from `wps_config.json`
2. Opens browser to WPS authorization page
3. Starts a local HTTP server to receive the callback
4. Exchanges the authorization code for an access token
5. Saves token to `wps_token.json` (auto-refreshes when expired)

## /wiki import

```
/wiki import [path] [--wps-folder URL] [--wps-file URL] [--manifest FILE] [--stdin] [OPTIONS]
```

Batch import WPS cloud documents into the wiki. Supports three input sources:

**Input sources (pick one):**
- `--wps-folder <url>` — Import all files from a WPS folder (auto-traverses subfolders)
- `--wps-file <url>` — Import a single WPS cloud document
- `--manifest <file>` — Import from a JSON manifest file
- `--stdin` — Read JSON manifest from stdin

**Options:**
- `--category CAT` — Force classification (overrides auto-classification)
- `--tags TAG1,TAG2` — Additional tags
- `--dry-run` — Preview mode (no files written)
- `--force` / `-y` — Skip confirmation, import directly
- `--skip-existing` — Skip files already imported (tracked by wps_file_id in SCHEMA.md)
- `--format table|json` — Output format
- `--pretty` — JSON indentation

**Import flow:**
1. Parse input source (folder URL / file URL / JSON manifest)
2. For folders: traverse all files, show scope summary (file count, type breakdown)
3. Wait for user confirmation (unless `--force` or `-y`)
4. For each file:
   - Skip if already indexed (`--skip-existing`)
   - Extract content via WPS API (`markdown` format)
   - Auto-classify: `raw/` (default), `entities/`, `concepts/`, `relations/`
   - Auto-generate tags from title and path keywords
   - Generate normalized filename (lowercase, hyphens)
   - Write wiki page with frontmatter (title, tags, source URL, wps_file_id)
5. Update SCHEMA.md `## 已索引文件` section for incremental tracking
6. Append import log to `log.md`

**Auto-classification rules:**

| Title/Path keywords | Category |
|---------------------|----------|
| 会议, 周报, 日报, 纪要 | `raw/` |
| 团队, 人员, 成员 | `entities/` |
| 概念, 方案, 设计, spec, 架构 | `concepts/` |
| Other | `raw/` (default) |

**JSON manifest format:**

```json
{
  "documents": [
    {
      "id": "wps_file_id",
      "title": "Document Title",
      "content": "Full text content (markdown)",
      "url": "https://www.kdocs.cn/xxx",
      "author": "Author Name",
      "date": "2025-01-15",
      "type": "doc|sheet|ppt|pdf",
      "tags": ["AI", "design"],
      "category": "",
      "path_hint": "/Team Docs/AI Project/"
    }
  ]
}
```

Only `id` and `title` are required. `content` can be empty (creates a stub page).

**Incremental updates:**
Imported files are tracked in SCHEMA.md under `## 已索引文件` with their `wps_file_id`. Use `--skip-existing` to only import new files on subsequent runs.

## Conventions

When reading/writing wiki pages:

1. **File names**: lowercase, hyphens (`transformer-architecture.md`)
2. **Cross-reference**: use `[[wikilinks]]` between pages
3. **Minimum links**: every new page links to >= 2 existing pages
4. **Raw is immutable**: NEVER modify, rename, or delete files in `raw/`. Corrections and interpretations go in wiki pages under other directories.
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
