"""Command: ingest — Ingest external sources into the wiki."""

import argparse
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from . import DIRS, CATEGORY_LABELS
from .helpers import expand, require_wiki, now, today, collect_documents, clear_doc_cache, read_schema_meta, append_to_log
from .templates import template_wiki_page


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
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; wiki-tools/1.2)",
        "Accept": "text/html, text/plain, text/markdown, */*",
    })
    resp = urlopen(req, timeout=timeout)
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

    body = resp.read()

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
    from urllib.parse import urlparse
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
            body = doc.get("_text") or ""[:500].lower()
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
