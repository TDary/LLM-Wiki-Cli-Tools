"""Commands: init, sync, bootstrap, install."""

import argparse
import shutil
import sys
from pathlib import Path

from . import DIRS
from .helpers import expand, require_wiki, now
from .templates import template_schema, template_readme, template_log


def cmd_init(args: argparse.Namespace) -> None:
    path = expand(args.path or "~/wiki")
    domain = args.domain or "Wiki 知识库"
    name = args.name or path.name

    path.mkdir(parents=True, exist_ok=True)

    schema_path = path / "SCHEMA.md"
    if schema_path.exists() and not args.force:
        print(f"ℹ️  检测到已有知识库: {path}")
        print(f"   如需重新生成文件，请使用 --force")
        return

    for d in DIRS:
        (path / d).mkdir(parents=True, exist_ok=True)

    print("📁 目录结构已创建:")
    for d in DIRS:
        print(f"   {d}/")

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
    require_wiki(path)
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
    """Install skill files into a project."""
    project = expand(args.path)
    skill_dir = project / ".claude" / "skills"
    scripts_dir = project / ".claude" / "skills-wiki-scripts"
    skill_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    script_path = Path(__file__).resolve().parent.parent / "wiki.py"
    pkg_dir = script_path.parent.parent  # scripts/.. -> package root

    # Claude Code skill
    skill_src = pkg_dir / "SKILL.md"
    if skill_src.exists():
        shutil.copy2(skill_src, skill_dir / "wiki.md")
        print(f"✔  {skill_dir / 'wiki.md'}")

    # Other agents
    agents_src = pkg_dir / "platform-adapters" / "AGENTS.md"
    if not agents_src.exists():
        agents_src = pkg_dir / "AGENTS.md"
    if agents_src.exists():
        shutil.copy2(agents_src, project / "AGENTS.md")
        print(f"✔  {project / 'AGENTS.md'}")

    # Python script + wiki_core package
    shutil.copy2(script_path, scripts_dir / "wiki.py")
    print(f"✔  {scripts_dir / 'wiki.py'}")

    core_src = script_path.parent / "wiki_core"
    core_dst = scripts_dir / "wiki_core"
    if core_src.is_dir():
        if core_dst.exists():
            shutil.rmtree(core_dst)
        shutil.copytree(core_src, core_dst)
        print(f"✔  {core_dst}")

    print()
    print("Done. The skill is now active for Claude Code + all AGENTS.md-compatible tools.")
