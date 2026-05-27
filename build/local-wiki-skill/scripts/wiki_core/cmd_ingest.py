"""Command: ingest — Ingest external sources into the wiki."""

import argparse
import hashlib
import ipaddress
import json
import re
import socket
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener
from urllib.error import URLError, HTTPError

from . import DIRS, CATEGORY_LABELS
from .helpers import expand, require_wiki, now, today, collect_documents, clear_doc_cache, read_schema_meta, append_to_log, extract_title, extract_frontmatter_from_text
from .templates import template_wiki_page

# Security limits
_MAX_RESPONSE_BYTES = 50 * 1024 * 1024  # 50 MB
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_url(url: str) -> None:
    """Validate URL for safety. Raises ValueError on rejection."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不允许的 URL 协议: {parsed.scheme}（仅支持 http/https）")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL 缺少主机名")
    try:
        addr = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addr:
            ip = ipaddress.ip_address(sockaddr[0])
            # Unmap IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1 → 127.0.0.1)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            for net in _PRIVATE_NETWORKS:
                if ip in net:
                    raise ValueError(f"拒绝访问内网/保留地址: {ip} ({hostname})")
    except socket.gaierror:
        raise ValueError(f"无法解析主机名: {hostname}")


class _SSRFSafeRedirectHandler(HTTPRedirectHandler):
    """Redirect handler that validates each hop against SSRF rules."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# ── HTML to text converter ──

class _HTMLTextExtractor(HTMLParser):
    """Strip HTML to plain text, skipping script/style/nav/footer."""

    SKIP_TAGS = {"script", "style", "nav", "footer", "header", "noscript"}
    BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote", "br", "hr", "pre"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1
        elif self._skip_depth == 0 and tag.lower() in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif self._skip_depth == 0 and tag.lower() in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        # Collapse multiple newlines
        lines = []
        prev_empty = False
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                if not prev_empty:
                    lines.append("")
                    prev_empty = True
            else:
                lines.append(stripped)
                prev_empty = False
        return "\n".join(lines).strip()


def _html_to_text(html_content: str) -> str:
    """Convert HTML to plain text using stdlib html.parser."""
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html_content)
    except Exception:
        # Fallback: strip tags with regex (crude but safe)
        text = re.sub(r"<[^>]+>", " ", html_content)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    return parser.get_text()


def _fetch_url(url: str, timeout: int = 30) -> tuple[str, str, str]:
    """Fetch URL content. Returns (final_url, content_type, text)."""
    _validate_url(url)
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; wiki-tools/1.2)",
        "Accept": "text/html, text/plain, text/markdown, */*",
    })
    opener = build_opener(_SSRFSafeRedirectHandler)
    resp = opener.open(req, timeout=timeout)
    final_url = resp.geturl()
    content_type = resp.headers.get("Content-Type", "text/plain")

    # Detect encoding
    encoding = "utf-8"
    if "charset=" in content_type.lower():
        for part in content_type.split(";"):
            part = part.strip()
            if part.lower().startswith("charset="):
                encoding = part.split("=", 1)[1].strip().strip('"')
                break

    body = resp.read(_MAX_RESPONSE_BYTES + 1)
    if len(body) > _MAX_RESPONSE_BYTES:
        raise ValueError(f"响应体过大（超过 {_MAX_RESPONSE_BYTES // 1024 // 1024} MB 限制）")

    # Check if binary
    if not content_type.startswith("text/"):
        return final_url, content_type, body.decode(encoding, errors="replace")

    text = body.decode(encoding, errors="replace")

    # Convert HTML to plain text
    if "html" in content_type.lower() or text.strip().startswith("<"):
        text = _html_to_text(text)

    return final_url, content_type, text


