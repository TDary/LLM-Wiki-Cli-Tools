---
name: wiki
version: 1.2.1
description: 创建、查询和管理本地知识库，纯文件模式，零依赖
---

# Local Wiki Skill v1.2.1

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
├── platform-adapters/
│   └── AGENTS.md      # Copilot / Cursor / Windsurf / OpenClaw instructions
└── scripts/
    ├── wiki.py         # CLI entry point — thin dispatcher
    └── wiki_core/      # Core package
        ├── __init__.py # Constants and version
        ├── helpers.py  # Shared utilities
        ├── templates.py # Template generators
        ├── cmd_init.py # init, sync, bootstrap, install
        ├── cmd_query.py # list, index, search, backlinks, tags, stats
        ├── cmd_health.py # health, orphans, trace, fix, rename
        └── cmd_ingest.py # ingest (URL, file, template)
```

`python scripts/wiki.py install <project>` copies all files to the right places for each tool.

## Agent 触发规则（强制）

> 以下规则不可跳过。Agent 看到触发条件时，必须执行对应动作。

| 触发条件 | 强制动作 |
|---------|---------|
| `ingest --url` 或 `ingest --file` 执行成功 | 立即读取 raw/ 中的源文件，执行知识提取（见"Full Ingest Workflow"） |
| `ingest --manifest` 批量执行成功 | 对每个成功摄入的源文件，逐一执行知识提取 |
| `health` 检查发现断链 | 立即运行 `fix --apply` 修复 |
| `health` 检查发现孤立文档 | 为每个孤立文档建立至少 1 条 `[[wikilink]]` 关联 |
| `search` 返回结果且用户问题需要综合分析 | 读取匹配文档全文，综合回答后判断是否回写 |
| `rename` 执行成功 | 验证所有 wikilinks 已更新，检查 index.md 是否同步，更新 log.md |
| `archive` 执行成功 | 验证 index.md 中已移除该页面，检查是否有上下文引用需要更新（如 query 页面），更新 log.md |
| `fix --apply` 执行成功 | 向用户报告修复详情（哪些链接被改了），验证修复结果，更新 log.md |
| `search` 查询后回写新页面 | 必须遵循 New page rule（frontmatter + ≥2 wikilinks + log + index） |

**违反以上任何一条 = 任务未完成。**

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
| `python scripts/wiki.py archive <page> [path]` | Archive document to `_archive/` directory |
| `python scripts/wiki.py tags [path]` | List all tags with counts and documents |
| `python scripts/wiki.py stats [path]` | Knowledge base statistics overview |
| `python scripts/wiki.py ingest [path]` | Ingest external source (URL, file, or template) |

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

Run a comprehensive health check on the wiki. Two categories of checks:

**结构检查 (Structural):**
- **Orphan documents** — no inbound `[[wikilinks]]`
- **Broken links** — `[[wikilinks]]` pointing to non-existent pages
- **Untagged documents** — missing frontmatter `tags`
- **Low-link documents** — fewer than 2 outbound `[[wikilinks]]`
- **Empty documents** — content under 50 bytes (stub/placeholder pages)
- **Self-referential links** — `[[wikilinks]]` pointing to the document itself

**内容质量 (Content Quality):**
- **Frontmatter 校验** — 必填字段（title/created/updated/type/tags/sources）、type 有效性、日期格式、标签是否在 SCHEMA.md 体系中
- **Index 完整性** — 检查所有 wiki 页面是否出现在 index.md 中
- **过期内容检测** — 找出超过 90 天未更新的页面
- **日志轮转** — 检查 log.md 是否超过 500 条记录
- **矛盾检测** — 找出共享标签/实体的页面，标记为潜在矛盾供人工审查

**Frontmatter 必填字段：**

```yaml
---
title: Page Title        # 必填
created: 2026-05-22      # 必填，YYYY-MM-DD
updated: 2026-05-22      # 必填，YYYY-MM-DD
type: entity             # 必填，entity|concept|comparison|query|summary
tags: [tech, AI]         # 必填，必须在 SCHEMA.md 标签体系中
sources: [raw/source.md] # 必填，指向 raw/ 源文件
---
```

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

**健康检查后 Checklist（Agent 必须逐项确认）：**

```
☐ 已运行 health 获取完整检查报告
☐ 已逐项处理每个问题类别
☐ 断链 → 已运行 fix --apply
☐ 孤立文档 → 已添加 [[wikilink]] 关联
☐ 无标签页面 → 已补充 frontmatter tags
☐ 过期内容 → 已标记或更新
☐ 已更新 log.md
```

**跳过任何一项 = 任务未完成。**

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

**fix --apply 后验证 Checklist：**

```
☐ 已向用户报告修复详情（哪些链接被改了，从什么改为什么）
☐ 已确认无误修复（未引入新的断链）
☐ 已更新 log.md
```

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

**rename 后验证 Checklist：**

```
☐ 已确认所有 [[wikilinks]] 已从旧名更新为新名
☐ 已确认文档内 # heading 已更新
☐ 已确认文件已重命名
☐ 已确认 index.md（如有）已同步
☐ 已更新 log.md
```

## /wiki archive

```
/wiki archive <page> [path] [--apply] [--format table|json] [--pretty]
```

Archive a document to `_archive/` directory, preserving the original category structure.

**Actions (in order):**
1. Update all `[[wikilinks]]` in other documents → plain text + "（已归档）"
2. Remove the page from `index.md` (if present)
3. Move the file to `_archive/<category>/<filename>.md`
4. Log the archive action in `log.md`

**Options:**
- `--apply` — actually perform the archive (default is dry-run preview)
- `--format json` — output as JSON (with `--pretty` for indentation)

Default mode is dry-run: shows what would change without making modifications.

**Example:**
```bash
# Preview what will happen
python scripts/wiki.py archive transformer-architecture

