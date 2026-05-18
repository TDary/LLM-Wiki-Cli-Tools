# Claude Code Wiki Integration

When working with this wiki, use `wiki-tools` (Go static binary, place it anywhere in PATH).

## One-Command Setup

```bash
wiki-tools bootstrap <REMOTE_URL> ~/team-wiki --domain "团队知识库"
```

## Daily Operations

**Auto-sync to Git:**
```bash
wiki-tools sync ~/team-wiki
```

**Preview before sync:**
```bash
wiki-tools sync ~/team-wiki --dry-run
```

**With rebase:**
```bash
wiki-tools sync ~/team-wiki --rebase
```

**Initialize a new wiki:**
```bash
wiki-tools init <path> "<domain description>"
```

**Start periodic sync daemon (replaces cron):**
```bash
wiki-tools serve ~/team-wiki --interval 10
```

**Search the wiki:**
```bash
grep -r "search term" ~/team-wiki/entities/ ~/team-wiki/concepts/ --include="*.md"
```

## Wiki Structure

```
team-wiki/
├── SCHEMA.md        # Conventions, domain config
├── README.md        # Navigation index
├── log.md           # Chronological action log
├── raw/             # Immutable source material
├── entities/        # Entity pages (people, projects, tools)
├── concepts/        # Concept/topic pages
├── relations/       # Cross-references
├── queries/         # Filed query results
└── drafts/          # Work in progress
```

## Mode Detection

Check `SCHEMA.md` first. The "Git 同步" field in the info table tells you what to do:

| Git 同步 | Mode | Behavior |
|-----------|------|----------|
| `启用` | Git mode | `wiki-tools sync` after changes |
| `禁用（纯本地模式）` | Local mode | Skip sync entirely — just read/write files directly |

## Conventions

- File names: lowercase, hyphens (e.g., `transformer-architecture.md`)
- Cross-reference with `[[wikilinks]]`
- Every page must link to at least 2 other pages
- Update `log.md` after every action
- Git mode: use `wiki-tools sync` after modifications — never run raw `git push` directly
- Local mode: skip all Git operations; files are the sole source of truth

## Environment Variables

`wiki-tools sync` respects the following env vars (CLI flags take priority):

| Variable | Purpose |
|----------|---------|
| `GIT_SYNC_NAME` | Committer name |
| `GIT_SYNC_EMAIL` | Committer email |
| `GIT_SYNC_BRANCH` | Target branch |
| `GIT_SYNC_MESSAGE` | Commit message template |
| `GIT_SYNC_DRY_RUN` | Set to `1` for preview |
| `GIT_SYNC_FORCE_PUSH` | Set to `1` for force-with-lease |
