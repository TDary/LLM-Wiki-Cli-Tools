"""Commands: list, index, search, backlinks, tags, stats."""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

from . import DIRS, CATEGORY_LABELS, SYSTEM_FILES
from .helpers import (
    expand, require_wiki, now, collect_documents, collect_documents_cached, clear_doc_cache, read_schema_meta,
    search_documents, build_backlink_map, _strip_internal,
    extract_frontmatter_from_text, extract_title, _lazy_load_text,
)


def cmd_list(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents_cached(path)

    if hasattr(args, "category") and args.category:
        docs = [d for d in docs if d["category"] == args.category]
    elif not getattr(args, "include_raw", False):
        docs = [d for d in docs if d["category"] not in ("raw", "normalized")]

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
        readonly = "  🔒只读" if d["category"] in ("raw", "normalized") else ""
        print(f"    {d['title']}")
        print(f"    ├─ {d['file']}  ({d['size']}B, {d['modified']}){tags_str}{links_str}{readonly}")
        print()


def cmd_index(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents_cached(path)
    meta = read_schema_meta(path)

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

    all_tags = set()
    for d in docs:
        for t in d.get("tags", []):
            all_tags.add(t)

    # Build inverted index for search acceleration
    inverted: dict[str, list[dict]] = {}
    for d in docs:
        text = d.get("_text")
        if text is None:
            text = _lazy_load_text(d, path)
        for line_no, line in enumerate(text.splitlines(), 1):
            words = set(re.findall(r"\w{2,}", line.lower()))
            for w in words:
                if w not in inverted:
                    inverted[w] = []
                inverted[w].append({"file": d["file"], "line": line_no})

    latest_modified = max((d["modified"] for d in docs), default="")

    index = {
        "wiki": meta,
        "generated_at": now(),
        "total_documents": len(docs),
        "latest_modified": latest_modified,
        "categories": [by_category[k] for k in DIRS if k in by_category],
        "tags": sorted(all_tags),
        "inverted_index": inverted,
    }

    output_path = expand(args.output or str(path / "queries" / "index.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    indent = 2 if args.pretty else None
    output_path.write_text(json.dumps(index, ensure_ascii=False, indent=indent), encoding="utf-8")
    clear_doc_cache()

    print(f"✅ 索引已生成: {output_path}")
    print(f"   文档总数: {len(docs)}")
    print(f"   分类数: {len(by_category)}")
    print(f"   标签: {', '.join(sorted(all_tags)) if all_tags else '无'}")
    print(f"   倒排索引: {len(inverted)} 词 → {sum(len(v) for v in inverted.values())} 条目")
    print(f"\n   💡 使用 search --use-index 可加速搜索")


def _try_index_search(path: Path, keyword: str, docs: list[dict], no_raw: bool = False) -> list[dict] | None:
    """Try inverted-index search. Returns results or None if index unavailable/stale."""
    index_path = path / "queries" / "index.json"
    if not index_path.exists():
        return None

    try:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    inv = idx.get("inverted_index")
    if not inv:
        return None

    # Freshness: index mtime must be >= latest actual file mtime
    index_mtime = os.path.getmtime(index_path)
    for d in DIRS:
        cat_dir = path / d
        if not cat_dir.is_dir():
            continue
        for md_file in cat_dir.glob("*.md"):
            if md_file.stat().st_mtime > index_mtime:
                return None

    kw_lower = keyword.lower()
    entries = inv.get(kw_lower, [])
    if not entries:
        return []

    if no_raw:
        raw_prefixes = ("raw/", "raw\\", "normalized/", "normalized\\")
        entries = [e for e in entries if not e["file"].startswith(raw_prefixes)]

    # Group entries by file, dedup line numbers
    by_file: dict[str, set[int]] = {}
    for e in entries:
        by_file.setdefault(e["file"], set()).add(e["line"])

    results = []
    for filepath, target_lines in by_file.items():
        fp = path / filepath
        # Path traversal guard: resolved path must stay within wiki directory
        try:
            fp.resolve().relative_to(path.resolve())
        except ValueError:
            continue
        if not fp.exists():
            continue
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = text.splitlines()
        fm = extract_frontmatter_from_text(text)
        title = fm.get("title") or extract_title(fp)
        tags = fm.get("tags", [])

        matches = []
        for line_no in sorted(target_lines):
            if 1 <= line_no <= len(lines):
                content = lines[line_no - 1].strip()
                if kw_lower in content.lower():
                    matches.append({"line": line_no, "content": content})

        if matches:
            results.append({
                "title": title,
                "file": filepath,
                "absolute_path": str(fp.resolve()).replace("\\", "/"),
                "category": filepath.split("/")[0] if "/" in filepath else filepath.split("\\")[0],
                "tags": tags,
                "matches": matches,
                "match_count": len(matches),
            })

    return results


def cmd_search(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents_cached(path)

    if getattr(args, "no_raw", False):
        docs = [d for d in docs if d["category"] not in ("raw", "normalized")]

    # Try inverted index first (non-regex only)
    use_index = getattr(args, "use_index", False)
    results = None
    if use_index and not getattr(args, "regex", False):
        results = _try_index_search(path, args.keyword, docs, getattr(args, "no_raw", False))

    # Fallback: full scan
    if results is None:
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

    page = args.page
    if page.endswith(".md"):
        page = page[:-3]
    target_stem = page.strip().lower().replace(" ", "-")

    backlinks = build_backlink_map(path, collect_documents_cached(path))
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


def cmd_tags(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents_cached(path)

    tag_map: dict[str, dict] = {}
    for d in docs:
        if d["category"] in ("raw", "normalized"):
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

    docs = collect_documents_cached(path)
    backlinks = build_backlink_map(path, docs)

    cat_count: dict[str, int] = {}
    for d in docs:
        cat_count[d["category"]] = cat_count.get(d["category"], 0) + 1

    tag_count: dict[str, int] = {}
    total_tags = 0
    for d in docs:
        for t in d.get("tags", []):
            t = t.strip()
            if t:
                tag_count[t] = tag_count.get(t, 0) + 1
                total_tags += 1

    total_links = sum(d["links_count"] for d in docs)
    link_density = total_links / len(docs) if docs else 0.0

    orphan_count = 0
    for d in docs:
        if d["category"] in ("raw", "normalized"):
            continue
        stem = Path(d["file"]).stem.lower()
        if stem in SYSTEM_FILES:
            continue
        if stem not in backlinks or len(backlinks[stem]) == 0:
            orphan_count += 1

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