# Execute the archive
python scripts/wiki.py archive transformer-architecture --apply
```

**Archive structure:**
```
wiki/
├── _archive/
│   ├── concepts/
│   │   └── old-page.md
│   ├── entities/
│   │   └── deprecated-entity.md
│   └── ...
├── concepts/
│   └── active-page.md
└── ...
```

**archive 后验证 Checklist：**

```
☐ 已确认所有引用该页面的 [[wikilinks]] 已更新为纯文本 + "（已归档）"
☐ 已确认 index.md 中已移除该页面
☐ 已确认文件已移至 _archive/ 目录
☐ 已检查是否有 query/relations 页面引用了归档内容，需要更新上下文
☐ 已更新 log.md
```

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

### Full Query Workflow (CLI + Agent)

**执行前 Checklist（Agent 必须逐项确认）：**

```
☐ 已调用 search/list/backlinks 定位相关页面
☐ 已读取匹配文档的全文
☐ 已综合多个来源给出完整答案
☐ 已在答案中用 [[wikilinks]] 引用来源
☐ 已判断答案是否有长期价值（是→回写，否→直接回答）
☐ 已更新 log.md（如有回写）
```

**跳过任何一项 = 任务未完成。**

The CLI provides **structural search** (keyword matching). The agent performs **semantic synthesis** (understanding, reasoning, filing):

```
用户: wiki 里关于 Transformer 和注意力机制有哪些内容？

┌─────────────────────────────────────────────────────────────┐
│ Step 1: CLI — 结构层（search / list / backlinks）            │
│   ✅ search "transformer" → 匹配的文档和行号                  │
│   ✅ search "attention" → 匹配的文档和行号                     │
│   ✅ backlinks transformer-architecture → 谁引用了这个页面      │
│   ✅ list --tags AI → 相关标签下的文档                         │
└─────────────────────────────────────────────────────────────┘
         ↓ CLI 输出 JSON（含匹配文档、行号、上下文）
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Agent — 语义层（大模型能力）                           │
│   1. 读取 CLI 返回的相关文档全文                               │
│   2. 理解用户问题的意图                                       │
│   3. 从多个文档中综合提取答案                                  │
│   4. 引用具体 wiki 页面作为来源                                │
│      "基于 [[transformer-architecture]] 和                    │
│       [[attention-mechanism]]，Transformer 的核心是..."       │
│   5. 判断答案是否有长期价值                                    │
│      → 有：创建 queries/ 或 comparisons/ 页面回写              │
│      → 无：直接回答，不写文件                                   │
│   6. 更新 log.md                                             │
└─────────────────────────────────────────────────────────────┘
```

**Agent 查询步骤：**

1. **定位相关页面** — 调用 `search` 搜索关键词，调用 `list --tags` 按标签过滤，调用 `backlinks` 找关联页面
2. **读取页面内容** — 读取匹配文档的全文，理解上下文
3. **综合回答** — 从多个来源中提取、整合、推理，形成完整答案
4. **引用来源** — 答文中用 `[[wikilinks]]` 引用 wiki 页面，可溯源
5. **回写有价值的内容** — 如果答案是深度分析、对比、或综合研究，创建新页面保存：
   - `queries/<topic>.md` — 查询结果、分析报告
   - `comparisons/<a>-vs-<b>.md` — 对比分析
   - 更新 `log.md` 记录查询和回写

**回写判断标准：**
| 情况 | 操作 |
|------|------|
| 简单事实查询（"X 是什么"） | 直接回答，不写文件 |
| 多文档综合分析 | 回写到 `queries/` |
| 对比类查询（"X 和 Y 的区别"） | 回写到 `relations/` |
| 深度研究（涉及 5+ 页面） | 回写到 `queries/`，附带完整引用 |

### Agent 查询示例

```
用户: RAG 和微调哪个更适合我们的场景？

