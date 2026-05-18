---
name: wiki
description: 创建、同步和管理 LLM 知识库 — 结构化目录、交叉引用、Git 版本控制
---

# Wiki Skill

Native skill for managing LLM-oriented knowledge bases. Operates entirely through Claude Code — no external binary required.

## Mode Detection

Always read `SCHEMA.md` first when entering an existing wiki. Check the **Git 同步** field:

| Git 同步 | Mode | Sync behavior |
|----------|------|---------------|
| `启用` | Git | `git add/commit/push` after changes |
| `禁用（纯本地模式）` | Local | Just write files, no git |

## /wiki init

```
/wiki init [path] [domain] [--no-git] [--force] [--name NAME]
```

Initialize a new wiki. If `path` is omitted, defaults to `~/wiki`. If `domain` is omitted, defaults to `"Wiki 知识库"`.

### Step-by-step

1. If path not given, default to `~/wiki`
2. **Check if SCHEMA.md already exists** — if yes and `--force` not set, report "detected existing wiki" and exit (don't overwrite)
3. If `--name` not given, use `filepath.Base(path)`. If domain not given, default to `"Wiki 知识库"`
4. Create these directories:
   ```
   raw/  entities/  concepts/  relations/  queries/  drafts/
   ```
4. Write **SCHEMA.md** — use the template below, filling in name, domain, git mode, and current date
5. Write **README.md** — use the template below
6. Write **log.md** — initial entry with current date
7. If NOT `--no-git`:
   - Check if git is available (`git --version`)
   - `git init`
   - Write `.gitignore` and `.gitattributes`
   - Create `.gitkeep` in each empty subdirectory
   - `git add .` then `git commit -m "init: wiki skeleton"`
8. If `--no-git` or git not available → SCHEMA.md shows `禁用（纯本地模式）`, no git files created
9. Print summary: path, domain, directory count, next steps

### Templates

**SCHEMA.md:**
```markdown
# SCHEMA — {name}

> 知识库领域配置 · 自动生成的索引和关系

## 基本信息

| 属性 | 值 |
|------|-----|
| **名称** | {name} |
| **领域** | {domain} |
| **Git 同步** | {启用 / 禁用（纯本地模式）} |
| **创建时间** | {YYYY-MM-DD HH:MM:SS} |
| **初始化工具** | wiki-tools |

## 目录说明

| 目录 | 用途 |
|------|------|
| `raw/` | 原始资料、外部引用、数据文件 |
| `entities/` | 实体页面（人、项目、工具等） |
| `concepts/` | 概念、术语、方法论 |
| `relations/` | 关系描述、交叉引用 |
| `queries/` | 查询模板、搜索索引 |
| `drafts/` | 草稿、临时笔记 |

## 标签体系

<!-- 可自定义标签，用于分类和检索 -->
\`\`\`yaml
tags:
  - type: tech
    label: 技术
  - type: process
    label: 流程
  - type: reference
    label: 参考
\`\`\`

## 关系类型

<!-- 可自定义实体间关系 -->
\`\`\`yaml
relations:
  - depends_on: 依赖
  - references: 引用
  - implements: 实现
  - owned_by: 归属
\`\`\`
```

**README.md:**
```markdown
# {name}

> {domain}

## 快速导航

- [SCHEMA](./SCHEMA.md) — 知识库配置与目录说明
- [原始资料](./raw/) — 外部引用与数据文件
- [实体](./entities/) — 人、项目、工具等
- [概念](./concepts/) — 术语与方法论
- [关系](./relations/) — 交叉引用
- [查询](./queries/) — 搜索索引
- [草稿](./drafts/) — 临时笔记

## 更新日志

参见 [log.md](./log.md)
```

**.gitignore:**
```gitignore
# LLM Wiki — Gitignore
.DS_Store
Thumbs.db
*.swp
*.swo
*~
.vscode/
.idea/
*.tmp
*.bak
*.log
__pycache__/
*.pyc
.venv/
node_modules/
```

**.gitattributes:**
```
# LLM Wiki — Gitattributes
*.md text eol=lf
*.sh text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
```

## /wiki sync

```
/wiki sync [path]
```

Auto-detect mode from `SCHEMA.md` and sync.

### Git mode

1. `git status --porcelain` — if clean, nothing to do
2. `git add .`
3. `git commit -m "auto sync: {timestamp}"` (use `GIT_SYNC_NAME`/`GIT_SYNC_EMAIL` env vars if set; default to `AI Assistant <ai@local>`)
4. `git pull --rebase origin {branch}`
5. `git push origin {branch}`
6. Append entry to `log.md`

If pull/push fails due to no remote configured, skip push and notify user.

### Local mode

Confirm all files on disk are consistent. Nothing to sync — just remind user their files are the sole source of truth.

### Env vars (git mode)

| Variable | Default | Purpose |
|----------|---------|---------|
| `GIT_SYNC_NAME` | `AI Assistant` | Committer name |
| `GIT_SYNC_EMAIL` | `ai@local` | Committer email |
| `GIT_SYNC_BRANCH` | current branch | Target branch |
| `GIT_SYNC_MESSAGE` | `auto sync: {timestamp}` | Commit message |
| `GIT_SYNC_DRY_RUN` | `0` | Set to `1` to preview only |
| `GIT_SYNC_FORCE_PUSH` | `0` | Set to `1` for force-with-lease |

## /wiki bootstrap

```
/wiki bootstrap <remote-url> [path] [--domain DOMAIN]
```

One-command setup from a remote Git repository.

1. If path not given, derive from repo name: `~/<repo-name>`
2. `git clone <url> <path>`
3. If `SCHEMA.md` missing, run init steps (but skip git init — already a repo)
4. `git config user.name "AI Assistant"` (if not set)
5. `git config user.email "ai@local"` (if not set)
6. Run sync once

If repository doesn't exist (404), offer to init a new local wiki at that path instead.

## Conventions (apply when reading/writing wiki pages)

1. **File names**: lowercase, hyphens for spaces (`transformer-architecture.md`)
2. **Cross-reference**: use `[[wikilinks]]` to link between pages
3. **Minimum links**: every new page must link to at least 2 existing pages
4. **Raw is immutable**: never modify files in `raw/` — corrections go in wiki pages
5. **Always log**: append to `log.md` after every action (ingest, update, query)
6. **Read first**: before writing, check `SCHEMA.md`, `README.md`, and recent `log.md` entries
7. **Git mode**: run `/wiki sync` after modifications
8. **Local mode**: skip all git operations — files are the sole source of truth
