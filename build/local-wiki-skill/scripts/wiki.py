#!/usr/bin/env python3
"""wiki-tools — Local wiki management (pure local mode, no Git)."""

import argparse
import sys

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    except Exception:
        pass

from wiki_core import VERSION, DIRS
from wiki_core.cmd_init import cmd_init, cmd_sync, cmd_bootstrap, cmd_install
from wiki_core.cmd_query import cmd_list, cmd_index, cmd_search, cmd_backlinks, cmd_tags, cmd_stats
from wiki_core.cmd_health import cmd_orphans, cmd_health, cmd_trace, cmd_fix, cmd_rename, cmd_archive
from wiki_core.cmd_ingest import cmd_ingest


def main() -> None:
    parser = argparse.ArgumentParser(prog="wiki-tools", description="Local wiki management")
    parser.add_argument("--version", action="version", version=f"wiki-tools v{VERSION}")

    sub = parser.add_subparsers(dest="command")

    # ── init group ──
    p_init = sub.add_parser("init", help="创建新知识库")
    p_init.add_argument("path", nargs="?", default="~/wiki")
    p_init.add_argument("domain", nargs="?", default="Wiki 知识库")
    p_init.add_argument("--name", default="")
    p_init.add_argument("--force", action="store_true", help="覆盖已存在的文件")

    p_sync = sub.add_parser("sync", help="同步（本地模式仅确认状态）")
    p_sync.add_argument("path", nargs="?", default=".")

    p_boot = sub.add_parser("bootstrap", help="从本地路径引导知识库")
    p_boot.add_argument("path", help="Wiki 路径")
    p_boot.add_argument("--domain", default="Wiki 知识库")
    p_boot.add_argument("--name", default="")
    p_boot.add_argument("--force", action="store_true")

    p_install = sub.add_parser("install", help="安装 skill 到目标项目")
    p_install.add_argument("path", help="项目路径")

    # ── query group ──
    p_list = sub.add_parser("list", help="列举所有知识文档")
    p_list.add_argument("path", nargs="?", default=".")
    p_list.add_argument("--format", default="table", choices=["table", "json"])
    p_list.add_argument("--category", default="", help="过滤指定目录 (raw/entities/concepts/relations/queries/drafts)")
    p_list.add_argument("--tags", default="", help="按标签过滤 (逗号分隔, 如 AI,tech)")
    p_list.add_argument("--include-raw", action="store_true", dest="include_raw", help="包含原始资料目录 (默认排除)")
    p_list.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_index = sub.add_parser("index", help="生成结构化 JSON 索引")
    p_index.add_argument("path", nargs="?", default=".")
    p_index.add_argument("--output", default="", help="输出路径 (默认 queries/index.json)")
    p_index.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_search = sub.add_parser("search", help="全文搜索文档")
    p_search.add_argument("keyword", help="搜索关键词")
    p_search.add_argument("path", nargs="?", default=".")
    p_search.add_argument("--format", default="table", choices=["table", "json"])
    p_search.add_argument("--no-raw", action="store_true", dest="no_raw", help="排除原始资料目录")
    p_search.add_argument("--regex", action="store_true", help="正则表达式搜索")
    p_search.add_argument("--use-index", action="store_true", dest="use_index", help="使用倒排索引加速搜索 (需先运行 index)")
    p_search.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_backlinks = sub.add_parser("backlinks", help="查看页面的反向链接")
    p_backlinks.add_argument("page", help="目标页面名 (如 transformer-architecture)")
    p_backlinks.add_argument("path", nargs="?", default=".")
    p_backlinks.add_argument("--format", default="table", choices=["table", "json"])
    p_backlinks.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_tags = sub.add_parser("tags", help="列出所有标签及使用统计")
    p_tags.add_argument("path", nargs="?", default=".")
    p_tags.add_argument("--format", default="table", choices=["table", "json"])
    p_tags.add_argument("--sort", default="count", choices=["count", "name"], help="排序方式")
    p_tags.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_stats = sub.add_parser("stats", help="知识库概览统计")
    p_stats.add_argument("path", nargs="?", default=".")
    p_stats.add_argument("--format", default="table", choices=["table", "json"])
    p_stats.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    # ── health group ──
    p_orphans = sub.add_parser("orphans", help="检测孤立文档")
    p_orphans.add_argument("path", nargs="?", default=".")
    p_orphans.add_argument("--format", default="table", choices=["table", "json"])
    p_orphans.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_health = sub.add_parser("health", help="知识库健康检查")
    p_health.add_argument("path", nargs="?", default=".")
    p_health.add_argument("--format", default="table", choices=["table", "json"])
    p_health.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_trace = sub.add_parser("trace", help="溯源追踪文档上下游引用链")
    p_trace.add_argument("page", help="目标页面名 (如 transformer-architecture)")
    p_trace.add_argument("path", nargs="?", default=".")
    p_trace.add_argument("--format", default="table", choices=["table", "json"])
    p_trace.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_fix = sub.add_parser("fix", help="结构层自愈检查与修复")
    p_fix.add_argument("path", nargs="?", default=".")
    p_fix.add_argument("--apply", action="store_true", help="执行修复（默认仅预览）")
    p_fix.add_argument("--interactive", "-i", action="store_true", help="逐条确认修复")
    p_fix.add_argument("--format", default="table", choices=["table", "json"])
    p_fix.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_rename = sub.add_parser("rename", help="重命名文档并全局更新链接")
    p_rename.add_argument("old_name", help="旧文档名 (如 transformer-architecture)")
    p_rename.add_argument("new_name", help="新文档名 (如 attention-mechanism)")
    p_rename.add_argument("path", nargs="?", default=".")
    p_rename.add_argument("--apply", action="store_true", help="执行重命名（默认仅预览）")
    p_rename.add_argument("--format", default="table", choices=["table", "json"])
    p_rename.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_archive = sub.add_parser("archive", help="归档文档到 _archive/ 目录")
    p_archive.add_argument("page", help="目标页面名 (如 transformer-architecture)")
    p_archive.add_argument("path", nargs="?", default=".")
    p_archive.add_argument("--apply", action="store_true", help="执行归档（默认仅预览）")
    p_archive.add_argument("--format", default="table", choices=["table", "json"])
    p_archive.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    # ── ingest ──
    p_ingest = sub.add_parser("ingest", help="摄入外部源到知识库")
    p_ingest.add_argument("path", nargs="?", default=".")
    p_ingest.add_argument("--url", default="", help="URL to fetch and save to raw/")
    p_ingest.add_argument("--file", default="", help="Local file to copy into raw/")
    p_ingest.add_argument("--template", default="", metavar="TITLE", help="Create wiki page template")
    p_ingest.add_argument("--manifest", default="", help="JSON manifest file for bulk ingest")
    p_ingest.add_argument("--category", default="drafts", choices=DIRS, help="Category for template (default: drafts)")
    p_ingest.add_argument("--tags", default="", help="Tags for template (comma-separated)")
    p_ingest.add_argument("--format", default="table", choices=["table", "json"])
    p_ingest.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    # ── dispatch ──
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "init": cmd_init,
        "sync": cmd_sync,
        "bootstrap": cmd_bootstrap,
        "install": cmd_install,
        "list": cmd_list,
        "index": cmd_index,
        "search": cmd_search,
        "backlinks": cmd_backlinks,
        "tags": cmd_tags,
        "stats": cmd_stats,
        "orphans": cmd_orphans,
        "health": cmd_health,
        "trace": cmd_trace,
        "fix": cmd_fix,
        "rename": cmd_rename,
        "archive": cmd_archive,
        "ingest": cmd_ingest,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
