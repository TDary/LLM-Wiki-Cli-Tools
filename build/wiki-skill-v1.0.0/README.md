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

This auto-detects your platform, picks the right binary, copies it to `~/.local/bin` (or `/usr/local/bin` on macOS), and adds it to PATH.

For the local-only variant (no Git dependency):

```bash
./install.sh --local
```

To also install the skill into a Claude Code project:

```bash
./install.sh --skill ~/my-project
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

`platform-adapters/` contains agent instructions for other AI coding tools (Cursor, Windsurf, Copilot, OpenClaw). Copy or reference `AGENTS.md` as your tool requires.

## License

MIT
