"""Commands: health, orphans, trace, fix, rename."""

import argparse
import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import DIRS, SYSTEM_FILES
from .helpers import (
    expand, require_wiki, today, collect_documents_cached, clear_doc_cache, read_schema_meta,
    build_backlink_map, build_link_graph, trace_graph, find_closest,
    read_health_config, read_custom_checks, _strip_internal,
    extract_frontmatter_from_text, _extract_yaml_block, _parse_yaml_kv_pairs,
    append_to_log, _lazy_load_text,
)


REQUIRED_FRONTMATTER = {"title", "created", "updated", "type", "tags", "sources"}
VALID_TYPES = {"entity", "concept", "comparison", "query", "summary"}


def _ensure_text(docs: list[dict], wiki_path: Path) -> None:
    """Load _text for any docs that have None (from index-based cache)."""
    for d in docs:
        if d.get("_text") is None:
            _lazy_load_text(d, wiki_path)


def _read_tag_taxonomy(wiki_path: Path) -> set[str]:
    """Read tag taxonomy from SCHEMA.md."""
    yaml_lines = _extract_yaml_block(wiki_path, "标签体系")
    tags = set()
    for line in yaml_lines:
        line = line.strip()
        if line.startswith("- type:"):
            tags.add(line.split(":", 1)[1].strip())
    return tags