Agent:
  1. search "RAG" → 找到 concepts/rag.md, queries/rag-performance.md
  2. search "fine-tuning" → 找到 concepts/fine-tuning.md
  3. list --tags optimization → 找到 concepts/model-optimization.md
  4. 读取这 4 个页面全文
  5. 综合分析，给出对比建议
  6. 回写: relations/rag-vs-fine-tuning.md（含对比表格和结论）
  7. 更新 log.md
```

## /wiki ingest

```
/wiki ingest [path] [--url URL | --file FILE | --template TITLE] [--category CAT] [--tags TAG1,TAG2] [--format table|json] [--pretty]
```

Ingest external sources into the wiki. Three modes:

**URL mode** (`--url`):
Fetch a URL, extract text content, save to `raw/` with source metadata header.

```bash
python scripts/wiki.py ingest . --url https://example.com/article
```

**File mode** (`--file`):
Copy a local file into `raw/` with normalized filename.

```bash
python scripts/wiki.py ingest . --file /path/to/document.md
```

**Template mode** (`--template`):
Create a wiki page template with proper frontmatter.

```bash
python scripts/wiki.py ingest . --template "AI Agent" --category concepts --tags AI,tech
```

**Bulk mode** (`--manifest`):
Process multiple sources from a JSON manifest file.

```bash
python scripts/wiki.py ingest . --manifest sources.json
```

Manifest format:
```json
{
  "sources": [
    {"type": "url", "url": "https://example.com/article1"},
    {"type": "url", "url": "https://example.com/article2"},
    {"type": "file", "path": "/path/to/document.md"},
    {"type": "template", "title": "My Page", "category": "concepts", "tags": ["AI"]}
  ]
}
```

**Options:**
- `--format json` — output as JSON
- `--pretty` — JSON indentation
- `--category` — category for template mode (default: drafts)
- `--tags` — comma-separated tags for template mode
- `--manifest` — JSON manifest file for bulk ingest

### Full Ingest Workflow (CLI + Agent)

**执行前 Checklist（Agent 必须逐项确认）：**

```
☐ CLI 命令已执行，源文件已保存到 raw/
☐ 已读取 raw/ 中源文件的完整内容
☐ 已识别实体（人/组织/产品/模型）
☐ 已识别概念（术语/方法论/技术原理）
☐ 已识别关系（对比/依赖/实现）
☐ 已检查现有 wiki 页面，避免重复
☐ 已为每个提取项创建 wiki 页面（含 frontmatter + ≥2 条 wikilinks）
☐ 已建立反向链接：检查已有页面是否需要添加指向新页面的 [[wikilink]]
☐ 已更新 index.md（如有）或重新生成 queries/index.json
☐ 已更新 log.md
```

**跳过任何一项 = 任务未完成。**

The `ingest` CLI command handles **structural operations** (save file, update log). After that, the agent performs **knowledge extraction and multi-layer content generation**:

```
用户: /wiki ingest . --url https://example.com/article

