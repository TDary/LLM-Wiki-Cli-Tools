# Wiki Skill — LLM Knowledge Base Toolkit

AI-native wiki management with structured directories, cross-references, and optional Git versioning.

## Quick Start

### One-command install

```bash
# Linux / macOS
./install.sh

# Windows (PowerShell)
.\install.ps1
```

Auto-detects platform, installs to `~/.local/bin` (macOS: `/usr/local/bin`), adds to PATH.

**Defaults to local-only variant** (init + bootstrap, zero dependencies, ~2.7MB). For the full variant with Git support:

```bash
./install.sh --full
```

Install everything at once — binary, skill, and AGENTS.md:

```bash
./install.sh --skill ~/my-project --agents ~/my-project
```

### Manual: Native Skill (zero dependencies)

Copy `skills/wiki.md` into your Claude Code project:

```bash
mkdir -p .claude/skills && cp skills/wiki.md .claude/skills/
```

Then invoke directly:

```
/wiki init ~/my-wiki "My Knowledge Domain"
/wiki sync ~/my-wiki
/wiki bootstrap git@github.com:user/repo.git ~/my-wiki
```

Operates entirely through Claude Code — no binary download required.

### Manual: Go CLI Binary

Pick your platform binary from `dist/`, rename to `wiki-tools`, add to PATH:

| Platform | Binary |
|----------|--------|
| Linux x64 | `wiki-tools-linux-amd64` |
| Linux ARM64 | `wiki-tools-linux-arm64` |
| macOS Intel | `wiki-tools-darwin-amd64` |
| macOS Apple Silicon | `wiki-tools-darwin-arm64` |
| Windows x64 | `wiki-tools-windows-amd64.exe` |

Each platform has two variants:
- `wiki-tools-*` — full mode (init, sync, bootstrap, serve) with Git support, ~3.3MB
- `wiki-tools-local-*` — local-only mode (init, bootstrap), zero Git dependency, ~2.7MB

### CLI Quick Reference

```bash
wiki-tools init <PATH> "<DOMAIN>"              # New wiki
wiki-tools bootstrap <URL> <PATH>              # Clone + init
wiki-tools sync <PATH>                         # Auto-detect mode and sync
wiki-tools serve <PATH> --interval 10          # Periodic sync daemon
```

### Daemon Mode (binary only, not available in skill)

```bash
wiki-tools serve ~/team-wiki --interval 10
```

## Directory Structure

```
wiki-root/
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

## Platform Adapters

`platform-adapters/` contains agent instructions for other AI coding tools. Each tool reads from a different location:

| Tool | Copy to |
|------|---------|
| **Claude Code** | `.claude/skills/wiki.md` (use `skills/wiki.md` — the native skill) |
| **Claude Code** (project rules) | `CLAUDE.md` in project root |
| **GitHub Copilot** | `AGENTS.md` in project root, or `.github/copilot-instructions.md` |
| **Cursor** | `AGENTS.md` in project root, or `.cursor/rules/wiki.mdc` |
| **Windsurf** | `AGENTS.md` in project root |
| **OpenClaw** | `AGENTS.md` in project root |

Quick copy:

```bash
# Claude Code native skill
cp skills/wiki.md ~/my-project/.claude/skills/

# Most other tools (Copilot, Cursor, Windsurf, OpenClaw)
cp platform-adapters/AGENTS.md ~/my-project/

# Claude Code project rules
cp platform-adapters/CLAUDE.md ~/my-project/
```

## License

MIT