def cmd_orphans(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents_cached(path)
    _ensure_text(docs, path)
    backlinks = build_backlink_map(path, docs)

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

    docs = collect_documents_cached(path)
    _ensure_text(docs, path)
    backlinks = build_backlink_map(path, docs)
    weights = read_health_config(path)

    user_docs = [d for d in docs if d["category"] != "raw" and Path(d["file"]).stem.lower() not in SYSTEM_FILES]
    existing_stems = {Path(d["file"]).stem.lower() for d in docs}

    # ── Structural checks (1-6) ──

    # Check 1: Orphan documents
    orphans = []
    for d in user_docs:
        stem = Path(d["file"]).stem.lower()
        if stem not in backlinks or len(backlinks[stem]) == 0:
            orphans.append(d)

    # Check 2: Broken wikilinks
    broken_links = []
    for d in user_docs:
        text = d.get("_text") or ""
        if not text:
            try:
                text = Path(d["absolute_path"]).read_text(encoding="utf-8")
            except Exception:
                continue
        for m in re.finditer(r"\[\[(.+?)\]\]", text):
            target = m.group(1).strip().lower().replace(" ", "-")
            if target not in existing_stems:
                line_no = text[:m.start()].count("\n") + 1
                broken_links.append({
                    "source_file": d["file"],
                    "source_title": d["title"],
                    "target": m.group(1),
                    "line": line_no,
                })

    # Check 3: No tags
    no_tags = [d for d in user_docs if not d.get("tags")]

    # Check 4: Low links
    low_links = [d for d in user_docs if d["links_count"] < 2]

    # Check 5: Empty documents
    empty_docs = [d for d in user_docs if len(d.get("_text") or "".strip()) < 50]

    # Check 6: Self-referential links
    self_links = []
    for d in user_docs:
        self_stem = Path(d["file"]).stem.lower()
        text = d.get("_text") or ""
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

    # ── Content quality checks (7-10) ──

    # Check 7: Frontmatter validation
    tag_taxonomy = _read_tag_taxonomy(path)
    fm_errors: list[dict] = []
    fm_warnings: list[dict] = []
    for d in user_docs:
        rel_file = d["file"]
        text = d.get("_text") or ""
        fm = extract_frontmatter_from_text(text)

        if not fm:
            fm_errors.append({"file": rel_file, "issue": "缺少 frontmatter"})
            continue

        for field in REQUIRED_FRONTMATTER:
            if field not in fm:
                fm_errors.append({"file": rel_file, "issue": f"缺少字段: {field}"})

        if "type" in fm and fm["type"] not in VALID_TYPES:
            fm_errors.append({"file": rel_file, "issue": f"无效 type: {fm['type']}"})

        for date_field in ("created", "updated"):
            if date_field in fm and not re.match(r"^\d{4}-\d{2}-\d{2}", fm[date_field]):
                fm_warnings.append({"file": rel_file, "issue": f"日期格式: {date_field}={fm[date_field]}"})

        if tag_taxonomy and "tags" in fm:
            for tag in fm["tags"]:
                if tag and tag not in tag_taxonomy:
                    fm_warnings.append({"file": rel_file, "issue": f"标签不在体系中: {tag}"})

    # Check 8: Index completeness
    index_issues: list[dict] = []
    index_path = path / "index.md"
    if index_path.exists():
        try:
            index_text = index_path.read_text(encoding="utf-8")
            index_links = set()
            for m in re.finditer(r"\[\[(.+?)\]\]", index_text):
                index_links.add(m.group(1).strip().lower().replace(" ", "-"))
            for d in user_docs:
                stem = Path(d["file"]).stem.lower()
                if stem not in index_links:
                    index_issues.append({"file": d["file"], "issue": "未在 index.md 中"})
        except Exception:
            pass

    # Check 9: Stale content (>90 days)
    stale_docs: list[dict] = []
    cutoff = datetime.now() - timedelta(days=90)
    for d in user_docs:
        fm = extract_frontmatter_from_text(d.get("_text") or "")
        if "updated" in fm:
            try:
                updated = datetime.strptime(fm["updated"][:10], "%Y-%m-%d")
                if updated < cutoff:
                    days_old = (datetime.now() - updated).days
                    stale_docs.append({"file": d["file"], "days": days_old})
            except ValueError:
                pass

    # Check 10: Log rotation
    log_path = path / "log.md"
    log_entries = 0
    log_needs_rotation = False
    if log_path.exists():
        try:
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("- ") and not line.strip().startswith("- 🎉"):
                    log_entries += 1
            log_needs_rotation = log_entries > 500
        except Exception:
            pass

    # Check 11: Potential contradictions (pages sharing tags/entities)
    contradictions: list[dict] = []
    # Build tag → pages map
    tag_pages: dict[str, list[str]] = {}
    for d in user_docs:
        for tag in d.get("tags", []):
            if tag:
                tag_pages.setdefault(tag, []).append(d["file"])

    # Build entity → pages map (pages that link to the same targets)
    outbound_map, _ = build_link_graph(path, docs)
    stem_to_file = {Path(d["file"]).stem.lower(): d["file"] for d in user_docs}
    entity_pages: dict[str, list[str]] = {}
    for stem, targets in outbound_map.items():
        source_file = stem_to_file.get(stem)
        if not source_file:
            continue
        for target in targets:
            entity_pages.setdefault(target, []).append(source_file)

    # Find pages with same tags that might contradict
    for tag, pages in tag_pages.items():
        if len(pages) >= 2:
            # Check if these pages have different titles (potential different perspectives)
            titles = []
            for p in pages:
                for d in user_docs:
                    if d["file"] == p:
                        titles.append(d["title"])
                        break
            # Only flag if there are multiple distinct pages with same tag
            if len(set(titles)) >= 2:
                contradictions.append({
                    "type": "shared_tag",
                    "tag": tag,
                    "pages": pages[:5],  # Limit to 5 pages
                    "count": len(pages),
                })

    # Find pages that reference the same entities (potential overlapping content)
    for entity, pages in entity_pages.items():
        unique_pages = list(set(pages))
        if len(unique_pages) >= 2:
            contradictions.append({
                "type": "shared_entity",
                "entity": entity,
                "pages": unique_pages[:5],
                "count": len(unique_pages),
            })

    # Limit contradictions to top 10
    contradictions = contradictions[:10]

    # Check 12: Page size (>200 lines)
    large_pages: list[dict] = []
    for d in user_docs:
        text = d.get("_text") or ""
        line_count = len(text.splitlines())
        if line_count > 200:
            large_pages.append({"file": d["file"], "lines": line_count})

    # Check 13: Tag audit
    all_used_tags: set[str] = set()
    for d in user_docs:
        for tag in d.get("tags", []):
            if tag:
                all_used_tags.add(tag)
    unregistered_tags = all_used_tags - tag_taxonomy if tag_taxonomy else set()

    # ── Custom checks ──
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
                    shlex.split(cmd), shell=False, capture_output=True, text=True,
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

    # ── Score calculation ──
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

    def status_icon(count: int, threshold: int = 0) -> str:
        if count == 0:
            return "✅"
        elif count <= threshold:
            return "⚠️"
        else:
            return "❌"

    # ── JSON output ──
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
                "frontmatter": {
                    "errors": len(fm_errors),
                    "warnings": len(fm_warnings),
                    "items": fm_errors + fm_warnings,
                },
                "index_missing": {"count": len(index_issues), "items": index_issues},
                "stale_content": {"count": len(stale_docs), "items": stale_docs},
                "log_rotation": {
                    "entries": log_entries,
                    "needs_rotation": log_needs_rotation,
                },
                "contradictions": {"count": len(contradictions), "items": contradictions},
                "large_pages": {"count": len(large_pages), "items": large_pages},
                "tag_audit": {
                    "used": sorted(all_used_tags),
                    "unregistered": sorted(unregistered_tags),
                },
                "custom": custom_results,
            },
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    # ── Table output ──
    meta = read_schema_meta(path)
    print(f"\n🏥 {meta['name']} — 知识库健康报告")
    print(f"   文档总数: {len(user_docs)}\n")

    # Structural checks
    print(f"   ── 结构检查 ──")
    print(f"   {status_icon(len(orphans), 5)} 孤立文档:     {len(orphans)} 篇 (权重 {weights.get('orphan', 3)})")
    print(f"   {status_icon(len(broken_links))} 断链:         {len(broken_links)} 处 (权重 {weights.get('broken_link', 5)})")
    print(f"   {status_icon(len(no_tags), 5)} 无标签文档:   {len(no_tags)} 篇 (权重 {weights.get('no_tag', 1)})")
    print(f"   {status_icon(len(low_links), 5)} 链接不足:     {len(low_links)} 篇 (< 2 条链接, 权重 {weights.get('low_link', 2)})")
    print(f"   {status_icon(len(empty_docs), 3)} 空文档:       {len(empty_docs)} 篇 (< 50 字节, 权重 {weights.get('empty_doc', 2)})")
    print(f"   {status_icon(len(self_links))} 自引用:       {len(self_links)} 处 (权重 {weights.get('self_link', 1)})")

    # Content quality checks
    print(f"\n   ── 内容质量 ──")
    fm_total = len(fm_errors) + len(fm_warnings)
    print(f"   {status_icon(len(fm_errors))} Frontmatter:  {len(fm_errors)} 错误, {len(fm_warnings)} 警告")
    print(f"   {status_icon(len(index_issues), 3)} Index 缺失:   {len(index_issues)} 个页面未收录")
    print(f"   {status_icon(len(stale_docs), 5)} 过期内容:     {len(stale_docs)} 个页面 >90 天未更新")
    log_icon = "⚠️" if log_needs_rotation else "✅"
    print(f"   {log_icon} 日志条目:     {log_entries} 条" + (" (建议轮转)" if log_needs_rotation else ""))
    contra_icon = "⚠️" if contradictions else "✅"
    print(f"   {contra_icon} 潜在矛盾:     {len(contradictions)} 组页面需审查")
    large_icon = "⚠️" if large_pages else "✅"
    print(f"   {large_icon} 页面过大:     {len(large_pages)} 篇 >200 行（建议拆分）")
    tag_icon = "⚠️" if unregistered_tags else "✅"
    print(f"   {tag_icon} 标签审计:     {len(unregistered_tags)} 个未注册标签")

    # Custom checks
    for cr in custom_results:
        icon = "✅" if cr["count"] == 0 else "⚠️"
        print(f"   {icon} {cr['name']:<14} {cr['count']} 处 (权重 {cr['weight']})")

    print(f"\n   健康评分: {score}/100")

    # ── Details ──
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
            text = d.get("_text") or ""
            print(f"   📄 {d['title']}  ({d['file']}, {len(text.strip())} 字节)")
        if len(empty_docs) > 10:
            print(f"   ... 共 {len(empty_docs)} 篇空文档")

    if self_links:
        print(f"\n   ── 自引用 ──")
        for sl in self_links[:10]:
            print(f"   🔄 {sl['file']} (L{sl['line']}): [[{sl['link']}]] → 自身")
        if len(self_links) > 10:
            print(f"   ... 共 {len(self_links)} 处自引用")

    if fm_errors:
        print(f"\n   ── Frontmatter 错误 ──")
        for item in fm_errors[:10]:
            print(f"   ❌ {item['file']}: {item['issue']}")
        if len(fm_errors) > 10:
            print(f"   ... 共 {len(fm_errors)} 个错误")

    if stale_docs:
        print(f"\n   ── 过期内容 ──")
        for item in stale_docs[:10]:
            print(f"   📅 {item['file']}: {item['days']} 天未更新")
        if len(stale_docs) > 10:
            print(f"   ... 共 {len(stale_docs)} 个页面")

    if contradictions:
        print(f"\n   ── 潜在矛盾（需人工审查）──")
        for c in contradictions[:5]:
            if c["type"] == "shared_tag":
                pages_str = ", ".join(c["pages"][:3])
                if len(c["pages"]) > 3:
                    pages_str += f" 等 {c['count']} 篇"
                print(f"   🏷️  共享标签 [{c['tag']}]: {pages_str}")
            elif c["type"] == "shared_entity":
                pages_str = ", ".join(c["pages"][:3])
                if len(c["pages"]) > 3:
                    pages_str += f" 等 {c['count']} 篇"
                print(f"   🔗 共享实体 [[{c['entity']}]]: {pages_str}")
        if len(contradictions) > 5:
            print(f"   ... 共 {len(contradictions)} 组")

    if large_pages:
        print(f"\n   ── 页面过大（建议拆分）──")
        for item in large_pages[:10]:
            print(f"   📄 {item['file']}: {item['lines']} 行")
        if len(large_pages) > 10:
            print(f"   ... 共 {len(large_pages)} 篇")

    if unregistered_tags:
        print(f"\n   ── 未注册标签 ──")
        for tag in sorted(unregistered_tags)[:10]:
            print(f"   🏷️  {tag} — 需添加到 SCHEMA.md 标签体系")
        if len(unregistered_tags) > 10:
            print(f"   ... 共 {len(unregistered_tags)} 个")

    for cr in custom_results:
        if cr["count"] > 0:
            print(f"\n   ── {cr['name']} ──")
            for issue in cr["issues"][:10]:
                print(f"   ⚠️  {issue}")
            if len(cr["issues"]) > 10:
                print(f"   ... 共 {len(cr['issues'])} 处")

    # ── Suggestions ──
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
    if fm_errors:
        issues.append("修复 frontmatter 错误（缺少必填字段或格式错误）")
    if index_issues:
        issues.append("将未收录页面添加到 index.md")
    if log_needs_rotation:
        issues.append(f"日志轮转: log.md 有 {log_entries} 条记录，建议归档")
    if contradictions:
        issues.append(f"审查 {len(contradictions)} 组潜在矛盾页面（共享标签/实体）")
    if large_pages:
        issues.append(f"拆分 {len(large_pages)} 篇超过 200 行的页面")
    if unregistered_tags:
        issues.append(f"将 {len(unregistered_tags)} 个标签添加到 SCHEMA.md 标签体系")
    for cr in custom_results:
        if cr["count"] > 0:
            issues.append(f"{cr['name']}: {cr['description']}")

    if issues:
        print(f"\n   💡 建议:")
        for i, issue in enumerate(issues, 1):
            print(f"      {i}. {issue}")
    else:
        print(f"\n   🎉 知识库状态良好，没有发现明显问题。")

    # ── Log the health check ──
    total_issues = len(orphans) + len(broken_links) + len(no_tags) + len(low_links) + len(empty_docs) + len(self_links) + len(fm_errors) + len(index_issues) + len(stale_docs) + len(contradictions) + len(large_pages) + len(unregistered_tags)
    append_to_log(path, f"health | score {score}/100, {total_issues} issues", [
        f"Orphans: {len(orphans)}, Broken links: {len(broken_links)}",
        f"FM errors: {len(fm_errors)}, Stale: {len(stale_docs)}, Contradictions: {len(contradictions)}",
    ])


