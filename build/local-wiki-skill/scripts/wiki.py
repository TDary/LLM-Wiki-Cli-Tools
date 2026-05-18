#!/usr/bin/env python3
"""wiki-tools — Local wiki management (pure local mode, no Git)."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    except Exception:
        pass

VERSION = "0.1.0"

DIRS = ["raw", "entities", "concepts", "relations", "queries", "drafts"]


# ── helpers ──

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def expand(s: str) -> Path:
    return Path(s).expanduser().resolve()


# ── templates ──

def template_schema(name: str, domain: str) -> str:
    return f"""# SCHEMA — {name}

> 知识库领域配置 · 自动生成的索引和关系

## 基本信息

| 属性 | 值 |
|------|-----|
| **名称** | {name} |
| **领域** | {domain} |
| **Git 同步** | 禁用（纯本地模式） |
| **创建时间** | {now()} |
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

```yaml
tags:
  - type: tech
    label: 技术
  - type: process
    label: 流程
  - type: reference
    label: 参考
```

## 关系类型

```yaml
relations:
  - depends_on: 依赖
  - references: 引用
  - implements: 实现
  - owned_by: 归属
```
"""


def template_readme(name: str, domain: str) -> str:
    return f"""# {name}

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
"""


def template_log() -> str:
    return f"""# 更新日志

## {today()}

- 🎉 知识库初始化完成
"""


# ── commands ──

def cmd_init(args: argparse.Namespace) -> None:
    path = expand(args.path or "~/wiki")
    domain = args.domain or "Wiki 知识库"
    name = args.name or path.name

    path.mkdir(parents=True, exist_ok=True)

    # Detect existing
    schema_path = path / "SCHEMA.md"
    if schema_path.exists() and not args.force:
        print(f"ℹ️  检测到已有知识库: {path}")
        print(f"   如需重新生成文件，请使用 --force")
        return

    # Create dirs
    for d in DIRS:
        (path / d).mkdir(parents=True, exist_ok=True)

    print("📁 目录结构已创建:")
    for d in DIRS:
        print(f"   {d}/")

    # Write files (idempotent unless --force)
    def _write(p: Path, content: str):
        if args.force or not p.exists():
            p.write_text(content, encoding="utf-8")
            print(f"📄 {name}/{p.name}")

    _write(schema_path, template_schema(name, domain))
    _write(path / "README.md", template_readme(name, domain))
    _write(path / "log.md", template_log())

    print()
    print(f"✅ wiki-tools init 完成: {path}")
    print(f"   领域: {domain}")
    print(f"   模式: 本地（纯文件）")
    print(f"   目录: {len(DIRS)} 个子目录")


def cmd_sync(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    schema = path / "SCHEMA.md"

    if not schema.exists():
        print(f"❌ 未找到 SCHEMA.md: {path} 不是一个 wiki 目录")
        sys.exit(1)

    print(f"ℹ️  本地模式 — 无需同步，文件即唯一真相来源: {path}")


def cmd_bootstrap(args: argparse.Namespace) -> None:
    path = expand(args.path)
    domain = args.domain or "Wiki 知识库"

    if not path.exists():
        print(f"ℹ️  路径不存在，将创建本地知识库: {path}")
    elif (path / "SCHEMA.md").exists() and not args.force:
        print(f"ℹ️  检测到已有知识库: {path}")
        print(f"   如需重新生成，请使用 --force")
        return

    cmd_init(argparse.Namespace(
        path=str(path), domain=domain, name=args.name or path.name,
        force=args.force,
    ))


def cmd_install(args: argparse.Namespace) -> None:
    """Install skill files into a project (Claude Code, Copilot, Cursor, Windsurf, OpenClaw)."""
    import shutil

    project = expand(args.path)
    skill_dir = project / ".claude" / "skills"
    scripts_dir = project / ".claude" / "skills-wiki-scripts"
    skill_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    script_path = Path(__file__).resolve()
    pkg_dir = script_path.parent.parent  # scripts/.. -> package root

    # Claude Code skill
    skill_src = pkg_dir / "SKILL.md"
    if skill_src.exists():
        shutil.copy2(skill_src, skill_dir / "wiki.md")
        print(f"✔  {skill_dir / 'wiki.md'}")

    # Other agents (Copilot, Cursor, Windsurf, OpenClaw)
    agents_src = pkg_dir / "AGENTS.md"
    if agents_src.exists():
        shutil.copy2(agents_src, project / "AGENTS.md")
        print(f"✔  {project / 'AGENTS.md'}")

    # Python script
    shutil.copy2(script_path, scripts_dir / "wiki.py")
    print(f"✔  {scripts_dir / 'wiki.py'}")

    print()
    print("Done. The skill is now active for Claude Code + all AGENTS.md-compatible tools.")


# ── CLI ──

def main() -> None:
    parser = argparse.ArgumentParser(prog="wiki-tools", description="Local wiki management")
    parser.add_argument("--version", action="version", version=f"wiki-tools v{VERSION}")

    sub = parser.add_subparsers(dest="command")

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

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "init":
        cmd_init(args)
    elif args.command == "sync":
        cmd_sync(args)
    elif args.command == "bootstrap":
        cmd_bootstrap(args)
    elif args.command == "install":
        cmd_install(args)


if __name__ == "__main__":
    main()