def _slugify_url(url: str) -> str:
    """Convert URL to a filesystem-safe slug for naming raw/ files."""
    parsed = urlparse(url)
    # Use path component
    slug = parsed.path.strip("/")
    if not slug:
        slug = parsed.netloc
    # Replace special chars
    slug = re.sub(r"[^\w\s-]", "-", slug)
    slug = re.sub(r"[-\s]+", "-", slug).strip("-").lower()
    # Truncate
    if len(slug) > 80:
        slug = slug[:80].rstrip("-")
    if len(slug) < 3:
        # Fallback to hash
        h = hashlib.md5(url.encode()).hexdigest()[:8]
        slug = f"page-{h}"
    return slug


def _generate_filename(slug: str, wiki_path: Path, subdir: str = "raw") -> str:
    """Generate a unique filename, appending numeric suffix if needed."""
    base = f"{slug}.md"
    target = wiki_path / subdir / base
    if not target.exists():
        return base
    for i in range(2, 100):
        candidate = f"{slug}-{i}.md"
        target = wiki_path / subdir / candidate
        if not target.exists():
            return candidate
    # Last resort
    return f"{slug}-{hashlib.md5(slug.encode()).hexdigest()[:6]}.md"


def _extract_title_from_text(text: str) -> str:
    """Extract title from the first # heading or first line of text."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    # Fallback: first non-empty line, truncated
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) > 3:
            return stripped[:80]
    return ""


def _extract_keywords(text: str) -> list[str]:
    """Extract keywords from text for related-page suggestions."""
    # Extract from headings and bold text
    keywords = set()
    for m in re.finditer(r"#+\s*(.+)", text):
        keywords.add(m.group(1).strip().lower())
    for m in re.finditer(r"\*\*(.+?)\*\*", text):
        keywords.add(m.group(1).strip().lower())
    # Extract from wikilinks
    for m in re.finditer(r"\[\[(.+?)\]\]", text):
        keywords.add(m.group(1).strip().lower())
    # Clean and deduplicate
    cleaned = set()
    for kw in keywords:
        kw = re.sub(r"[^\w\s-]", "", kw).strip()
        if len(kw) > 2:
            cleaned.add(kw)
    return sorted(cleaned)


def _suggest_related(wiki_path: Path, keywords: list[str]) -> list[dict]:
    """Suggest related existing pages based on keyword overlap."""
    if not keywords:
        return []

    docs = collect_documents(wiki_path)
    scored: list[tuple[float, dict]] = []

    for doc in docs:
        if doc["category"] == "raw":
            continue
        score = 0
        title_lower = doc["title"].lower()
        tags_lower = {t.lower() for t in doc.get("tags", [])}

        for kw in keywords:
            if kw in title_lower:
                score += 3
            if kw in tags_lower:
                score += 2
            # Check body content (first 500 chars)
            body = (doc.get("_text") or "")[:500].lower()
            if kw in body:
                score += 1

        if score > 0:
            scored.append((score, {
                "title": doc["title"],
                "file": doc["file"],
                "category": doc["category"],
                "relevance_score": score,
            }))

    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:10]]


def _ingest_manifest(wiki_path: Path, args: argparse.Namespace) -> None:
    """Bulk ingest from a JSON manifest file."""
    manifest_path = expand(args.manifest)
    if not manifest_path.exists():
        print(f"❌ 清单文件不存在: {manifest_path}")
        sys.exit(1)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析错误: {e}")
        sys.exit(1)

    sources = manifest.get("sources", [])
    if not sources:
        print("❌ 清单中没有源文件")
        sys.exit(1)

    print(f"📥 批量摄入: {len(sources)} 个源\n")

    results = []
    errors = []

    for i, source in enumerate(sources, 1):
        source_type = source.get("type", "")
        title = source.get("title", "")
        tags = source.get("tags", [])

        try:
            if source_type == "url":
                url = source.get("url", "")
                if not url:
                    errors.append({"index": i, "error": "缺少 url 字段"})
                    continue

                print(f"  [{i}/{len(sources)}] 获取: {url}")
                final_url, content_type, text = _fetch_url(url)

                slug = _slugify_url(url)
                filename = _generate_filename(slug, wiki_path, "raw")
                dest = wiki_path / "raw" / filename

                doc_title = _extract_title_from_text(text) or title or url
                header = f"# {doc_title}\n\n> Source: {url}\n> Fetched: {now()}\n> Content-Type: {content_type}\n\n---\n\n"
                dest.write_text(header + text, encoding="utf-8")

                keywords = _extract_keywords(text)
                related = _suggest_related(wiki_path, keywords)

                results.append({
                    "index": i,
                    "source_type": "url",
                    "source": url,
                    "destination": f"raw/{filename}",
                    "size_bytes": dest.stat().st_size,
                    "title": doc_title,
                    "keywords": keywords,
                    "related_pages": related,
                })

            elif source_type == "file":
                file_path = source.get("path", "")
                if not file_path:
                    errors.append({"index": i, "error": "缺少 path 字段"})
                    continue

                src = expand(file_path)
                if not src.exists():
                    errors.append({"index": i, "error": f"文件不存在: {src}"})
                    continue

                # Security: block source files outside wiki directory
                try:
                    src.resolve().relative_to(wiki_path.resolve())
                except ValueError:
                    errors.append({"index": i, "error": f"源文件不在 wiki 目录内（安全限制）: {src}"})
                    continue

                print(f"  [{i}/{len(sources)}] 导入: {src}")

                slug = src.stem.lower().replace(" ", "-")
                slug = re.sub(r"[^\w-]", "-", slug)
                slug = re.sub(r"-+", "-", slug).strip("-")
                if not slug:
                    slug = "imported"

                filename = _generate_filename(slug, wiki_path, "raw")
                dest = wiki_path / "raw" / filename

                import shutil
                shutil.copy2(src, dest)

                try:
                    text = dest.read_text(encoding="utf-8")
                except Exception:
                    text = ""

                doc_title = _extract_title_from_text(text) if text else (title or src.stem.replace("-", " ").title())
                keywords = _extract_keywords(text)
                related = _suggest_related(wiki_path, keywords)

                results.append({
                    "index": i,
                    "source_type": "file",
                    "source": str(src),
                    "destination": f"raw/{filename}",
                    "size_bytes": dest.stat().st_size,
                    "title": doc_title,
                    "keywords": keywords,
                    "related_pages": related,
                })

            elif source_type == "template":
                if not title:
                    errors.append({"index": i, "error": "缺少 title 字段"})
                    continue

                category = source.get("category", "drafts")
                slug = title.lower().replace(" ", "-")
                slug = re.sub(r"[^\w-]", "-", slug)
                slug = re.sub(r"-+", "-", slug).strip("-")

                filename = _generate_filename(slug, wiki_path, category)
                dest = wiki_path / category / filename

                content = template_wiki_page(title, category, tags, source="(manual)")
                dest.write_text(content, encoding="utf-8")

                print(f"  [{i}/{len(sources)}] 模板: {title}")

                results.append({
                    "index": i,
                    "source_type": "template",
                    "destination": f"{category}/{filename}",
                    "title": title,
                    "category": category,
                    "tags": tags,
                })
            else:
                errors.append({"index": i, "error": f"未知类型: {source_type}"})

        except Exception as e:
            errors.append({"index": i, "error": str(e)[:200]})

    # Batch log update
    if results:
        details = [f"Processed: {len(results)} sources"]
        for r in results[:5]:
            dest = r.get("destination", "")
            details.append(f"  - {r.get('title', '?')}: {dest}")
        if len(results) > 5:
            details.append(f"  ... and {len(results) - 5} more")
        append_to_log(wiki_path, f"bulk ingest | {len(results)} sources", details)

    clear_doc_cache()

    # Output
    if args.format == "json":
        meta = read_schema_meta(wiki_path)
        output = {
            "wiki": meta,
            "action": "bulk_ingest",
            "total": len(sources),
            "success": len(results),
            "errors": len(errors),
            "results": results,
            "errors_detail": errors,
            "agent_required": True,
            "agent_instruction": "批量摄入仅完成结构层。Agent 必须对每个成功摄入的源文件逐一执行知识提取（读取 raw/ → 提取实体/概念/关系 → 创建 wiki 页面 → 交叉引用 → 更新 log.md）。详见 SKILL.md「批量摄入工作流」。",
            "pending_files": [r.get("destination", "") for r in results],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    # Table output
    print(f"\n{'─' * 40}")
    print(f"✅ 成功: {len(results)} 个")
    if errors:
        print(f"❌ 失败: {len(errors)} 个")
        for e in errors:
            print(f"   [{e['index']}] {e['error']}")
    print(f"\n📝 日志已更新: log.md")

    # Remind agent: batch structural ingest is done, semantic extraction is next
    print(f"\n⚠️  批量摄入仅完成结构层（保存到 raw/）。Agent 必须继续执行：")
    print(f"   对每个成功摄入的源文件，逐一执行完整的知识提取流程。")
    print(f"   详见 SKILL.md「批量摄入工作流」。")
    if results:
        print(f"\n   待处理文件清单：")
        for r in results:
            dest = r.get("destination", "")
            title = r.get("title", "?")
            print(f"   ☐ {dest} — {title}")


def _parse_sources_from_frontmatter(text: str) -> list[str]:
    """Extract raw file paths from `sources:` frontmatter field.

    Handles formats: sources: [raw/foo.md], sources: [raw/a.md, raw/b.md]
    """
    fm = extract_frontmatter_from_text(text)
    raw_val = fm.get("sources", "")
    if not raw_val:
        return []
    # Already a list (parsed by extract_frontmatter_from_text for [...] format)
    if isinstance(raw_val, list):
        return [s.strip() for s in raw_val if s.strip()]
    # Single string value
    val = str(raw_val).strip()
    if val.startswith("[") and val.endswith("]"):
        val = val[1:-1]
    return [s.strip() for s in val.split(",") if s.strip()]


# Summary-like patterns that suggest content depends heavily on a single source
_SUMMARY_PATTERNS = [
    re.compile(r"^> .*总结", re.MULTILINE),
    re.compile(r"^> .*摘要", re.MULTILINE),
    re.compile(r"^## (?:Summary|摘要|总结|概要)", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^> .*原文", re.MULTILINE),
    re.compile(r"^## (?:原文|Original)", re.MULTILINE | re.IGNORECASE),
]


def _classify_page_content(text: str) -> str:
    """Classify whether page content is a direct summary or general knowledge.

    Returns 'summary' if the page appears to be a direct summary/extract of
    its source material, 'general' if it appears to contain independent knowledge.
    """
    # Strip frontmatter for analysis
    lines = text.splitlines()
    body_lines = []
    in_fm = False
    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---":
            in_fm = True
            continue
        if in_fm:
            if line.strip() == "---":
                in_fm = False
            continue
        body_lines.append(line)

    body = "\n".join(body_lines).strip()

    # Very short pages are likely summaries
    if len(body) < 300:
        return "summary"

    # Check for summary-like patterns
    for pat in _SUMMARY_PATTERNS:
        if pat.search(body):
            return "summary"

    # Check ratio of quoted/blockquote content (high = likely summary)
    quote_lines = sum(1 for l in body_lines if l.strip().startswith(">"))
    total_lines = sum(1 for l in body_lines if l.strip())
    if total_lines > 0 and quote_lines / total_lines > 0.3:
        return "summary"

    return "general"


def _update_frontmatter_sources(
    text: str,
    remove_source: str,
) -> str:
    """Remove a source from frontmatter.

    Returns the modified text. If no frontmatter exists, returns text unchanged.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text

    # Find frontmatter boundaries
    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx < 0:
        return text

    fm_lines = lines[1:end_idx]
    body_lines = lines[end_idx + 1:]

    # Process sources line
    new_fm_lines = []
    for line in fm_lines:
        stripped = line.strip()
        if stripped.startswith("sources:"):
            sources = _parse_sources_from_text(stripped)
            sources = [s for s in sources if s != remove_source]
            if sources:
                new_fm_lines.append(f"sources: [{', '.join(sources)}]")
            else:
                new_fm_lines.append("sources: []")
        else:
            new_fm_lines.append(line)

    # Reconstruct: frontmatter + body
    parts = ["---", "\n".join(new_fm_lines), "---"]
    if body_lines:
        parts.append("\n".join(body_lines))
    return "\n".join(parts) + "\n"


