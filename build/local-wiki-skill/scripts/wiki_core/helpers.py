"""Shared helper functions for wiki tools."""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from . import DIRS, CATEGORY_LABELS


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


def read_health_config(wiki_path: Path) -> dict:
    """Read configurable health check weights from SCHEMA.md."""
    from . import HEALTH_WEIGHT_DEFAULTS
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


def _strip_internal(docs: list[dict]) -> list[dict]:
    """Remove internal fields (_text) before serialization."""
    return [{k: v for k, v in d.items() if not k.startswith("_")} for d in docs]


def build_link_graph(wiki_path: Path) -> tuple[dict[str, list[str]], dict[str, dict]]:
    """Build bidirectional link graph. Returns (outbound_map, doc_info_map)."""
    outbound: dict[str, list[str]] = {}
    doc_info: dict[str, dict] = {}

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


def trace_graph(stem: str, adjacency: dict[str, list[str]], visited: set, depth: int) -> list[dict]:
    """Recursively trace through a link graph."""
    results = []
    if depth > 10 or stem in visited:
        return results
    visited.add(stem)
    for neighbor in adjacency.get(stem, []):
        results.append({"stem": neighbor, "depth": depth})
        results.extend(trace_graph(neighbor, adjacency, visited, depth + 1))
    return results


def find_closest(target: str, candidates: list[str]) -> str | None:
    """Find the closest matching stem using edit distance."""
    best = None
    best_score = -1
    target_chars = set(target)
    for c in candidates:
        c_chars = set(c)
        overlap = len(target_chars & c_chars) / max(len(target_chars | c_chars), 1)
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


def append_to_log(wiki_path: Path, action: str, details: list[str]) -> None:
    """Append an action entry to log.md."""
    log_path = wiki_path / "log.md"
    today_str = today()
    date_heading = f"## {today_str}"

    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
    else:
        content = "# 更新日志\n\n"

    if date_heading not in content:
        content = content.rstrip() + f"\n\n{date_heading}\n"

    entry_lines = [f"- {action}"]
    for detail in details:
        entry_lines.append(f"  {detail}")
    entry = "\n".join(entry_lines) + "\n"

    content = content.rstrip() + "\n" + entry
    log_path.write_text(content, encoding="utf-8")