┌─────────────────────────────────────────────────────────────┐
│ Step 1: CLI — 结构层（wiki.py ingest）                       │
│   ✅ 抓取 URL 内容                                           │
│   ✅ 保存到 raw/example-article.md（带源信息头）               │
│   ✅ 提取关键词，建议相关页面                                   │
│   ✅ 更新 log.md                                             │
└─────────────────────────────────────────────────────────────┘
         ↓ CLI 输出 JSON（含 title, keywords, related_pages）
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Agent — 知识提取层（大模型能力）                       │
│   1. 读取 raw/example-article.md 全文                        │
│   2. 分析内容，提取：                                         │
│      - 实体（人、组织、产品、模型）                             │
│      - 概念（术语、方法论、技术原理）                           │
│      - 关系（依赖、对比、实现）                                │
│   3. 检查现有 wiki 页面，避免重复                              │
│   4. 为每个实体/概念创建 wiki 页面：                           │
│      - entities/openai.md                                    │
│      - entities/sam-altman.md                                │
│      - concepts/transformer-architecture.md                  │
│      - concepts/attention-mechanism.md                       │
│      - relations/transformer-vs-rnn.md                       │
│   5. 每个页面包含：                                          │
│      - YAML frontmatter（title, created, updated, type,      │
│        tags, sources 指向 raw/ 源文件）                       │
│      - 结构化内容（概述、要点、引用）                           │
│      - [[wikilinks]] 交叉引用（≥2 条出站链接）                │
│   6. 更新 log.md 记录所有创建/更新的页面                       │
└─────────────────────────────────────────────────────────────┘
```

**Agent 后处理步骤：**

1. **读取源文件** — 读 `raw/` 中刚保存的完整内容
2. **实体提取** — 识别文中提到的人、组织、产品、模型等，每个创建 `entities/<name>.md`
3. **概念提取** — 识别技术术语、方法论、原理，每个创建 `concepts/<name>.md`
4. **关系提取** — 识别对比、依赖、实现等关系，创建 `relations/<a>-vs-<b>.md`
5. **交叉引用** — 确保每个新页面有 ≥2 条 `[[wikilinks]]`，并检查已有页面是否需要反向链接
6. **更新索引** — 将新页面加入 `index.md`（如有）或生成 `queries/index.json`
7. **记录日志** — 在 `log.md` 中记录所有创建/更新操作

**一个源文件通常触发 5-15 个 wiki 页面的创建/更新** — 这是知识库的复利效应。

### Agent 调用示例

```
用户: 帮我把这篇论文的知识提取到 wiki 里
      https://arxiv.org/abs/2301.00001

Agent:
  1. 调用 CLI 保存源文件
     → python wiki.py ingest . --url https://arxiv.org/abs/2301.00001
  2. 读取 raw/arxiv-2301-00001.md
  3. 分析内容，识别出 3 个实体、2 个概念、1 个关系
  4. 创建 6 个 wiki 页面（带 frontmatter 和交叉引用）
  5. 检查已有页面，添加反向 [[wikilinks]]
  6. 更新 index.md（如有）
  7. 更新 log.md
  8. 汇报：创建了 entities/xxx.md, concepts/yyy.md 等
```

### Page Type Mapping

| 提取内容 | 目录 | type 字段 | 示例 |
|---------|------|----------|------|
| 人、组织、产品、模型 | `entities/` | `entity` | entities/openai.md |
| 术语、方法论、技术原理 | `concepts/` | `concept` | concepts/attention-mechanism.md |
| 对比、竞品分析 | `relations/` | `comparison` | relations/transformer-vs-rnn.md |
| 查询结果、分析报告 | `queries/` | `query` | queries/rag-vs-fine-tuning.md |
| 草稿、临时笔记 | `drafts/` | `summary` | drafts/todo-notes.md |

### Frontmatter 标准

每个自动生成的页面必须包含完整 frontmatter：

```yaml
---
title: Page Title
created: 2026-05-22
updated: 2026-05-22
type: entity | concept | comparison | query | summary
tags: [tech, AI, ...]
sources: [raw/example-article.md]
---
```

- `sources` 必须指向 `raw/` 中的源文件（溯源）
- `tags` 必须来自 SCHEMA.md 中定义的标签体系
- 每次更新页面时 `updated` 日期必须更新

## Conventions

When reading/writing wiki pages:

1. **File names**: lowercase, hyphens (`transformer-architecture.md`)
2. **Cross-reference**: use `[[wikilinks]]` between pages
3. **Minimum links**: every new page links to >= 2 existing pages
4. **Raw is immutable**: NEVER modify, rename, or delete files in `raw/`. Corrections and interpretations go in wiki pages under other directories.
5. **Always log**: append to `log.md` after every action
6. **Read first**: before writing, check `SCHEMA.md`, `README.md`, and recent `log.md`
7. **No skip rule**: Agent 必须完成 workflow 中的所有步骤。CLI 执行成功 ≠ 任务完成。知识提取、交叉引用、日志更新是强制步骤。
8. **New page rule**: 创建任何新 wiki 页面时，以下 4 项缺一不可：① 完整 frontmatter（title/created/updated/type/tags/sources）② ≥2 条 `[[wikilinks]]` 出站链接 ③ 更新 `log.md` ④ 更新 `index.md`（如有）

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
