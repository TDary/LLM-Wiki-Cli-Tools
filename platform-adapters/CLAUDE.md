# Claude Code Wiki Integration

When working with this wiki, use the following CLI tools (installed at `~/.local/bin/`).

## One-Command Setup

```bash
wiki-bootstrap <REMOTE_URL> ~/team-wiki --domain "团队知识库"
```

## Daily Operations

**Auto-sync to Git:**
```bash
git-auto-sync ~/team-wiki
```

**Initialize a new wiki:**
```bash
wiki-init <path> "<domain description>"
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

## Conventions

- File names: lowercase, hyphens (e.g., `transformer-architecture.md`)
- Cross-reference with `[[wikilinks]]`
- Every page must link to at least 2 other pages
- Update `log.md` after every action
- Use `git-auto-sync` after modifications — never run raw `git push` directly

## Git Auto-Sync

The `git-auto-sync` script handles all edge cases (no changes, push conflicts, empty repos).
Customize via environment variables:

```bash
GIT_SYNC_NAME="Claude" GIT_SYNC_EMAIL="claude@local" git-auto-sync ~/team-wiki
```