def _update_frontmatter_fields(text: str, fields: dict[str, str]) -> str:
    """Add or update fields in existing frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text

    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx < 0:
        return text

    fm_lines = lines[1:end_idx]
    body_lines = lines[end_idx + 1:]

    # Update existing fields, track which keys were found
    new_fm_lines = []
    updated_keys: set[str] = set()
    for line in fm_lines:
        key = line.strip().split(":")[0].strip() if ":" in line.strip() else ""
        if key in fields:
            new_fm_lines.append(f"{key}: {fields[key]}")
            updated_keys.add(key)
        else:
            new_fm_lines.append(line)

    # Add fields that weren't already present
    for key, val in fields.items():
        if key not in updated_keys:
            new_fm_lines.append(f"{key}: {val}")

    parts = ["---", "\n".join(new_fm_lines), "---"]
    if body_lines:
        parts.append("\n".join(body_lines))
    return "\n".join(parts) + "\n"


def _parse_sources_from_text(frontmatter_line: str) -> list[str]:
    """Parse sources from a single frontmatter line like 'sources: [a, b]'."""
    _, _, val = frontmatter_line.partition(":")
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        val = val[1:-1]
    return [s.strip() for s in val.split(",") if s.strip()]


def _process_stale_refs(
    wiki_path: Path,
    stale_detail: dict[str, list[str]],
    apply: bool,
) -> list[dict]:
    """Process stale references: classify and optionally update wiki pages.

    Groups stale sources by referrer page so each page is processed once.
    Classification is based on the state AFTER all stale sources are removed.

    Returns list of action records for each processed ref.
    """
    # Invert: referrer_file -> [raw_files that are stale]
    page_stale: dict[str, list[str]] = {}
    for raw_file, referrers in stale_detail.items():
        for ref in referrers:
            page_stale.setdefault(ref, []).append(raw_file)

    actions = []

    for referrer_file, stale_files in page_stale.items():
        fp = wiki_path / referrer_file
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:
            continue

        sources = _parse_sources_from_frontmatter(text)
        remaining = [s for s in sources if s not in stale_files]
        has_remaining = len(remaining) > 0

        if has_remaining:
            # Page still has valid sources — just clean the stale ones
            for raw_file in stale_files:
                actions.append({
                    "raw_file": raw_file,
                    "referrer": referrer_file,
                    "is_only_source": False,
                    "action": "clean_reference",
                    "description": "清理失效引用（页面仍有其他来源）",
                })
            if apply:
                new_text = text
                for raw_file in stale_files:
                    new_text = _update_frontmatter_sources(new_text, raw_file)
                fp.write_text(new_text, encoding="utf-8")
                for a in actions[-len(stale_files):]:
                    a["applied"] = True
        else:
            # All sources are stale — classify content
            content_type = _classify_page_content(text)
            if content_type == "summary":
                for raw_file in stale_files:
                    actions.append({
                        "raw_file": raw_file,
                        "referrer": referrer_file,
                        "is_only_source": True,
                        "content_type": content_type,
                        "action": "suggest_archive",
                        "description": "唯一来源且内容为直接摘要，建议归档",
                    })
                if apply:
                    new_text = text
                    for raw_file in stale_files:
                        new_text = _update_frontmatter_sources(new_text, raw_file)
                    new_text = _update_frontmatter_fields(
                        new_text,
                        {"source_status": "review", "archive_suggested": "true"},
                    )
                    fp.write_text(new_text, encoding="utf-8")
                    for a in actions[-len(stale_files):]:
                        a["applied"] = True
            else:
                for raw_file in stale_files:
                    actions.append({
                        "raw_file": raw_file,
                        "referrer": referrer_file,
                        "is_only_source": True,
                        "content_type": content_type,
                        "action": "mark_review",
                        "description": "唯一来源已失，内容为通用知识，标记待审",
                    })
                if apply:
                    new_text = text
                    for raw_file in stale_files:
                        new_text = _update_frontmatter_sources(new_text, raw_file)
                    new_text = _update_frontmatter_fields(
                        new_text, {"source_status": "review"},
                    )
                    fp.write_text(new_text, encoding="utf-8")
                    for a in actions[-len(stale_files):]:
                        a["applied"] = True

    return actions


def cmd_refresh(args: argparse.Namespace) -> None:
    """Scan raw/ and cross-reference with wiki pages to find new/deleted files."""
    path = expand(args.path or ".")
    require_wiki(path)

    raw_dir = path / "raw"
    if not raw_dir.is_dir():
        print(f"❌ raw/ 目录不存在: {raw_dir}")
        sys.exit(1)

    apply = getattr(args, "apply", False)

    # Collect raw files
    raw_files = sorted(f"raw/{f.name}" for f in raw_dir.glob("*.md"))
    raw_set = set(raw_files)

    # Collect wiki pages (exclude raw/ and queries/)
    docs = collect_documents(path)
    wiki_docs = [d for d in docs if d["category"] not in ("raw", "queries")]

    # Build set of referenced raw files from frontmatter
    referenced_raw: set[str] = set()
    # Map: raw_file -> [page that references it]
    raw_referrers: dict[str, list[str]] = {}

    for doc in wiki_docs:
        text = doc.get("_text") or ""
        if not text:
            continue
        sources = _parse_sources_from_frontmatter(text)
        for src in sources:
            # Normalize: strip leading ./ and use forward slashes
            src_norm = src.lstrip("./").replace("\\", "/")
            referenced_raw.add(src_norm)
            raw_referrers.setdefault(src_norm, []).append(doc["file"])

    # New files: in raw/ but not referenced by any wiki page
    new_files = sorted(raw_set - referenced_raw)

    # Stale refs: referenced but file no longer exists on disk
    stale_refs = sorted(referenced_raw - raw_set)
    stale_detail = {ref: raw_referrers.get(ref, []) for ref in stale_refs}

    has_changes = bool(new_files or stale_refs)

    # Process stale refs if --apply or always classify for output
    stale_actions = _process_stale_refs(path, stale_detail, apply=apply)

    # Log the refresh action
    details = [f"New raw files: {len(new_files)}", f"Stale references: {len(stale_refs)}"]
    if new_files:
        details.append(f"  Pending extraction: {', '.join(new_files[:5])}")
        if len(new_files) > 5:
            details.append(f"  ... and {len(new_files) - 5} more")
    if apply and stale_actions:
        applied = [a for a in stale_actions if a.get("applied")]
        details.append(f"  Applied: {len(applied)} stale ref cleanups")
    append_to_log(path, "refresh", details)

    clear_doc_cache()

    # ── Output ──
    if args.format == "json":
        meta = read_schema_meta(path)
        output = {
            "wiki": meta,
            "action": "refresh",
            "apply": apply,
            "new_files": [
                {"file": f, "title": extract_title(path / f)}
                for f in new_files
            ],
            "stale_actions": stale_actions,
            "summary": {
                "total_raw_files": len(raw_files),
                "processed": len(raw_set & referenced_raw),
                "new": len(new_files),
                "stale": len(stale_refs),
                "stale_cleaned": len([a for a in stale_actions if a["action"] == "clean_reference"]),
                "stale_review": len([a for a in stale_actions if a["action"] == "mark_review"]),
                "stale_archive": len([a for a in stale_actions if a["action"] == "suggest_archive"]),
            },
            "log_updated": True,
        }
        if new_files:
            output["agent_required"] = True
            output["agent_instruction"] = (
                "发现新增原始资料。Agent 必须对每个新文件执行知识提取："
                "读取 raw/ → 提取实体/概念/关系 → 创建 wiki 页面（含 frontmatter + wikilinks）→ 更新 log.md。"
                "详见 SKILL.md「Full Ingest Workflow」。"
            )
            output["pending_files"] = new_files
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    # Table output
    if not has_changes:
        print(f"✅ 刷新检查完成 — 无变更（{len(raw_files)} 个原始资料均已处理）")
        return

    mode_label = "已执行" if apply else "预览"
    print(f"🔄 刷新检查完成（{mode_label}）\n")

    if new_files:
        print(f"📥 新增原始资料（需要知识提取）: {len(new_files)} 个")
        for f in new_files:
            title = extract_title(path / f)
            print(f"   ☐ {f} — {title}")
        print(f"   └── Agent 必须执行: 读取 → 提取实体/概念/关系 → 创建 wiki 页面 → 更新 log.md")

    if stale_actions:
        if new_files:
            print()

        # Group by action type
        clean_refs = [a for a in stale_actions if a["action"] == "clean_reference"]
        mark_review = [a for a in stale_actions if a["action"] == "mark_review"]
        suggest_archive = [a for a in stale_actions if a["action"] == "suggest_archive"]

        total_stale = len(stale_actions)
        print(f"⚠️  已删除的原始资料（引用失效）: {total_stale} 个\n")

        if clean_refs:
            print(f"   📎 仅清理引用（{len(clean_refs)} 个）:")
            for a in clean_refs:
                print(f"      • {a['referrer']} ← {a['raw_file']}")
                if apply:
                    print(f"        ✅ 已清理")

        if mark_review:
            print(f"\n   🔍 标记待审（{len(mark_review)} 个，唯一来源已失但内容为通用知识）:")
            for a in mark_review:
                print(f"      • {a['referrer']} ← {a['raw_file']}")
                if apply:
                    print(f"        ✅ 已标记 source_status: review")

        if suggest_archive:
            print(f"\n   📦 建议归档（{len(suggest_archive)} 个，唯一来源且内容为直接摘要）:")
            for a in suggest_archive:
                print(f"      • {a['referrer']} ← {a['raw_file']}")
                if apply:
                    print(f"        ✅ 已标记 archive_suggested: true")

        if not apply:
            print(f"\n   💡 使用 --apply 执行清理")

    print(f"\n📝 日志已更新: log.md")


# ── command ──

def cmd_ingest(args: argparse.Namespace) -> None:
    path = expand(args.path or ".")
    require_wiki(path)

    # Check for manifest mode
    if args.manifest:
        _ingest_manifest(path, args)
        return

    # Validate: exactly one source
    sources = [bool(args.url), bool(args.file), bool(args.template)]
    if sum(sources) != 1:
        print("❌ 请指定一个来源: --url, --file, --template, 或 --manifest")
        sys.exit(1)

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    result: dict = {}

    if args.url:
        # ── URL mode ──
        url = args.url
        print(f"📥 正在获取: {url}")

        try:
            final_url, content_type, text = _fetch_url(url)
        except HTTPError as e:
            print(f"❌ HTTP 错误: {e.code} {e.reason}")
            sys.exit(1)
        except URLError as e:
            print(f"❌ 网络错误: {e.reason}")
            sys.exit(1)
        except TimeoutError:
            print(f"❌ 请求超时（30 秒）")
            sys.exit(1)
        except Exception as e:
            print(f"❌ 获取失败: {e}")
            sys.exit(1)

        slug = _slugify_url(url)
        filename = _generate_filename(slug, path, "raw")
        dest = path / "raw" / filename

        # Build content with source header
        title = _extract_title_from_text(text)
        if not title:
            title = url

        header = f"# {title}\n\n> Source: {url}\n> Fetched: {now()}\n> Content-Type: {content_type}\n\n---\n\n"
        dest.write_text(header + text, encoding="utf-8")

        keywords = _extract_keywords(text)
        related = _suggest_related(path, keywords)

        append_to_log(path, f"ingest | {title}", [
            f"Saved to: raw/{filename}",
            f"Size: {dest.stat().st_size} bytes",
            f"Source: {url}",
        ])

        result = {
            "action": "ingest",
            "source_type": "url",
            "source": url,
            "destination": f"raw/{filename}",
            "size_bytes": dest.stat().st_size,
            "content_type": content_type,
            "title": title,
            "keywords": keywords,
            "related_pages": related,
            "log_updated": True,
        }

    elif args.file:
        # ── File mode ──
        src = expand(args.file)
        if not src.exists():
            print(f"❌ 文件不存在: {src}")
            sys.exit(1)

        # Security: block source files outside wiki directory
        try:
            src.resolve().relative_to(path.resolve())
        except ValueError:
            print(f"❌ 源文件不在 wiki 目录内（安全限制）: {src}")
            sys.exit(1)

        slug = src.stem.lower().replace(" ", "-")
        slug = re.sub(r"[^\w-]", "-", slug)
        slug = re.sub(r"-+", "-", slug).strip("-")
        if not slug:
            slug = "imported"

        filename = _generate_filename(slug, path, "raw")
        dest = path / "raw" / filename

        import shutil
        shutil.copy2(src, dest)

        # Read for keyword extraction
        try:
            text = dest.read_text(encoding="utf-8")
        except Exception:
            text = ""

        title = _extract_title_from_text(text) if text else src.stem.replace("-", " ").title()
        keywords = _extract_keywords(text)
        related = _suggest_related(path, keywords)

        append_to_log(path, f"ingest | {title}", [
            f"Saved to: raw/{filename}",
            f"Size: {dest.stat().st_size} bytes",
            f"Source: local file {src}",
        ])

        result = {
            "action": "ingest",
            "source_type": "file",
            "source": str(src),
            "destination": f"raw/{filename}",
            "size_bytes": dest.stat().st_size,
            "title": title,
            "keywords": keywords,
            "related_pages": related,
            "log_updated": True,
        }

    elif args.template:
        # ── Template mode ──
        title = args.template.strip()
        category = args.category or "drafts"
        slug = title.lower().replace(" ", "-")
        slug = re.sub(r"[^\w-]", "-", slug)
        slug = re.sub(r"-+", "-", slug).strip("-")

        filename = _generate_filename(slug, path, category)
        dest = path / category / filename

        content = template_wiki_page(title, category, tags, source="(manual)")
        dest.write_text(content, encoding="utf-8")

        append_to_log(path, f"create | {title}", [
            f"File: {category}/{filename}",
            f"Type: template",
        ])

        result = {
            "action": "ingest",
            "source_type": "template",
            "destination": f"{category}/{filename}",
            "title": title,
            "category": category,
            "tags": tags,
            "log_updated": True,
        }

    clear_doc_cache()

    # ── Output ──
    if args.format == "json":
        meta = read_schema_meta(path)
        result["wiki"] = meta
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    # Table output
    if args.url:
        print(f"   保存到: raw/{result['destination'].split('/')[-1]}  ({result['size_bytes']} bytes)")
        print(f"   类型: {result['content_type']}")
        if result.get("related_pages"):
            print(f"\n   💡 相关页面:")
            for rp in result["related_pages"][:5]:
                print(f"      [[{rp['title']}]]  ({rp['file']})")
        print(f"\n   📝 日志已更新: log.md")

    elif args.file:
        print(f"📥 已导入: {args.file}")
        print(f"   保存到: raw/{result['destination'].split('/')[-1]}  ({result['size_bytes']} bytes)")
        if result.get("related_pages"):
            print(f"\n   💡 相关页面:")
            for rp in result["related_pages"][:5]:
                print(f"      [[{rp['title']}]]  ({rp['file']})")
        print(f"\n   📝 日志已更新: log.md")

    elif args.template:
        print(f"📄 模板已创建: {result['destination']}")
        print(f"   标题: {title}")
        print(f"   分类: {category}")
        if tags:
            print(f"   标签: {', '.join(tags)}")
        print(f"\n   📝 日志已更新: log.md")
