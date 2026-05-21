#!/usr/bin/env python3
"""wiki-import — WPS cloud document batch import for local wiki.

Zero external dependencies — uses only Python standard library (urllib).
Requires: Python 3.9+
"""

import json
import os
import re
import sys
import time
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── WPS API Config ──────────────────────────────────────────

WPS_BASE_URL = "https://openapi.wps.cn"
WPS_AUTH_URL = f"{WPS_BASE_URL}/oauth2/auth"
WPS_TOKEN_URL = f"{WPS_BASE_URL}/oauth2/token"
WPS_SCOPES = ["kso.file.read", "kso.file.search", "kso.drive.readwrite"]

SCRIPT_DIR = Path(__file__).resolve().parent
WPS_CONFIG_FILE = SCRIPT_DIR / "wps_config.json"
WPS_TOKEN_FILE = SCRIPT_DIR / "wps_token.json"


# ── WPS Token Management ────────────────────────────────────

def wps_load_config() -> dict:
    """Load app_id, app_secret, redirect_uri from wps_config.json."""
    if not WPS_CONFIG_FILE.exists():
        print(f"❌ 未找到 WPS 配置文件: {WPS_CONFIG_FILE}")
        print(f"   请创建 {WPS_CONFIG_FILE}，内容示例:")
        print(json.dumps({
            "app_id": "your_app_id",
            "app_secret": "your_app_secret",
            "redirect_uri": "http://localhost:8899/callback",
        }, indent=2, ensure_ascii=False))
        sys.exit(1)
    with open(WPS_CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def wps_load_token() -> dict | None:
    """Load saved token from wps_token.json."""
    if not WPS_TOKEN_FILE.exists():
        return None
    with open(WPS_TOKEN_FILE, encoding="utf-8") as f:
        return json.load(f)


def wps_save_token(token: dict) -> None:
    """Save token to wps_token.json."""
    with open(WPS_TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token, f, indent=2, ensure_ascii=False)
    print(f"✅ Token 已保存到 {WPS_TOKEN_FILE}")


def wps_is_token_valid(token: dict) -> bool:
    """Check if access_token is not expired."""
    if not token:
        return False
    return bool(token.get("access_token")) and time.time() < token.get("expires_at", 0) - 60


def wps_refresh_token(token: dict) -> dict:
    """Refresh access_token using refresh_token."""
    if not token.get("refresh_token"):
        raise ValueError("没有 refresh_token，需要重新授权")

    config = wps_load_config()
    data = urlencode({
        "grant_type": "refresh_token",
        "client_id": config["app_id"],
        "client_secret": config["app_secret"],
        "refresh_token": token["refresh_token"],
    }).encode()

    req = Request(WPS_TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    resp = urlopen(req)
    result = json.loads(resp.read().decode())

    new_token = {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", token["refresh_token"]),
        "expires_at": time.time() + result.get("expires_in", 7200),
        "openid": result.get("openid", token.get("openid", "")),
    }
    wps_save_token(new_token)
    return new_token


def wps_get_valid_token() -> str:
    """Get a valid access_token, refreshing if needed."""
    token = wps_load_token()
    if not token:
        print("❌ 未找到 token，请先运行授权: python wiki.py wps-auth")
        sys.exit(1)
    if not wps_is_token_valid(token):
        print("🔄 Token 已过期，尝试刷新...")
        try:
            token = wps_refresh_token(token)
        except Exception as e:
            print(f"❌ Token 刷新失败: {e}")
            print("   请重新授权: python wiki.py wps-auth")
            sys.exit(1)
    return token["access_token"]


# ── OAuth Authorization ──────────────────────────────────────

_auth_code_result = {"code": None}


class _CallbackHandler(BaseHTTPRequestHandler):
    """Local HTTP server to receive OAuth callback."""

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        code = qs.get("code", [None])[0]
        if code:
            _auth_code_result["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("授权成功！可以关闭此窗口。".encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Authorization failed")

    def log_message(self, *args):
        pass


def wps_do_auth() -> None:
    """Run OAuth authorization flow."""
    config = wps_load_config()
    app_id = config.get("app_id", "")
    app_secret = config.get("app_secret", "")
    redirect_uri = config.get("redirect_uri", "http://localhost:8899/callback")

    if not app_id or app_id == "your_app_id":
        print(f"❌ 请先在 {WPS_CONFIG_FILE} 中填写真实的 app_id 和 app_secret")
        sys.exit(1)

    # Build authorization URL
    params = urlencode({
        "response_type": "code",
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "scope": ",".join(WPS_SCOPES),
    })
    auth_url = f"{WPS_AUTH_URL}?{params}"

    # Start local callback server
    parsed = urlparse(redirect_uri)
    port = parsed.port or 8899
    server = HTTPServer(("0.0.0.0", port), _CallbackHandler)

    print(f"🔑 请在浏览器中完成授权...")
    print(f"   如果浏览器没有自动打开，请手动访问:")
    print(f"   {auth_url}")
    print()

    webbrowser.open(auth_url)
    print(f"⏳ 正在等待回调到 {redirect_uri} ...")
    server.handle_request()

    code = _auth_code_result["code"]
    if not code:
        print("❌ 未获取到授权码")
        sys.exit(1)

    print(f"✅ 获取到授权码: {code[:8]}...")

    # Exchange code for token
    data = urlencode({
        "grant_type": "authorization_code",
        "client_id": app_id,
        "client_secret": app_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }).encode()

    req = Request(WPS_TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    resp = urlopen(req)
    result = json.loads(resp.read().decode())

    if not result.get("access_token"):
        print(f"❌ Token 交换失败: {result}")
        sys.exit(1)

    token = {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", ""),
        "expires_at": time.time() + result.get("expires_in", 7200),
        "openid": result.get("openid", ""),
    }
    wps_save_token(token)
    print("✅ OAuth 授权完成！")


# ── WPS API Client ──────────────────────────────────────────

def wps_api(method: str, path: str, query: dict = None, body: dict = None) -> dict:
    """Make an authenticated WPS API request."""
    access_token = wps_get_valid_token()

    url = f"{WPS_BASE_URL}{path}"
    if query:
        url += "?" + urlencode(query)

    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/json")

    try:
        resp = urlopen(req)
        result = json.loads(resp.read().decode())
    except HTTPError as e:
        if e.code == 401:
            # Token expired, refresh and retry
            print("🔄 Token 过期，刷新并重试...")
            token = wps_refresh_token(wps_load_token())
            req = Request(url, data=data, method=method)
            req.add_header("Authorization", f"Bearer {token['access_token']}")
            req.add_header("Content-Type", "application/json")
            resp = urlopen(req)
            result = json.loads(resp.read().decode())
        else:
            error_body = e.read().decode() if e.readable() else ""
            raise RuntimeError(f"WPS API 错误 ({e.code}): {error_body}") from e

    # Check for API-level errors
    code = result.get("code", 0)
    if code not in (0, "ok", None):
        raise RuntimeError(f"WPS API 错误: {result}")

    return result.get("data") or result


def wps_list_drives() -> list:
    """List all drives for the authenticated user."""
    return wps_api("GET", "/v7/drives", query={"allotee_type": "user"})


def wps_list_files(drive_id: str, parent_id: str = "0") -> list:
    """List files in a drive folder. Returns list of file metadata."""
    result = wps_api("GET", f"/v7/drives/{drive_id}/files/{parent_id}/children")
    if isinstance(result, dict):
        return result.get("files", result.get("items", []))
    return result if isinstance(result, list) else []


def wps_list_files_recursive(drive_id: str, parent_id: str = "0") -> list:
    """Recursively list all files in a drive folder."""
    all_files = []
    items = wps_list_files(drive_id, parent_id)
    for item in items:
        all_files.append(item)
        if item.get("type") == "folder":
            sub_files = wps_list_files_recursive(drive_id, item["id"])
            all_files.extend(sub_files)
    return all_files


def wps_get_file_meta(file_id: str) -> dict:
    """Get file metadata."""
    return wps_api("GET", f"/v7/files/{file_id}/meta", query={"with_drive": "true"})


def wps_extract_content(drive_id: str, file_id: str, fmt: str = "markdown") -> str:
    """Extract file content. fmt: kdc/plain/markdown."""
    result = wps_api("GET", f"/v7/drives/{drive_id}/files/{file_id}/content",
                     query={"format": fmt})
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return result.get("content", result.get("text", json.dumps(result, ensure_ascii=False)))
    return str(result)


def wps_search_files(keyword: str, search_type: str = "file_name") -> list:
    """Search files by keyword."""
    result = wps_api("GET", "/v7/files/search",
                     query={"keyword": keyword, "type": search_type})
    if isinstance(result, dict):
        return result.get("files", result.get("items", []))
    return result if isinstance(result, list) else []


# ── URL Parsing ──────────────────────────────────────────────

def wps_parse_url(url: str) -> dict:
    """Parse a WPS cloud document URL.

    Supported formats:
    - https://www.kdocs.cn/folder/xxx → folder
    - https://www.kdocs.cn/l/xxx → file (short link)
    - https://www.kdocs.cn/xxx → file
    - https://www.kdocs.cn/p/xxx → presentation
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")

    if not path:
        return {"type": "unknown", "id": "", "url": url}

    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "folder":
        return {"type": "folder", "id": parts[1], "url": url}

    # Single file or short link
    file_id = parts[-1] if parts else ""
    return {"type": "file", "id": file_id, "url": url}


def wps_resolve_folder(folder_url: str) -> list[dict]:
    """Resolve a folder URL to a list of file metadata dicts."""
    info = wps_parse_url(folder_url)
    if info["type"] != "folder":
        raise ValueError(f"不是文件夹 URL: {folder_url}")

    folder_id = info["id"]

    # Need drive_id — try to get it from folder metadata
    meta = wps_get_file_meta(folder_id)
    drive_id = meta.get("drive_id", "")

    if not drive_id:
        # Fallback: list drives and use first one
        drives = wps_list_drives()
        if drives:
            drive_id = drives[0].get("id", "")
        if not drive_id:
            raise RuntimeError("无法获取 drive_id，请检查授权")

    files = wps_list_files_recursive(drive_id, folder_id)
    # Attach drive_id to each file for later content extraction
    for f in files:
        f["_drive_id"] = drive_id
    return files


# ── Classification & Tagging ─────────────────────────────────

CATEGORY_RULES = {
    "raw": ["会议记录", "周报", "日报", "纪要", "周会", "月报", "review"],
    "entities": ["团队", "人员", "成员", "team", "成员介绍"],
    "concepts": ["概念", "术语", "方案", "设计", "spec", "rfc", "架构", "规范", "标准", "方法论"],
}


def auto_classify(doc: dict) -> str:
    """Auto-classify a document based on metadata."""
    # 1. Explicit category
    if doc.get("category"):
        return doc["category"]

    title = doc.get("title", "").lower()
    path_hint = doc.get("path_hint", "").lower()

    # 2. Path-based classification
    path_rules = {
        "raw": ["/meeting", "/会议", "/周会", "/纪要", "/archive", "/归档"],
        "entities": ["/team", "/团队", "/人员", "/成员"],
        "concepts": ["/concept", "/概念", "/术语", "/方案", "/设计", "/spec"],
        "relations": ["/relation", "/关系", "/交叉"],
    }
    for cat, keywords in path_rules.items():
        for kw in keywords:
            if kw in path_hint:
                return cat

    # 3. Title-based classification
    for cat, keywords in CATEGORY_RULES.items():
        for kw in keywords:
            if kw in title:
                return cat

    # 4. Default
    return "raw"


TAG_RULES = {
    "会议": ["会议记录", "会议", "纪要", "周会"],
    "周报": ["周报"],
    "日报": ["日报"],
    "月报": ["月报"],
    "AI": ["ai", "llm", "gpt", "大模型", "人工智能", "机器学习", "深度学习"],
    "设计": ["设计", "架构", "方案"],
    "需求": ["需求", "prd", "产品需求"],
    "技术": ["技术", "开发", "代码", "api", "sdk"],
    "流程": ["流程", "规范", "标准", "指南"],
}


def auto_tags(doc: dict) -> list[str]:
    """Auto-generate tags based on title and path."""
    tags = list(doc.get("tags", []))
    title = doc.get("title", "").lower()
    path_hint = doc.get("path_hint", "").lower()
    combined = title + " " + path_hint

    for tag, keywords in TAG_RULES.items():
        for kw in keywords:
            if kw in combined and tag not in tags:
                tags.append(tag)
                break

    return tags


# ── Filename & Page Generation ───────────────────────────────

def generate_filename(title: str, existing: set[str]) -> str:
    """Generate a normalized filename from a title."""
    stem = title.strip()
    # Remove special characters, keep Chinese + alphanumeric
    stem = re.sub(r'[^\w一-鿿\s-]', '', stem)
    # Replace spaces/underscores with hyphens
    stem = re.sub(r'[\s_]+', '-', stem).strip('-').lower()
    if not stem:
        stem = "untitled"

    # Handle duplicates
    candidate = stem
    counter = 1
    while candidate in existing:
        counter += 1
        candidate = f"{stem}-{counter}"
    return candidate


def generate_page(doc: dict, filename: str, category: str, tags: list[str]) -> str:
    """Generate a wiki page markdown content."""
    title = doc.get("title", filename)
    lines = [
        "---",
        f'title: "{title}"',
    ]
    if tags:
        lines.append(f"tags: [{', '.join(tags)}]")
    if doc.get("author"):
        lines.append(f"author: {doc['author']}")
    if doc.get("date"):
        lines.append(f"date: {doc['date']}")
    if doc.get("url"):
        lines.append(f"source: {doc['url']}")
    if doc.get("id"):
        lines.append(f"wps_file_id: {doc['id']}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")

    # Source link
    if doc.get("url"):
        lines.append(f"> 来源: [{title}]({doc['url']})")
        lines.append("")

    # Body content
    content = doc.get("content", "")
    if content:
        lines.append(content.strip())
    else:
        lines.append("（内容待补充）")

    lines.append("")
    return "\n".join(lines)


# ── Incremental Update Tracking ──────────────────────────────

def load_indexed_files(wiki_path: Path) -> dict:
    """Load indexed file records from SCHEMA.md."""
    from wiki import _extract_yaml_block

    yaml_lines = _extract_yaml_block(wiki_path, "已索引文件")
    indexed = {}
    current = {}

    for line in yaml_lines:
        line = line.strip()
        if not line or line == "indexed:":
            continue
        if line.startswith("- "):
            if current.get("file_id"):
                indexed[current["file_id"]] = current
            current = {}
            # Parse inline key: value
            kv_str = line[2:]
            for pair in kv_str.split(","):
                pair = pair.strip()
                if ":" in pair:
                    k, _, v = pair.partition(":")
                    current[k.strip()] = v.strip().strip('"').strip("'")
        elif ":" in line:
            k, _, v = line.partition(":")
            current[k.strip()] = v.strip().strip('"').strip("'")

    if current.get("file_id"):
        indexed[current["file_id"]] = current
    return indexed


def save_indexed_files(wiki_path: Path, indexed: dict) -> None:
    """Update the 已索引文件 section in SCHEMA.md."""
    schema_path = wiki_path / "SCHEMA.md"
    if not schema_path.exists():
        return

    text = schema_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find or create the section
    section_start = -1
    yaml_start = -1
    yaml_end = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") and "已索引文件" in stripped:
            section_start = i
        if section_start >= 0 and i > section_start and stripped == "```yaml":
            yaml_start = i
        if yaml_start >= 0 and i > yaml_start and stripped == "```":
            yaml_end = i
            break

    # Build new YAML block
    yaml_lines = ["```yaml", "indexed:"]
    for fid, info in indexed.items():
        yaml_lines.append(f'  - file_id: "{fid}"')
        if info.get("filename"):
            yaml_lines.append(f'    filename: "{info["filename"]}"')
        if info.get("category"):
            yaml_lines.append(f'    category: "{info["category"]}"')
        if info.get("imported_at"):
            yaml_lines.append(f'    imported_at: "{info["imported_at"]}"')
    yaml_lines.append("```")

    if section_start >= 0 and yaml_start >= 0 and yaml_end >= 0:
        # Replace existing block
        new_lines = lines[:yaml_start] + yaml_lines + lines[yaml_end + 1:]
    elif section_start >= 0:
        # Section exists but no YAML block — append after section header
        new_lines = lines[:section_start + 1] + [""] + yaml_lines + lines[section_start + 1:]
    else:
        # No section — append at end
        new_lines = lines + ["", "## 已索引文件", ""] + yaml_lines

    schema_path.write_text("\n".join(new_lines), encoding="utf-8")


# ── Import Core Logic ────────────────────────────────────────

class ImportOptions:
    """Options for import operations."""
    def __init__(self, args):
        self.category = getattr(args, "category", "")
        self.extra_tags = [t.strip() for t in getattr(args, "tags", "").split(",") if t.strip()]
        self.dry_run = getattr(args, "dry_run", False)
        self.force = getattr(args, "force", False)
        self.yes = getattr(args, "yes", False)
        self.skip_existing = getattr(args, "skip_existing", False)
        self.format = getattr(args, "format", "table")
        self.pretty = getattr(args, "pretty", False)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _log_import(wiki_path: Path, entries: list[str]) -> None:
    """Append import entries to log.md."""
    log_path = wiki_path / "log.md"
    if not log_path.exists():
        return

    log_lines = [
        "",
        f"## {_today()} — WPS 批量导入",
    ]
    log_lines.extend(entries)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")


def _show_scope_summary(files: list[dict], indexed: dict, skip_existing: bool) -> tuple[int, int]:
    """Show import scope summary and return (total, skip_count)."""
    # Type breakdown
    type_count: dict[str, int] = {}
    for f in files:
        ftype = f.get("type", "unknown")
        type_count[ftype] = type_count.get(ftype, 0) + 1

    # Count already-indexed
    skip_count = 0
    if skip_existing:
        for f in files:
            fid = f.get("id", "")
            if fid and fid in indexed:
                skip_count += 1

    total = len(files)
    pending = total - skip_count

    print(f"\n📂 WPS 文件夹内容:")
    print(f"   文件总数: {total} 个")
    for ftype, count in sorted(type_count.items(), key=lambda x: -x[1]):
        print(f"     {ftype}: {count} 个")
    if skip_existing and skip_count > 0:
        print(f"   跳过已导入: {skip_count} 个")
    print(f"   待导入: {pending} 个")

    return total, skip_count


def _confirm_import(total: int, skip_count: int, opts: ImportOptions) -> bool:
    """Ask user for confirmation unless --yes or --force."""
    if opts.yes or opts.force:
        return True
    if opts.dry_run:
        return False

    pending = total - skip_count
    if pending == 0:
        print("   ✅ 没有新文件需要导入。")
        return False

    try:
        ans = input(f"   确认导入 {pending} 个文件? [y/n] ").strip().lower()
    except EOFError:
        ans = "y"
    return ans == "y"


def import_from_manifest(wiki_path: Path, manifest: dict, opts: ImportOptions) -> dict:
    """Import documents from a JSON manifest."""
    from wiki import collect_documents

    docs_in = manifest.get("documents", [])
    if not docs_in:
        return {"imported": 0, "skipped": 0, "errors": []}

    # Load existing state
    indexed = load_indexed_files(wiki_path)
    existing_docs = collect_documents(wiki_path)
    existing_names = {Path(d["file"]).stem for d in existing_docs}

    imported = 0
    skipped = 0
    errors = []
    log_entries = []

    for doc in docs_in:
        file_id = doc.get("id", "")
        title = doc.get("title", "untitled")

        # Skip if already indexed
        if opts.skip_existing and file_id and file_id in indexed:
            skipped += 1
            continue

        try:
            # Classify & tag
            category = opts.category or auto_classify(doc)
            tags = auto_tags(doc)
            for t in opts.extra_tags:
                if t not in tags:
                    tags.append(t)

            # Generate filename
            filename = generate_filename(title, existing_names)
            existing_names.add(filename)

            # Generate page content
            page_content = generate_page(doc, filename, category, tags)

            if opts.dry_run:
                print(f"   [预览] {category}/{filename}.md — {title}")
                imported += 1
                continue

            # Write file
            cat_dir = wiki_path / category
            cat_dir.mkdir(parents=True, exist_ok=True)
            file_path = cat_dir / f"{filename}.md"
            file_path.write_text(page_content, encoding="utf-8")
            print(f"   ✅ {category}/{filename}.md — {title}")

            # Track
            if file_id:
                indexed[file_id] = {
                    "file_id": file_id,
                    "filename": filename,
                    "category": category,
                    "imported_at": _now(),
                }

            imported += 1
            log_entries.append(f"- 导入: {category}/{filename}.md ({title})")

        except Exception as e:
            errors.append(f"{title}: {e}")
            print(f"   ❌ {title}: {e}")

    # Update SCHEMA.md
    if not opts.dry_run and imported > 0:
        save_indexed_files(wiki_path, indexed)

    # Update log.md
    if not opts.dry_run and log_entries:
        _log_import(wiki_path, log_entries)

    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_from_wps_folder(wiki_path: Path, folder_url: str, opts: ImportOptions) -> dict:
    """Import all files from a WPS folder."""
    # 1. Resolve folder
    print(f"\n🔍 正在解析 WPS 文件夹: {folder_url}")
    try:
        files = wps_resolve_folder(folder_url)
    except Exception as e:
        print(f"❌ 无法访问文件夹: {e}")
        return {"imported": 0, "skipped": 0, "errors": [str(e)]}

    if not files:
        print("   文件夹为空。")
        return {"imported": 0, "skipped": 0, "errors": []}

    # Filter out folders (only import files)
    files = [f for f in files if f.get("type") != "folder"]

    # 2. Scope confirmation
    indexed = load_indexed_files(wiki_path)
    total, skip_count = _show_scope_summary(files, indexed, opts.skip_existing)

    if not _confirm_import(total, skip_count, opts):
        if opts.dry_run:
            return {"imported": total - skip_count, "skipped": skip_count, "errors": []}
        return {"imported": 0, "skipped": 0, "errors": []}

    # 3. Process each file
    from wiki import collect_documents

    existing_docs = collect_documents(wiki_path)
    existing_names = {Path(d["file"]).stem for d in existing_docs}

    imported = 0
    skipped = 0
    errors = []
    log_entries = []

    for f in files:
        file_id = f.get("id", "")
        title = f.get("name", f.get("title", "untitled"))
        # Strip file extension from title
        if "." in title:
            title = title.rsplit(".", 1)[0]
        drive_id = f.get("_drive_id", "")

        # Skip if already indexed
        if opts.skip_existing and file_id and file_id in indexed:
            skipped += 1
            continue

        try:
            # Extract content
            content = ""
            if not opts.dry_run and drive_id and file_id:
                try:
                    content = wps_extract_content(drive_id, file_id, fmt="markdown")
                except Exception as e:
                    print(f"   ⚠️  内容提取失败 ({title}): {e}，将创建空页面")

            doc = {
                "id": file_id,
                "title": title,
                "content": content,
                "url": f.get("url", ""),
                "type": f.get("type", ""),
                "path_hint": f.get("parent_path", ""),
            }

            # Classify & tag
            category = opts.category or auto_classify(doc)
            tags = auto_tags(doc)
            for t in opts.extra_tags:
                if t not in tags:
                    tags.append(t)

            # Generate filename
            filename = generate_filename(title, existing_names)
            existing_names.add(filename)

            if opts.dry_run:
                print(f"   [预览] {category}/{filename}.md — {title}")
                imported += 1
                continue

            # Generate & write
            page_content = generate_page(doc, filename, category, tags)
            cat_dir = wiki_path / category
            cat_dir.mkdir(parents=True, exist_ok=True)
            file_path = cat_dir / f"{filename}.md"
            file_path.write_text(page_content, encoding="utf-8")
            print(f"   ✅ {category}/{filename}.md — {title}")

            # Track
            if file_id:
                indexed[file_id] = {
                    "file_id": file_id,
                    "filename": filename,
                    "category": category,
                    "imported_at": _now(),
                }

            imported += 1
            log_entries.append(f"- 导入: {category}/{filename}.md ({title})")

        except Exception as e:
            errors.append(f"{title}: {e}")
            print(f"   ❌ {title}: {e}")

    # Update SCHEMA.md
    if not opts.dry_run and imported > 0:
        save_indexed_files(wiki_path, indexed)

    # Update log.md
    if not opts.dry_run and log_entries:
        _log_import(wiki_path, log_entries)

    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_from_wps_file(wiki_path: Path, file_url: str, opts: ImportOptions) -> dict:
    """Import a single WPS file."""
    info = wps_parse_url(file_url)
    if info["type"] == "folder":
        return import_from_wps_folder(wiki_path, file_url, opts)

    file_id = info["id"]
    if not file_id:
        print(f"❌ 无法解析文件 URL: {file_url}")
        return {"imported": 0, "skipped": 0, "errors": ["Invalid URL"]}

    print(f"\n🔍 正在获取文件信息: {file_url}")

    try:
        meta = wps_get_file_meta(file_id)
    except Exception as e:
        print(f"❌ 无法获取文件信息: {e}")
        return {"imported": 0, "skipped": 0, "errors": [str(e)]}

    title = meta.get("name", meta.get("title", "untitled"))
    if "." in title:
        title = title.rsplit(".", 1)[0]
    drive_id = meta.get("drive_id", "")

    # Check if already indexed
    indexed = load_indexed_files(wiki_path)
    if opts.skip_existing and file_id in indexed:
        print(f"   ⏭️  已导入，跳过: {title}")
        return {"imported": 0, "skipped": 1, "errors": []}

    # Extract content
    content = ""
    if not opts.dry_run and drive_id:
        try:
            content = wps_extract_content(drive_id, file_id, fmt="markdown")
        except Exception as e:
            print(f"   ⚠️  内容提取失败: {e}，将创建空页面")

    doc = {
        "id": file_id,
        "title": title,
        "content": content,
        "url": file_url,
        "type": meta.get("type", ""),
    }

    # Use manifest import for single file
    manifest = {"documents": [doc]}
    return import_from_manifest(wiki_path, manifest, opts)


# ── Main Command Handler ────────────────────────────────────

def cmd_import(args, wiki_path: Path) -> None:
    """Main import command handler."""
    opts = ImportOptions(args)

    # Determine input source
    wps_folder = getattr(args, "wps_folder", "")
    wps_file = getattr(args, "wps_file", "")
    manifest_file = getattr(args, "manifest", "")
    read_stdin = getattr(args, "stdin", False)

    sources = sum([bool(wps_folder), bool(wps_file), bool(manifest_file), read_stdin])
    if sources == 0:
        print("❌ 请指定导入源:")
        print("   --wps-folder <url>   WPS 文件夹 URL")
        print("   --wps-file <url>     单个 WPS 文件 URL")
        print("   --manifest <file>    JSON 清单文件")
        print("   --stdin              从 stdin 读取 JSON")
        sys.exit(1)
    if sources > 1:
        print("❌ 请只指定一个导入源")
        sys.exit(1)

    if wps_folder:
        result = import_from_wps_folder(wiki_path, wps_folder, opts)
    elif wps_file:
        result = import_from_wps_file(wiki_path, wps_file, opts)
    else:
        # Read JSON manifest
        if read_stdin:
            raw = sys.stdin.read()
        else:
            manifest_path = Path(manifest_file)
            if not manifest_path.exists():
                print(f"❌ 清单文件不存在: {manifest_file}")
                sys.exit(1)
            raw = manifest_path.read_text(encoding="utf-8")

        try:
            manifest = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析失败: {e}")
            sys.exit(1)

        result = import_from_manifest(wiki_path, manifest, opts)

    # Print summary
    mode = "预览" if opts.dry_run else "完成"
    print(f"\n{'─' * 40}")
    print(f"📋 导入{mode}:")
    print(f"   导入: {result['imported']} 个")
    print(f"   跳过: {result['skipped']} 个")
    if result["errors"]:
        print(f"   错误: {len(result['errors'])} 个")
        for err in result["errors"][:5]:
            print(f"     - {err}")

    if opts.dry_run:
        print(f"\n💡 去掉 --dry-run 执行实际导入。")
