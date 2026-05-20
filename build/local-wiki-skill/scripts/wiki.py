#!/usr/bin/env python3
"""wiki-tools — Local wiki management (pure local mode, no Git)."""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    except Exception:
        pass

VERSION = "1.1.0"

DIRS = ["raw", "entities", "concepts", "relations", "queries", "drafts"]

CATEGORY_LABELS = {
    "raw": "原始资料",
    "entities": "实体",
    "concepts": "概念",
    "relations": "关系",
    "queries": "查询",
    "drafts": "草稿",
}

SYSTEM_FILES = {"readme.md", "log.md", "schema.md"}

# ── helpers ──

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def expand(s: str) -> Path:
    return Path(s).expanduser().resolve()

def require_wiki(path: Path) -> None:
    """Exit if path is not a valid wiki directory."""
    if not (path / "SCHEMA.md").exists():
        print(f"❌ 未找到 SCHEMA.md: {path} 不是一个 wiki 目录")
        sys.exit(1)

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

# ── document helpers ──

def extract_title(filepath: Path) -> str:
    """Extract title from first # heading in a markdown file."""
    try:
        for line in filepath.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
    except Exception:
        pass
    return filepath.stem.replace("-", " ").title()

def extract_frontmatter(filepath: Path) -> dict:
    """Extract YAML-style frontmatter between --- markers."""
    try:
        return extract_frontmatter_from_text(filepath.read_text(encoding="utf-8"))
    except Exception:
        return {}

def extract_frontmatter_from_text(text: str) -> dict:
    """Extract YAML-style frontmatter from raw text."""
    fm = {}
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            line = lines[i].strip()
            if line == "---":
                break
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key == "tags":
                    fm[key] = [t.strip() for t in val.strip("[]").split(",") if t.strip()]
                else:
                    fm[key] = val
    return fm

