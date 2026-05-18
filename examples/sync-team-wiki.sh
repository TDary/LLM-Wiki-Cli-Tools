#!/bin/bash
# wiki 自动同步脚本 — 薄封装，调用通用 git-auto-sync CLI
export GIT_SYNC_NAME="你的Agent"
export GIT_SYNC_EMAIL="agent@local"
export PATH="$HOME/.local/bin:$PATH"
exec git-auto-sync ~/team-wiki
