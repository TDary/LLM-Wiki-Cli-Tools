#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
BIN_NAME="wiki-tools"
FULL=false
TARGET_DIR=""
SKILL_TARGET=""
AGENTS_TARGET=""

usage() {
    echo "Usage: ./install.sh [--full] [--dir PATH] [--skill PROJECT_PATH] [--agents PROJECT_PATH]"
    echo ""
    echo "  --full          Install the full variant (init, sync, bootstrap, serve — requires Git)"
    echo "  --dir PATH      Install binary to PATH (default: ~/.local/bin, macOS: /usr/local/bin)"
    echo "  --skill PATH    Also copy the skill file to project/.claude/skills/"
    echo "  --agents PATH   Also copy AGENTS.md to project root (for Copilot/Cursor/Windsurf/OpenClaw)"
    echo ""
    echo "  Default: local-only variant (init, bootstrap) — zero dependencies, ~2.7MB"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --full) FULL=true; shift ;;
        --dir) TARGET_DIR="$2"; shift 2 ;;
        --skill) SKILL_TARGET="$2"; shift 2 ;;
        --agents) AGENTS_TARGET="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown: $1"; usage ;;
    esac
done

# Detect platform
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

case "$OS" in
    linux)   GOOS="linux" ;;
    darwin)  GOOS="darwin" ;;
    mingw*|msys*|cygwin*) GOOS="windows" ;;
    *) echo "Unsupported OS: $OS"; exit 1 ;;
esac

case "$ARCH" in
    x86_64|amd64) GOARCH="amd64" ;;
    aarch64|arm64) GOARCH="arm64" ;;
    *) echo "Unsupported arch: $ARCH"; exit 1 ;;
esac

# Pick binary — default to local-only
BINARY="wiki-tools-local-${GOOS}-${GOARCH}"
$FULL && BINARY="wiki-tools-${GOOS}-${GOARCH}"
[[ "$GOOS" == "windows" ]] && BINARY="${BINARY}.exe" && BIN_NAME="${BIN_NAME}.exe"

SRC="$DIST_DIR/$BINARY"

if [[ ! -f "$SRC" ]]; then
    echo "Binary not found: $SRC"
    echo "Available:"
    ls -1 "$DIST_DIR/"
    exit 1
fi

# Determine target directory
if [[ -z "$TARGET_DIR" ]]; then
    if [[ "$GOOS" == "darwin" ]]; then
        TARGET_DIR="/usr/local/bin"
    else
        TARGET_DIR="${HOME}/.local/bin"
    fi
fi

mkdir -p "$TARGET_DIR"

DST="$TARGET_DIR/$BIN_NAME"
cp "$SRC" "$DST"
chmod +x "$DST"

echo "Installed: $DST ($( [[ $FULL == true ]] && echo 'full' || echo 'local-only' ))"
"$DST" --version 2>/dev/null || true

# Check PATH
if ! echo "$PATH" | tr ':' '\n' | grep -qF "$TARGET_DIR"; then
    echo ""
    echo "Add to PATH:"
    echo "  export PATH=\"$TARGET_DIR:\$PATH\""
    echo "  (add this line to ~/.bashrc or ~/.zshrc)"
fi

# Skill
if [[ -n "$SKILL_TARGET" ]]; then
    SKILL_SRC="$SCRIPT_DIR/skills/wiki.md"
    SKILL_DST="$SKILL_TARGET/.claude/skills/wiki.md"
    mkdir -p "$(dirname "$SKILL_DST")"
    cp "$SKILL_SRC" "$SKILL_DST"
    echo "Skill installed: $SKILL_DST"
fi

# AGENTS.md
if [[ -n "$AGENTS_TARGET" ]]; then
    AGENTS_SRC="$SCRIPT_DIR/platform-adapters/AGENTS.md"
    AGENTS_DST="$AGENTS_TARGET/AGENTS.md"
    cp "$AGENTS_SRC" "$AGENTS_DST"
    echo "AGENTS.md installed: $AGENTS_DST"
fi

echo ""
echo "Done. Try: wiki-tools init ~/my-wiki \"My Domain\""