def build_backlink_map(wiki_path: Path) -> dict[str, list[dict]]:
    """Build a map of {target_file: [source_doc_info, ...]} from all wikilinks."""
    backlinks: dict[str, list[dict]] = {}
    for d in DIRS:
        category_dir = wiki_path / d
        if not category_dir.is_dir():
            continue
        for md_file in sorted(category_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            rel_file = str(md_file.relative_to(wiki_path)).replace("\\", "/")
            fm = extract_frontmatter_from_text(text)
            title = fm.get("title") or extract_title(md_file)
            text_lines = text.splitlines()
            link_targets = [m.group(1) for m in re.finditer(r"\[\[(.+?)\]\]", text)]
            for target in link_targets:
                target_stem = target.strip().lower().replace(" ", "-")
                if target_stem not in backlinks:
                    backlinks[target_stem] = []
                link_pattern = f"[[{target}]]"
                for line_no, line in enumerate(text_lines, 1):
                    if link_pattern in line:
                        backlinks[target_stem].append({
                            "source_title": title,
                            "source_file": rel_file,
                            "line": line_no,
                            "line_content": line.strip(),
                        })
    return backlinks

def search_documents(docs: list[dict], keyword: str, regex: bool = False) -> list[dict]:
    """Search documents by keyword or regex pattern in title and body content."""
    if regex:
        try:
            matcher = re.compile(keyword).search
        except re.error as e:
            print(f"❌ 无效正则表达式: {e}")
            sys.exit(1)
    else:
        kw_lower = keyword.lower()
        matcher = lambda s: kw_lower in s.lower()

    results = []
    for doc in docs:
        matches_in_file = []
        if matcher(doc["title"]):
            matches_in_file.append({"line": 0, "content": doc["title"]})
        text = doc.get("_text", "")
        if not text:
            try:
                text = Path(doc["absolute_path"]).read_text(encoding="utf-8")
            except Exception:
                pass
        for line_no, line in enumerate(text.splitlines(), 1):
            if matcher(line):
                matches_in_file.append({"line": line_no, "content": line.strip()})
        if matches_in_file:
            out = {k: v for k, v in doc.items() if k != "_text"}
            out["matches"] = matches_in_file
            out["match_count"] = len(matches_in_file)
            results.append(out)
    return results

def collect_documents(wiki_path: Path) -> list[dict]:
    """Walk all category dirs and collect markdown file metadata."""
    docs = []
    for d in DIRS:
        category_dir = wiki_path / d
        if not category_dir.is_dir():
            continue
        for md_file in sorted(category_dir.glob("*.md")):
            stat = md_file.stat()
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                text = ""
            fm = extract_frontmatter_from_text(text)
            docs.append({
                "title": fm.get("title") or extract_title(md_file),
                "file": str(md_file.relative_to(wiki_path)).replace("\\", "/"),
                "absolute_path": str(md_file.resolve()).replace("\\", "/"),
                "category": d,
                "category_label": CATEGORY_LABELS.get(d, d),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "tags": fm.get("tags", []),
                "links_count": len(re.findall(r"\[\[.+?\]\]", text)),
                "_text": text,
            })
    return docs

def read_schema_meta(wiki_path: Path) -> dict:
    """Read basic metadata from SCHEMA.md."""
    meta = {"name": wiki_path.name, "domain": "Wiki 知识库"}
    schema_path = wiki_path / "SCHEMA.md"
    if not schema_path.exists():
        return meta
    try:
        for line in schema_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("| **名称** |"):
                parts = [p.strip() for p in stripped.split("|") if p.strip()]
                if len(parts) >= 2:
                    meta["name"] = parts[1]
            elif stripped.startswith("| **领域** |"):
                parts = [p.strip() for p in stripped.split("|") if p.strip()]
                if len(parts) >= 2:
                    meta["domain"] = parts[1]
            elif stripped.startswith("| **创建时间** |"):
                parts = [p.strip() for p in stripped.split("|") if p.strip()]
                if len(parts) >= 2:
                    meta["created_at"] = parts[1]
    except Exception:
        pass
    return meta

def _extract_yaml_block(wiki_path: Path, section_keyword: str) -> list[str]:
    """Extract YAML lines from a ```yaml block under a ## section in SCHEMA.md."""
    schema_path = wiki_path / "SCHEMA.md"
    if not schema_path.exists():
        return []
    try:
        lines = schema_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    in_yaml = False
    in_section = False
    yaml_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = section_keyword in stripped
            in_yaml = False
            continue
        if in_section and stripped == "```yaml":
            in_yaml = True
            continue
        if in_yaml and stripped == "```":
            break
        if in_yaml and in_section:
            yaml_lines.append(line)
    return yaml_lines

def _parse_yaml_kv_pairs(yaml_lines: list[str]) -> dict[str, str]:
    """Parse simple 'key: value' pairs from YAML lines, skipping known headers."""
    result = {}
    for yl in yaml_lines:
        yl = yl.strip()
        if not yl or yl.endswith(":"):
            continue
        if ":" in yl:
            key, _, val = yl.partition(":")
            result[key.strip()] = val.strip().strip("\"'")
    return result

HEALTH_WEIGHT_DEFAULTS = {
    "orphan": 3, "broken_link": 5, "no_tag": 1,
    "low_link": 2, "empty_doc": 2, "self_link": 1,
}

def read_health_config(wiki_path: Path) -> dict:
    """Read configurable health check weights from SCHEMA.md."""
    config = dict(HEALTH_WEIGHT_DEFAULTS)
    for key, val in _parse_yaml_kv_pairs(_extract_yaml_block(wiki_path, "健康检查")).items():
        try:
            n = int(val)
            if n > 0:
                config[key] = n
        except ValueError:
            pass
    return config

def read_custom_checks(wiki_path: Path) -> list[dict]:
    """Read custom health checks from SCHEMA.md."""
    yaml_lines = _extract_yaml_block(wiki_path, "自定义检查")
    checks = []
    current = {}
    for yl in yaml_lines:
        yl = yl.strip()
        if not yl or yl == "checks:":
            continue
        if yl.startswith("- "):
            if current.get("name"):
                checks.append(current)
            current = {"weight": 1}
            kv = _parse_yaml_kv_pairs(["  " + yl[2:]])
            for k, v in kv.items():
                if k in ("name", "command", "description"):
                    current[k] = v
                elif k == "weight":
                    try:
                        current["weight"] = int(v)
                    except ValueError:
                        pass
            continue
        kv = _parse_yaml_kv_pairs([yl])
        for k, v in kv.items():
            if k in ("name", "command", "description"):
                current[k] = v
            elif k == "weight":
                try:
                    current["weight"] = int(v)
                except ValueError:
                    pass
    if current.get("name"):
        checks.append(current)
    return checks

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

def _strip_internal(docs: list[dict]) -> list[dict]:
    """Remove internal fields (_text) before serialization."""
    return [{k: v for k, v in d.items() if not k.startswith("_")} for d in docs]

def cmd_list(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents(path)

    # Filter by category
    if hasattr(args, "category") and args.category:
        docs = [d for d in docs if d["category"] == args.category]
    elif not getattr(args, "include_raw", False):
        # Default: exclude raw/ (immutable source material)
        docs = [d for d in docs if d["category"] != "raw"]

    # Filter by tags
    if hasattr(args, "tags") and args.tags:
        filter_tags = {t.strip().lower() for t in args.tags.split(",") if t.strip()}
        docs = [d for d in docs if filter_tags & {t.lower() for t in d.get("tags", [])}]

    if args.format == "json":

        meta = read_schema_meta(path)
        output = {
            "wiki": meta,
            "total": len(docs),
            "documents": _strip_internal(docs),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if getattr(args, "pretty", False) else None))
        return

    # Table format
    meta = read_schema_meta(path)
    print(f"\n📚 {meta['name']} — {meta['domain']}")
    print(f"   共 {len(docs)} 篇文档\n")

    current_cat = None
    for d in docs:
        if d["category"] != current_cat:
            current_cat = d["category"]
            print(f"  [{d['category_label']}] ({d['category']}/)")
        tags_str = f" [{', '.join(d['tags'])}]" if d["tags"] else ""
        links_str = f"  🔗{d['links_count']}" if d["links_count"] > 0 else ""
        readonly = "  🔒只读" if d["category"] == "raw" else ""
        print(f"    {d['title']}")
        print(f"    ├─ {d['file']}  ({d['size']}B, {d['modified']}){tags_str}{links_str}{readonly}")
        print()

def cmd_index(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    import json

    docs = collect_documents(path)
    meta = read_schema_meta(path)

    # Group by category
    by_category = {}
    for d in docs:
        cat = d["category"]
        if cat not in by_category:
            by_category[cat] = {
                "category": cat,
                "category_label": d["category_label"],
                "count": 0,
                "documents": [],
            }
        by_category[cat]["count"] += 1
        by_category[cat]["documents"].append({k: v for k, v in d.items() if not k.startswith("_")})

    # Collect all tags
    all_tags = set()
    for d in docs:
        for t in d.get("tags", []):
            all_tags.add(t)

    index = {
        "wiki": meta,
        "generated_at": now(),
        "total_documents": len(docs),
        "categories": [by_category[k] for k in DIRS if k in by_category],
        "tags": sorted(all_tags),
    }

    output_path = expand(args.output or str(path / "queries" / "index.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    indent = 2 if args.pretty else None
    output_path.write_text(json.dumps(index, ensure_ascii=False, indent=indent), encoding="utf-8")

    print(f"✅ 索引已生成: {output_path}")
    print(f"   文档总数: {len(docs)}")
    print(f"   分类数: {len(by_category)}")
    print(f"   标签: {', '.join(sorted(all_tags)) if all_tags else '无'}")

def cmd_search(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents(path)

    # Exclude raw/ if --no-raw
    if getattr(args, "no_raw", False):
        docs = [d for d in docs if d["category"] != "raw"]

    if getattr(args, "regex", False):
        results = search_documents(docs, args.keyword, regex=True)
    else:
        results = search_documents(docs, args.keyword)

    if args.format == "json":

        meta = read_schema_meta(path)
        output = {
            "wiki": meta,
            "keyword": args.keyword,
            "total": len(results),
            "results": results,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    # Table format
    print(f"\n🔍 搜索: \"{args.keyword}\"")
    print(f"   匹配文档: {len(results)} 篇\n")
    for r in results:
        print(f"  📄 {r['title']}")
        print(f"     {r['file']}  ({r['category']})")
        for m in r["matches"][:5]:
            prefix = f"L{m['line']}" if m["line"] > 0 else "标题"
            content = m["content"]
            if len(content) > 80:
                content = content[:77] + "..."
            print(f"     {prefix}: {content}")
        if len(r["matches"]) > 5:
            print(f"     ... 共 {r['match_count']} 处匹配")
        print()

def cmd_backlinks(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    # Resolve the target page stem
    page = args.page
    # Strip .md extension if provided
    if page.endswith(".md"):
        page = page[:-3]
    target_stem = page.strip().lower().replace(" ", "-")

    backlinks = build_backlink_map(path)
    refs = backlinks.get(target_stem, [])

    if args.format == "json":

        meta = read_schema_meta(path)
        output = {
            "wiki": meta,
            "page": args.page,
            "total": len(refs),
            "backlinks": refs,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    # Table format
    print(f"\n🔗 反向链接: [[{page}]]")
    print(f"   被引用次数: {len(refs)}\n")
    if not refs:
        print("   没有找到引用此页面的文档。")
    else:
        for ref in refs:
            print(f"  📄 {ref['source_title']}")
            print(f"     {ref['source_file']}  (L{ref['line']})")
            content = ref["line_content"]
            if len(content) > 80:
                content = content[:77] + "..."
            print(f"     {content}")
            print()

def cmd_orphans(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents(path)
    backlinks = build_backlink_map(path)

    # System files to exclude
    orphans = []
    for doc in docs:
        if doc["category"] == "raw":
            continue
        stem = Path(doc["file"]).stem.lower()
        if stem in SYSTEM_FILES:
            continue
        if stem not in backlinks or len(backlinks[stem]) == 0:
            orphans.append(doc)

    if args.format == "json":

        meta = read_schema_meta(path)
        output = {
            "wiki": meta,
            "total": len(orphans),
            "orphans": _strip_internal(orphans),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    # Table format
    print(f"\n🏝️  孤立文档检测")
    print(f"   文档总数: {len(docs)}")
    print(f"   孤立文档: {len(orphans)}\n")
    if not orphans:
        print("   ✅ 没有发现孤立文档，所有文档都有入站链接。")
    else:
        for d in orphans:
            print(f"  📄 {d['title']}")
            print(f"     {d['file']}  ({d['category']})")
            if d["links_count"] > 0:
                print(f"     出站链接: {d['links_count']} 个（但无文档链接到此页面）")
            else:
                print(f"     ⚠️  无出站链接且无入站链接")
        print()
        print("💡 建议: 在相关文档中添加 [[wikilinks]] 指向孤立文档，或将它们合并到其他页面。")

def cmd_health(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents(path)
    backlinks = build_backlink_map(path)

    # Read configurable weights
    weights = read_health_config(path)

    # Exclude system files and raw/ (immutable source material)
    user_docs = [d for d in docs if d["category"] != "raw" and Path(d["file"]).stem.lower() not in SYSTEM_FILES]

    # Build set of all existing page stems for broken link detection
    existing_stems = {Path(d["file"]).stem.lower() for d in docs}

    # Check 1: Orphan documents (no inbound links)
    orphans = []
    for d in user_docs:
        stem = Path(d["file"]).stem.lower()
        if stem not in backlinks or len(backlinks[stem]) == 0:
            orphans.append(d)

    # Check 2: Broken wikilinks (outbound links to non-existent pages)
    broken_links = []
    for d in user_docs:
        text = d.get("_text", "")
        if not text:
            try:
                text = Path(d["absolute_path"]).read_text(encoding="utf-8")
            except Exception:
                continue
        for m in re.finditer(r"\[\[(.+?)\]\]", text):
            target = m.group(1).strip().lower().replace(" ", "-")
            if target not in existing_stems:
                # Find line number
                for line_no, line in enumerate(text.splitlines(), 1):
                    if f"[[{m.group(1)}]]" in line:
                        broken_links.append({
                            "source_file": d["file"],
                            "source_title": d["title"],
                            "target": m.group(1),
                            "line": line_no,
                        })
                        break

    # Check 3: Documents without tags
    no_tags = [d for d in user_docs if not d.get("tags")]

    # Check 4: Documents with < 2 outbound links
    low_links = [d for d in user_docs if d["links_count"] < 2]

    # Check 5: Empty documents (< 50 bytes of content)
    empty_docs = [d for d in user_docs if len(d.get("_text", "").strip()) < 50]

    # Check 6: Self-referential links (page links to itself)
    self_links = []
    for d in user_docs:
        self_stem = Path(d["file"]).stem.lower()
        text = d.get("_text", "")
        for line_no, line in enumerate(text.splitlines(), 1):
            for m in re.finditer(r"\[\[(.+?)\]\]", line):
                target = m.group(1).strip().lower().replace(" ", "-")
                if target == self_stem:
                    self_links.append({
                        "file": d["file"],
                        "title": d["title"],
                        "line": line_no,
                        "link": m.group(1),
                    })

    # Custom checks
    custom_checks = read_custom_checks(path)
    custom_results = []
    custom_deduction = 0

    for check in custom_checks:
        result = {
            "name": check.get("name", ""),
            "description": check.get("description", ""),
            "weight": check.get("weight", 1),
            "issues": [],
            "count": 0,
        }
        cmd = check.get("command", "")
        if cmd:
            try:
                proc = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True,
                    timeout=5, cwd=str(path),
                )
                if proc.stdout.strip():
                    lines = [l.strip() for l in proc.stdout.strip().splitlines() if l.strip()]
                    result["issues"] = lines
                    result["count"] = len(lines)
                elif proc.returncode != 0 and proc.stderr.strip():
                    result["issues"] = [proc.stderr.strip()[:200]]
                    result["count"] = 1
            except subprocess.TimeoutExpired:
                result["issues"] = ["命令超时（5 秒）"]
                result["count"] = 1
            except Exception as e:
                result["issues"] = [str(e)[:200]]
                result["count"] = 1
        if result["count"] > 0:
            custom_deduction += result["count"] * result["weight"]
        custom_results.append(result)

    # Calculate health score with configurable weights
    total_checks = len(user_docs) if user_docs else 1
    sum_weights = (weights.get("orphan", 3) + weights.get("broken_link", 5) +
                   weights.get("no_tag", 1) + weights.get("low_link", 2) +
                   weights.get("empty_doc", 2) + weights.get("self_link", 1))
    if sum_weights == 0:
        sum_weights = 6
    deductions = (
        len(orphans) * weights.get("orphan", 3) +
        len(broken_links) * weights.get("broken_link", 5) +
        len(no_tags) * weights.get("no_tag", 1) +
        len(low_links) * weights.get("low_link", 2) +
        len(empty_docs) * weights.get("empty_doc", 2) +
        len(self_links) * weights.get("self_link", 1)
    )
    score = max(0, min(100, 100 - (deductions + custom_deduction) * 100 // (total_checks * sum_weights)))

    # Status icon
    def status_icon(count: int, threshold: int = 0) -> str:
        if count == 0:
            return "✅"
        elif count <= threshold:
            return "⚠️"
        else:
            return "❌"

    if args.format == "json":

        meta = read_schema_meta(path)
        output = {
            "wiki": meta,
            "score": score,
            "total_documents": len(user_docs),
            "weights": weights,
            "checks": {
                "orphans": {"count": len(orphans), "items": orphans},
                "broken_links": {"count": len(broken_links), "items": broken_links},
                "no_tags": {"count": len(no_tags), "items": _strip_internal(no_tags)},
                "low_links": {"count": len(low_links), "items": _strip_internal(low_links)},
                "empty_docs": {"count": len(empty_docs), "items": _strip_internal(empty_docs)},
                "self_links": {"count": len(self_links), "items": self_links},
                "custom": custom_results,
            },
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    # Table format
    meta = read_schema_meta(path)
    print(f"\n🏥 {meta['name']} — 知识库健康报告")
    print(f"   文档总数: {len(user_docs)}\n")

    print(f"   {status_icon(len(orphans), 5)} 孤立文档:     {len(orphans)} 篇 (权重 {weights.get('orphan', 3)})")
    print(f"   {status_icon(len(broken_links))} 断链:         {len(broken_links)} 处 (权重 {weights.get('broken_link', 5)})")
    print(f"   {status_icon(len(no_tags), 5)} 无标签文档:   {len(no_tags)} 篇 (权重 {weights.get('no_tag', 1)})")
    print(f"   {status_icon(len(low_links), 5)} 链接不足:     {len(low_links)} 篇 (< 2 条链接, 权重 {weights.get('low_link', 2)})")
    print(f"   {status_icon(len(empty_docs), 3)} 空文档:       {len(empty_docs)} 篇 (< 50 字节, 权重 {weights.get('empty_doc', 2)})")
    print(f"   {status_icon(len(self_links))} 自引用:       {len(self_links)} 处 (权重 {weights.get('self_link', 1)})")

    for cr in custom_results:
        icon = "✅" if cr["count"] == 0 else "⚠️"
        print(f"   {icon} {cr['name']:<14} {cr['count']} 处 (权重 {cr['weight']})")

    print(f"\n   健康评分: {score}/100")

    # Show details for issues
    if broken_links:
        print(f"\n   ── 断链详情 ──")
        for bl in broken_links[:10]:
            print(f"   ❌ {bl['source_file']} (L{bl['line']}): [[{bl['target']}]] → 不存在")
        if len(broken_links) > 10:
            print(f"   ... 共 {len(broken_links)} 处断链")

    if orphans:
        print(f"\n   ── 孤立文档 ──")
        for d in orphans[:10]:
            print(f"   📄 {d['title']}  ({d['file']})")
        if len(orphans) > 10:
            print(f"   ... 共 {len(orphans)} 篇孤立文档")

    if empty_docs:
        print(f"\n   ── 空文档 ──")
        for d in empty_docs[:10]:
            text = d.get("_text", "")
            print(f"   📄 {d['title']}  ({d['file']}, {len(text.strip())} 字节)")
        if len(empty_docs) > 10:
            print(f"   ... 共 {len(empty_docs)} 篇空文档")

    if self_links:
        print(f"\n   ── 自引用 ──")
        for sl in self_links[:10]:
            print(f"   🔄 {sl['file']} (L{sl['line']}): [[{sl['link']}]] → 自身")
        if len(self_links) > 10:
            print(f"   ... 共 {len(self_links)} 处自引用")

    # Show custom check details
    for cr in custom_results:
        if cr["count"] > 0:
            print(f"\n   ── {cr['name']} ──")
            for issue in cr["issues"][:10]:
                print(f"   ⚠️  {issue}")
            if len(cr["issues"]) > 10:
                print(f"   ... 共 {len(cr['issues'])} 处")

    # Suggestions
    issues = []
    if broken_links:
        issues.append("修复断链（目标页面不存在）")
    if orphans:
        issues.append("为孤立文档添加 [[wikilinks]]")
    if no_tags:
        issues.append("给无标签文档添加 frontmatter tags")
    if low_links:
        issues.append("为链接不足的文档补充交叉引用（建议 >= 2 条）")
    if empty_docs:
        issues.append("补充空文档内容或删除无用占位页")
    if self_links:
        issues.append("移除自引用链接（页面不应链接到自身）")
    for cr in custom_results:
        if cr["count"] > 0:
            issues.append(f"{cr['name']}: {cr['description']}")

    if issues:
        print(f"\n   💡 建议:")
        for i, issue in enumerate(issues, 1):
            print(f"      {i}. {issue}")
    else:
        print(f"\n   🎉 知识库状态良好，没有发现明显问题。")

def _build_link_graph(wiki_path: Path) -> tuple[dict[str, list[str]], dict[str, dict]]:
    """Build bidirectional link graph. Returns (outbound_map, doc_info_map)."""
    outbound: dict[str, list[str]] = {}   # stem -> [target_stems]
    doc_info: dict[str, dict] = {}         # stem -> {title, file, category}

    for d in DIRS:
        category_dir = wiki_path / d
        if not category_dir.is_dir():
            continue
        for md_file in sorted(category_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            stem = md_file.stem.lower()
            fm = extract_frontmatter_from_text(text)
            title = fm.get("title") or extract_title(md_file)
            rel_file = str(md_file.relative_to(wiki_path)).replace("\\", "/")
            doc_info[stem] = {"title": title, "file": rel_file, "category": d}

            targets = []
            for m in re.finditer(r"\[\[(.+?)\]\]", text):
                target_stem = m.group(1).strip().lower().replace(" ", "-")
                targets.append(target_stem)
            outbound[stem] = targets

    return outbound, doc_info

def _trace_graph(stem: str, adjacency: dict[str, list[str]], visited: set, depth: int) -> list[dict]:
    """Recursively trace through a link graph."""
    results = []
    if depth > 10 or stem in visited:
        return results
    visited.add(stem)
    for neighbor in adjacency.get(stem, []):
        results.append({"stem": neighbor, "depth": depth})
        results.extend(_trace_graph(neighbor, adjacency, visited, depth + 1))
    return results

def cmd_trace(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    # Resolve target stem
    page = args.page
    if page.endswith(".md"):
        page = page[:-3]
    target_stem = page.strip().lower().replace(" ", "-")

    outbound, doc_info = _build_link_graph(path)

    # Build inbound map from outbound
    inbound: dict[str, list[str]] = {}
    for source, targets in outbound.items():
        for t in targets:
            if t not in inbound:
                inbound[t] = []
            inbound[t].append(source)

    doc = doc_info.get(target_stem)
    if not doc:
        print(f"❌ 未找到页面: {page}")
        sys.exit(1)

    # Trace upstream (what this page links to)
    upstream = _trace_graph(target_stem, outbound, set(), 1)
    # Trace downstream (what links to this page)
    downstream = _trace_graph(target_stem, inbound, set(), 1)

    if args.format == "json":

        meta = read_schema_meta(path)

        def _enrich(items):
            enriched = []
            for item in items:
                info = doc_info.get(item["stem"], {"title": item["stem"], "file": "???", "category": "???"})
                enriched.append({**item, **info})
            return enriched

        output = {
            "wiki": meta,
            "page": page,
            "document": doc,
            "upstream": _enrich(upstream),
            "downstream": _enrich(downstream),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    # Table format
    print(f"\n🔍 溯源: [[{page}]]")
    print(f"   {doc['title']}  ({doc['file']})")

    # Upstream
    print(f"\n   ── 上游（该页面引用了）──")
    if not upstream:
        print("   无上游引用。")
    else:
        seen = set()
        for item in upstream:
            if item["stem"] in seen:
                continue
            seen.add(item["stem"])
            info = doc_info.get(item["stem"])
            if info:
                indent = "   " + "  " * item["depth"]
                marker = "←" if item["depth"] == 1 else "←" + "─" * item["depth"]
                print(f" {indent}{marker} [[{info['title']}]]  ({info['file']})")
            else:
                indent = "   " + "  " * item["depth"]
                print(f" {indent}← [[{item['stem']}]]  (⚠️ 不存在)")

    # Downstream
    print(f"\n   ── 下游（哪些页面引用了该页面）──")
    if not downstream:
        print("   无下游引用。")
    else:
        seen = set()
        for item in downstream:
            if item["stem"] in seen:
                continue
            seen.add(item["stem"])
            info = doc_info.get(item["stem"])
            if info:
                indent = "   " + "  " * item["depth"]
                marker = "→" if item["depth"] == 1 else "→" + "─" * item["depth"]
                print(f" {indent}{marker} [[{info['title']}]]  ({info['file']})")

    # Summary
    print(f"\n   上游引用: {len(set(i['stem'] for i in upstream))} 个")
    print(f"   下游被引: {len(set(i['stem'] for i in downstream))} 个")

def _find_closest(target: str, candidates: list[str]) -> str | None:
    """Find the closest matching stem using edit distance."""
    best = None
    best_score = -1
    target_chars = set(target)
    for c in candidates:
        # Simple overlap score: ratio of shared characters
        c_chars = set(c)
        overlap = len(target_chars & c_chars) / max(len(target_chars | c_chars), 1)
        # Bonus for prefix match
        prefix = 0
        for a, b in zip(target, c):
            if a == b:
                prefix += 1
            else:
                break
        score = overlap + prefix * 0.1
        if score > best_score:
            best_score = score
            best = c
    return best if best_score > 0.3 else None

def cmd_fix(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents(path)
    outbound, doc_info = _build_link_graph(path)
    existing_stems = set(doc_info.keys())

    # Collect all fixes
    fixes = []

    # Fix 1: Broken links
    for d in docs:
        if d["category"] == "raw":
            continue
        text = d.get("_text", "")
        if not text:
            continue
        for m in re.finditer(r"\[\[(.+?)\]\]", text):
            original = m.group(1)
            target_stem = original.strip().lower().replace(" ", "-")
            if target_stem not in existing_stems:
                closest = _find_closest(target_stem, list(existing_stems))
                fixes.append({
                    "type": "broken_link",
                    "file": d["file"],
                    "original": original,
                    "target_stem": target_stem,
                    "suggestion": closest,
                    "action": f"[[{original}]] → [[{doc_info[closest]['title']}]]" if closest else f"[[{original}]] → (删除或创建目标页面)",
                })

    # Fix 2: Naming inconsistency in wikilinks (underscores, mixed case)
    for d in docs:
        if d["category"] == "raw":
            continue
        text = d.get("_text", "")
        if not text:
            continue
        for m in re.finditer(r"\[\[(.+?)\]\]", text):
            original = m.group(1)
            # Check for underscores
            if "_" in original:
                normalized = original.replace("_", "-")
                fixes.append({
                    "type": "normalize",
                    "file": d["file"],
                    "original": original,
                    "target_stem": normalized.strip().lower().replace(" ", "-"),
                    "suggestion": normalized,
                    "action": f"[[{original}]] → [[{normalized}]]",
                })

    # Deduplicate
    seen = set()
    unique_fixes = []
    for f in fixes:
        key = (f["type"], f["file"], f["original"])
        if key not in seen:
            seen.add(key)
            unique_fixes.append(f)
    fixes = unique_fixes

    if args.format == "json":

        meta = read_schema_meta(path)
        output = {
            "wiki": meta,
            "total": len(fixes),
            "dry_run": not args.apply,
            "fixes": fixes,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    # Table format
    interactive = getattr(args, "interactive", False)
    if args.apply:
        mode = "交互执行" if interactive else "执行"
    else:
        mode = "预览"
    print(f"\n🔧 自愈检查 — {mode}模式")
    print(f"   发现 {len(fixes)} 个可修复项\n")

    if not fixes:
        print("   ✅ 没有发现可自动修复的结构问题。")
        return

    # Group by type
    broken = [f for f in fixes if f["type"] == "broken_link"]
    norm = [f for f in fixes if f["type"] == "normalize"]

    skip_types: set[str] = set()
    applied_count = 0
    skipped_count = 0

    def _apply_fix(fix: dict, skip_label: str) -> str:
        """Apply a single fix with optional interactive confirmation. Returns 'applied'/'skipped'/'skip_remaining'."""
        nonlocal applied_count, skipped_count
        if interactive and fix["type"] not in skip_types:
            status = "✅ 可修复" if fix["suggestion"] else "⚠️  需手动"
            print(f"   {status}  {fix['file']}: {fix['action']}")
            try:
                ans = input(f"   确认? [y/n/s=跳过剩余{skip_label}] ").strip().lower()
            except EOFError:
                ans = "y"
            if ans == "s":
                skip_types.add(fix["type"])
                skipped_count += 1
                print(f"   ⏭️  跳过剩余{skip_label}")
                return "skip_remaining"
            elif ans == "n":
                skipped_count += 1
                print(f"   ⏭️  已跳过")
                return "skipped"

        filepath = path / fix["file"]
        text = filepath.read_text(encoding="utf-8")
        if fix["suggestion"]:
            info = doc_info[fix["suggestion"]]
            new_text = text.replace(f"[[{fix['original']}]]", f"[[{info['title']}]]")
            filepath.write_text(new_text, encoding="utf-8")
            print(f"   ✅ {fix['file']}: {fix['action']}")
            applied_count += 1
        else:
            print(f"   ⏭️  {fix['file']}: {fix['action']} (需手动处理)")
        return "applied"

    if broken:
        print(f"   ── 断链修复 ({len(broken)} 处) ──")
        for f in broken:
            if args.apply:
                _apply_fix(f, "断链修复")
            else:
                status = "✅ 可修复" if f["suggestion"] else "⚠️  需手动"
                print(f"   {status}  {f['file']}: {f['action']}")
        print()

    if norm:
        print(f"   ── 命名规范化 ({len(norm)} 处) ──")
        for f in norm:
            if args.apply:
                _apply_fix(f, "规范化")
            else:
                print(f"   ✅ 可修复  {f['file']}: {f['action']}")
        print()

    if not args.apply:
        auto_count = len([f for f in fixes if f["suggestion"]])
        manual_count = len(fixes) - auto_count
        print(f"   💡 {auto_count} 项可自动修复，{manual_count} 项需手动处理。")
        print(f"      使用 --apply 执行自动修复。")
        if not getattr(args, "interactive", False):
            print(f"      使用 --interactive 逐条确认。")
    elif getattr(args, "interactive", False):
        print(f"   已应用 {applied_count} 项，跳过 {skipped_count} 项。")

def cmd_rename(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    old_name = args.old_name
    new_name = args.new_name

    # Normalize stems
    old_stem = old_name.strip().lower().replace(" ", "-")
    new_stem = new_name.strip().lower().replace(" ", "-")
    new_title = new_name.strip().replace("-", " ").title()

    # Find the source document
    docs = collect_documents(path)
    source_doc = None
    for d in docs:
        stem = Path(d["file"]).stem.lower()
        if stem == old_stem:
            source_doc = d
            break
    if not source_doc:
        print(f"❌ 未找到文档: {old_name}")
        sys.exit(1)

    old_title = source_doc["title"]

    # Collect all rename actions
    actions = []

    # 1. Rename file action
    old_rel = source_doc["file"]
    new_rel = str(Path(old_rel).parent / (new_stem + ".md"))
    actions.append({
        "type": "rename_file",
        "file": old_rel,
        "original": old_rel,
        "new": new_rel,
    })

    # 2. Scan all docs for wikilink references to old name
    for d in docs:
        text = d.get("_text", "")
        for m in re.finditer(r"\[\[(.+?)\]\]", text):
            link_target = m.group(1).strip().lower().replace(" ", "-")
            if link_target == old_stem:
                actions.append({
                    "type": "update_link",
                    "file": d["file"],
                    "original": f"[[{m.group(1)}]]",
                    "new": f"[[{new_title}]]",
                })

    # 3. Update internal heading if it matches old title
    for line_no, line in enumerate(source_doc.get("_text", "").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            heading = stripped[2:]
            if heading == old_title:
                actions.append({
                    "type": "update_heading",
                    "file": old_rel,
                    "original": f"# {old_title}",
                    "new": f"# {new_title}",
                })

    if args.format == "json":

        meta = read_schema_meta(path)
        output = {
            "wiki": meta,
            "old": old_name,
            "new": new_name,
            "dry_run": not getattr(args, "apply", False),
            "total": len(actions),
            "actions": actions,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    print(f"\n📝 重命名: [[{old_title}]] → [[{new_title}]]")
    print(f"   影响 {len(actions)} 处\n")

    if not actions:
        print("   ✅ 无需修改。")
        return

    for a in actions:
        print(f"   {a['type']}: {a['original']} → {a['new']}")

    if getattr(args, "apply", False):
        # Update links in all files FIRST (before renaming source file)
        files_to_update: set[str] = set()
        for a in actions:
            if a["type"] in ("update_link", "update_heading"):
                files_to_update.add(a["file"])

        for f in files_to_update:
            fp = path / f
            text = fp.read_text(encoding="utf-8")
            for a in actions:
                if a["file"] == f:
                    text = text.replace(a["original"], a["new"])
            fp.write_text(text, encoding="utf-8")
            print(f"   ✅ 已更新: {f}")

        # Rename file AFTER content updates
        old_path = path / old_rel
        new_path = path / new_rel
        old_path.rename(new_path)
        print(f"\n   ✅ 文件已重命名: {old_rel} → {new_rel}")
        print(f"\n   重命名完成！")
    else:
        print(f"\n   💡 使用 --apply 执行重命名。")

def cmd_tags(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents(path)

    # Build tag index (exclude raw/)
    tag_map: dict[str, dict] = {}
    for d in docs:
        if d["category"] == "raw":
            continue
        for t in d.get("tags", []):
            t = t.strip()
            if not t:
                continue
            if t not in tag_map:
                tag_map[t] = {"tag": t, "count": 0, "documents": []}
            tag_map[t]["count"] += 1
            tag_map[t]["documents"].append(d["file"])

    tags = list(tag_map.values())

    # Sort
    sort_by = getattr(args, "sort", "count")
    if sort_by == "name":
        tags.sort(key=lambda t: t["tag"].lower())
    else:
        tags.sort(key=lambda t: (-t["count"], t["tag"].lower()))

    if args.format == "json":

        meta = read_schema_meta(path)
        output = {
            "wiki": meta,
            "total": len(tags),
            "tags": tags,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    meta = read_schema_meta(path)
    print(f"\n🏷️  {meta['name']} — 标签列表")
    print(f"   共 {len(tags)} 个标签\n")

    if not tags:
        print("   没有找到标签。")
        return

    for t in tags:
        example = ""
        if t["documents"]:
            example = t["documents"][0]
            if len(t["documents"]) > 1:
                example += f" 等 {len(t['documents'])} 篇"
        print(f"   {t['tag']:<20}  {t['count']:>3} 次  {example}")

def cmd_stats(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents(path)
    backlinks = build_backlink_map(path)

    # Category breakdown
    cat_count: dict[str, int] = {}
    for d in docs:
        cat_count[d["category"]] = cat_count.get(d["category"], 0) + 1

    # Tag stats
    tag_count: dict[str, int] = {}
    total_tags = 0
    for d in docs:
        for t in d.get("tags", []):
            t = t.strip()
            if t:
                tag_count[t] = tag_count.get(t, 0) + 1
                total_tags += 1

    # Link density
    total_links = sum(d["links_count"] for d in docs)
    link_density = total_links / len(docs) if docs else 0.0

    # Orphan count
    orphan_count = 0
    for d in docs:
        if d["category"] == "raw":
            continue
        stem = Path(d["file"]).stem.lower()
        if stem in SYSTEM_FILES:
            continue
        if stem not in backlinks or len(backlinks[stem]) == 0:
            orphan_count += 1

    # Total size and latest modification
    total_size = 0
    latest_mod = ""
    for d in docs:
        total_size += d["size"]
        if d["modified"] > latest_mod:
            latest_mod = d["modified"]

    unique_tags = len(tag_count)

    if args.format == "json":

        meta = read_schema_meta(path)
        cat_breakdown = {}
        for cat, count in cat_count.items():
            cat_breakdown[cat] = {
                "label": CATEGORY_LABELS.get(cat, cat),
                "count": count,
            }
        output = {
            "wiki": meta,
            "total_documents": len(docs),
            "categories": cat_breakdown,
            "unique_tags": unique_tags,
            "total_tag_uses": total_tags,
            "link_density": link_density,
            "orphan_count": orphan_count,
            "total_size_bytes": total_size,
            "latest_modified": latest_mod,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    meta = read_schema_meta(path)
    print(f"\n📊 {meta['name']} — 知识库统计")
    print(f"\n   文档总数: {len(docs)}")
    for cat in DIRS:
        count = cat_count.get(cat, 0)
        if count > 0:
            print(f"     {CATEGORY_LABELS.get(cat, cat) + '/':<12} {count} 篇")

    print(f"\n   标签统计:")
    print(f"     唯一标签: {unique_tags}")
    print(f"     标签使用: {total_tags} 次")

    print(f"\n   链接密度: {link_density:.1f} 条/文档")
    print(f"   孤立文档: {orphan_count} 篇", end="")
    if docs:
        print(f" ({orphan_count * 100 / len(docs):.0f}%)")
    else:
        print()

    print(f"   总文件大小: {total_size} 字节", end="")
    if total_size > 1024 * 1024:
        print(f" ({total_size / 1024 / 1024:.1f} MB)")
    elif total_size > 1024:
        print(f" ({total_size / 1024:.1f} KB)")
    else:
        print()

    if latest_mod:
        print(f"   最近修改: {latest_mod}")

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
    p_search.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_backlinks = sub.add_parser("backlinks", help="查看页面的反向链接")
    p_backlinks.add_argument("page", help="目标页面名 (如 transformer-architecture)")
    p_backlinks.add_argument("path", nargs="?", default=".")
    p_backlinks.add_argument("--format", default="table", choices=["table", "json"])
    p_backlinks.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

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

    p_tags = sub.add_parser("tags", help="列出所有标签及使用统计")
    p_tags.add_argument("path", nargs="?", default=".")
    p_tags.add_argument("--format", default="table", choices=["table", "json"])
    p_tags.add_argument("--sort", default="count", choices=["count", "name"], help="排序方式")
    p_tags.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

    p_stats = sub.add_parser("stats", help="知识库概览统计")
    p_stats.add_argument("path", nargs="?", default=".")
    p_stats.add_argument("--format", default="table", choices=["table", "json"])
    p_stats.add_argument("--pretty", action="store_true", help="JSON 缩进美化")

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
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "index":
        cmd_index(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "backlinks":
        cmd_backlinks(args)
    elif args.command == "orphans":
        cmd_orphans(args)
    elif args.command == "health":
        cmd_health(args)
    elif args.command == "trace":
        cmd_trace(args)
    elif args.command == "fix":
        cmd_fix(args)
    elif args.command == "rename":
        cmd_rename(args)
    elif args.command == "tags":
        cmd_tags(args)
    elif args.command == "stats":
        cmd_stats(args)

if __name__ == "__main__":
    main()