def cmd_trace(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    page = args.page
    if page.endswith(".md"):
        page = page[:-3]
    target_stem = page.strip().lower().replace(" ", "-")

    docs = collect_documents_cached(path)
    _ensure_text(docs, path)
    outbound, doc_info = build_link_graph(path, docs)

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

    upstream = trace_graph(target_stem, outbound, set(), 1)
    downstream = trace_graph(target_stem, inbound, set(), 1)

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

    print(f"\n🔍 溯源: [[{page}]]")
    print(f"   {doc['title']}  ({doc['file']})")

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

    print(f"\n   上游引用: {len(set(i['stem'] for i in upstream))} 个")
    print(f"   下游被引: {len(set(i['stem'] for i in downstream))} 个")


def cmd_fix(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    docs = collect_documents_cached(path)
    _ensure_text(docs, path)
    outbound, doc_info = build_link_graph(path, docs)
    existing_stems = {k for k, v in doc_info.items() if v["category"] != "raw"}

    fixes = []

    # Fix 1: Broken links
    for d in docs:
        if d["category"] == "raw":
            continue
        text = d.get("_text") or ""
        if not text:
            continue
        for m in re.finditer(r"\[\[(.+?)\]\]", text):
            original = m.group(1)
            target_stem = original.strip().lower().replace(" ", "-")
            if target_stem not in existing_stems:
                closest = find_closest(target_stem, list(existing_stems))
                fixes.append({
                    "type": "broken_link",
                    "file": d["file"],
                    "original": original,
                    "target_stem": target_stem,
                    "suggestion": closest,
                    "action": f"[[{original}]] → [[{doc_info[closest]['title']}]]" if closest else f"[[{original}]] → (删除或创建目标页面)",
                })

    # Fix 2: Naming inconsistency
    for d in docs:
        if d["category"] == "raw":
            continue
        text = d.get("_text") or ""
        if not text:
            continue
        for m in re.finditer(r"\[\[(.+?)\]\]", text):
            original = m.group(1)
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

    mode = "执行" if args.apply else "预览"
    print(f"\n🔧 自愈检查 — {mode}模式")
    print(f"   发现 {len(fixes)} 个可修复项\n")

    if not fixes:
        print("   ✅ 没有发现可自动修复的结构问题。")
        return

    broken = [f for f in fixes if f["type"] == "broken_link"]
    norm = [f for f in fixes if f["type"] == "normalize"]

    applied_count = 0

    def _auto_apply(fix_list: list[dict]) -> None:
        """Auto-apply all fixes with suggestions, grouped by file."""
        nonlocal applied_count
        fixes_by_file: dict[str, list[dict]] = {}
        for f in fix_list:
            if f["suggestion"]:
                fixes_by_file.setdefault(f["file"], []).append(f)
            else:
                print(f"   ⏭️  {f['file']}: {f['action']} (需手动处理)")

        for filepath, file_fixes in fixes_by_file.items():
            fp = path / filepath
            text = fp.read_text(encoding="utf-8")
            for f in file_fixes:
                if f["suggestion"] and f["suggestion"] in doc_info:
                    info = doc_info[f["suggestion"]]
                    text = text.replace(f"[[{f['original']}]]", f"[[{info['title']}]]")
                elif f["suggestion"]:
                    text = text.replace(f"[[{f['original']}]]", f"[[{f['suggestion']}]]")
                print(f"   ✅ {f['file']}: {f['action']}")
                applied_count += 1
            fp.write_text(text, encoding="utf-8")

    def _print_dry_run(fix_list: list[dict]) -> None:
        for f in fix_list:
            status = "✅ 可修复" if f["suggestion"] else "⚠️  需手动"
            print(f"   {status}  {f['file']}: {f['action']}")

    if broken:
        print(f"   ── 断链修复 ({len(broken)} 处) ──")
        if args.apply:
            _auto_apply(broken)
        else:
            _print_dry_run(broken)
        print()

    if norm:
        print(f"   ── 命名规范化 ({len(norm)} 处) ──")
        if args.apply:
            _auto_apply(norm)
        else:
            _print_dry_run(norm)
        print()

    if not args.apply:
        auto_count = len([f for f in fixes if f["suggestion"]])
        manual_count = len(fixes) - auto_count
        print(f"   💡 {auto_count} 项可自动修复，{manual_count} 项需手动处理。")
        print(f"      使用 --apply 执行自动修复。")
    else:
        clear_doc_cache()
        print(f"   已应用 {applied_count} 项。")


def cmd_rename(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    old_name = args.old_name
    new_name = args.new_name

    old_stem = old_name.strip().lower().replace(" ", "-")
    new_stem = new_name.strip().lower().replace(" ", "-")
    new_title = new_name.strip().replace("-", " ").title()

    docs = collect_documents_cached(path)
    _ensure_text(docs, path)
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

    # 2. Scan for wikilink references
    for d in docs:
        text = d.get("_text") or ""
        for m in re.finditer(r"\[\[(.+?)\]\]", text):
            link_target = m.group(1).strip().lower().replace(" ", "-")
            if link_target == old_stem:
                actions.append({
                    "type": "update_link",
                    "file": d["file"],
                    "original": f"[[{m.group(1)}]]",
                    "new": f"[[{new_title}]]",
                })

    # 3. Update internal heading
    for line_no, line in enumerate((source_doc.get("_text") or "").splitlines(), 1):
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
        files_to_update: set[str] = set()
        for a in actions:
            if a["type"] in ("update_link", "update_heading"):
                files_to_update.add(a["file"])

        for f in files_to_update:
            fp = path / f
            text = fp.read_text(encoding="utf-8")
            for a in actions:
                if a["file"] == f and a["type"] in ("update_link", "update_heading"):
                    text = text.replace(a["original"], a["new"])
            fp.write_text(text, encoding="utf-8")
            print(f"   ✅ 已更新: {f}")

        old_path = path / old_rel
        new_path = path / new_rel
        old_path.rename(new_path)
        print(f"\n   ✅ 文件已重命名: {old_rel} → {new_rel}")
        clear_doc_cache()
        print(f"\n   重命名完成！")
    else:
        print(f"\n   💡 使用 --apply 执行重命名。")


def cmd_archive(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    page = args.page
    if page.endswith(".md"):
        page = page[:-3]
    target_stem = page.strip().lower().replace(" ", "-")

    # Find the source document
    docs = collect_documents_cached(path)
    _ensure_text(docs, path)
    source_doc = None
    for d in docs:
        if Path(d["file"]).stem.lower() == target_stem:
            source_doc = d
            break
    if not source_doc:
        print(f"❌ 未找到文档: {page}")
        sys.exit(1)

    # Don't archive source material.
    if source_doc["category"] in ("raw", "normalized"):
        print(f"❌ 不能归档 {source_doc['category']}/ 目录中的文件（原始资料不可变）")
        sys.exit(1)

    old_title = source_doc["title"]
    old_rel = source_doc["file"]

    # Build archive path: _archive/<category>/<filename>
    archive_dir = path / "_archive" / source_doc["category"]
    archive_rel = f"_archive/{source_doc['category']}/{Path(old_rel).name}"
    archive_path = archive_dir / Path(old_rel).name

    # Collect all actions
    actions = []

    # 1. Move file action
    actions.append({
        "type": "move_file",
        "original": old_rel,
        "new": archive_rel,
    })

    # 2. Scan all docs for wikilink references
    for d in docs:
        if d["file"] == old_rel:
            continue
        text = d.get("_text") or ""
        for m in re.finditer(r"\[\[(.+?)\]\]", text):
            link_target = m.group(1).strip().lower().replace(" ", "-")
            if link_target == target_stem:
                actions.append({
                    "type": "update_link",
                    "file": d["file"],
                    "original": f"[[{m.group(1)}]]",
                    "new": f"{old_title}（已归档）",
                })

    # 3. Remove from index.md
    index_path = path / "index.md"
    index_removed = False
    if index_path.exists():
        try:
            index_text = index_path.read_text(encoding="utf-8")
            # Find and remove lines containing [[page_title]]
            pattern = f"[[{old_title}]]"
            if pattern in index_text:
                actions.append({
                    "type": "update_index",
                    "file": "index.md",
                    "original": pattern,
                    "new": "",
                })
                index_removed = True
        except Exception:
            pass

    if args.format == "json":
        meta = read_schema_meta(path)
        output = {
            "wiki": meta,
            "page": page,
            "title": old_title,
            "dry_run": not getattr(args, "apply", False),
            "total": len(actions),
            "actions": actions,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    print(f"\n📦 归档: [[{old_title}]]")
    print(f"   来源: {old_rel}")
    print(f"   目标: {archive_rel}")
    print(f"   影响 {len(actions)} 处\n")

    if not actions:
        print("   ✅ 无需修改。")
        return

    for a in actions:
        if a["type"] == "move_file":
            print(f"   📁 移动: {a['original']} → {a['new']}")
        elif a["type"] == "update_link":
            content = a["original"]
            if len(content) > 40:
                content = content[:37] + "..."
            print(f"   🔗 更新: {a['file']}: {content} → 纯文本+已归档")
        elif a["type"] == "update_index":
            print(f"   📋 从 index.md 移除")

    if getattr(args, "apply", False):
        # 1. Create archive directory
        archive_dir.mkdir(parents=True, exist_ok=True)

        # 2. Update links in all files FIRST (before moving source file)
        files_to_update: set[str] = set()
        for a in actions:
            if a["type"] == "update_link":
                files_to_update.add(a["file"])

        for f in files_to_update:
            fp = path / f
            text = fp.read_text(encoding="utf-8")
            for a in actions:
                if a["file"] == f and a["type"] == "update_link":
                    text = text.replace(a["original"], a["new"])
            fp.write_text(text, encoding="utf-8")
            print(f"\n   ✅ 已更新: {f}")

        # 3. Remove from index.md
        if index_removed:
            try:
                index_text = index_path.read_text(encoding="utf-8")
                lines = index_text.splitlines()
                pattern = f"[[{old_title}]]"
                new_lines = [l for l in lines if pattern not in l]
                index_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                print(f"   ✅ 已从 index.md 移除")
            except Exception:
                pass

        # 4. Move file AFTER content updates
        old_path = path / old_rel
        old_path.rename(archive_path)
        print(f"   ✅ 已归档: {old_rel} → {archive_rel}")

        # 5. Log the action
        log_path = path / "log.md"
        try:
            from .helpers import today
            log_content = log_path.read_text(encoding="utf-8") if log_path.exists() else "# 更新日志\n\n"
            date_heading = f"## {today()}"
            if date_heading not in log_content:
                log_content = log_content.rstrip() + f"\n\n{date_heading}\n"
            log_content = log_content.rstrip() + f"\n- archive | {old_title}\n  From: {old_rel}\n  To: {archive_rel}\n"
            log_path.write_text(log_content, encoding="utf-8")
            print(f"   ✅ 日志已更新")
        except Exception:
            pass

        print(f"\n   归档完成！")
        clear_doc_cache()
    else:
        link_count = len([a for a in actions if a["type"] == "update_link"])
        print(f"\n   💡 将更新 {link_count} 处引用，移动文件到 _archive/。")
        print(f"      使用 --apply 执行归档。")
