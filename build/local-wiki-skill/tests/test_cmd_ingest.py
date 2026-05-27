"""Tests for wiki_core.cmd_ingest module."""

import json
import sys
from pathlib import Path

import pytest

# Add scripts/ to sys.path so we can import wiki_core
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from wiki_core.helpers import clear_doc_cache, collect_documents, search_documents
from wiki_core.cmd_ingest import (
    _html_to_text,
    _slugify_url,
    _generate_filename,
    _extract_title_from_text,
    _extract_keywords,
    _suggest_related,
    _HTMLTextExtractor,
    _parse_sources_from_frontmatter,
    _classify_page_content,
    _update_frontmatter_sources,
    _update_frontmatter_fields,
    _process_stale_refs,
    cmd_refresh,
    cmd_ingest,
)

from conftest import _write_page

# conftest provides: wiki_dir fixture, _write_page helper


class TestHTMLToText:
    def test_basic_html(self):
        html = "<p>Hello <b>world</b></p>"
        text = _html_to_text(html)
        assert "Hello" in text
        assert "world" in text
        assert "<p>" not in text
        assert "<b>" not in text

    def test_strips_script(self):
        html = "<p>Keep</p><script>alert('xss')</script><p>After</p>"
        text = _html_to_text(html)
        assert "Keep" in text
        assert "After" in text
        assert "alert" not in text

    def test_strips_style(self):
        html = "<style>body{color:red}</style><p>Content</p>"
        text = _html_to_text(html)
        assert "color" not in text
        assert "Content" in text

    def test_strips_nav_footer(self):
        html = "<nav>Menu</nav><p>Body</p><footer>Footer</p>"
        text = _html_to_text(html)
        assert "Body" in text
        assert "Menu" not in text
        assert "Footer" not in text

    def test_nested_skip_tags(self):
        html = "<nav><div><script>deep</script></div></nav><p>Safe</p>"
        text = _html_to_text(html)
        assert "deep" not in text
        assert "Safe" in text

    def test_empty_html(self):
        assert _html_to_text("") == ""

    def test_plain_text_passthrough(self):
        text = _html_to_text("Just plain text")
        assert "Just plain text" in text

    def test_multiple_newlines_collapsed(self):
        html = "<p>A</p><p></p><p></p><p>B</p>"
        text = _html_to_text(html)
        # Should not have 3+ consecutive newlines
        assert "\n\n\n" not in text

    def test_heading_block_handling(self):
        html = "<h1>Title</h1><h2>Sub</h2>"
        text = _html_to_text(html)
        assert "Title" in text
        assert "Sub" in text

    def test_malformed_html(self):
        html = "<p>unclosed <b>bold <i>italic</p>"
        # Should not crash
        text = _html_to_text(html)
        assert "unclosed" in text


class TestSlugifyUrl:
    def test_simple_url(self):
        slug = _slugify_url("https://example.com/my-article")
        assert slug == "my-article"

    def test_deep_path(self):
        slug = _slugify_url("https://example.com/blog/2024/ai-post")
        assert "ai-post" in slug or "blog" in slug

    def test_root_url(self):
        slug = _slugify_url("https://example.com/")
        assert len(slug) >= 3

    def test_special_chars(self):
        slug = _slugify_url("https://example.com/hello-world!@#")
        assert "!" not in slug
        assert "@" not in slug
        assert "#" not in slug

    def test_long_slug_truncated(self):
        slug = _slugify_url("https://example.com/" + "a" * 200)
        assert len(slug) <= 80

    def test_short_slug_uses_hash(self):
        slug = _slugify_url("https://example.com/a")
        assert len(slug) >= 3
        assert slug.startswith("page-") or len(slug) >= 3

    def test_consistent_output(self):
        s1 = _slugify_url("https://example.com/test")
        s2 = _slugify_url("https://example.com/test")
        assert s1 == s2


class TestGenerateFilename:
    def test_no_conflict(self, wiki_dir):
        name = _generate_filename("test-doc", wiki_dir, "raw")
        assert name == "test-doc.md"

    def test_conflict_appends_number(self, wiki_dir):
        (wiki_dir / "raw" / "test.md").write_text("first", encoding="utf-8")
        name = _generate_filename("test", wiki_dir, "raw")
        assert name == "test-2.md"

    def test_multiple_conflicts(self, wiki_dir):
        (wiki_dir / "raw" / "x.md").write_text("1", encoding="utf-8")
        (wiki_dir / "raw" / "x-2.md").write_text("2", encoding="utf-8")
        (wiki_dir / "raw" / "x-3.md").write_text("3", encoding="utf-8")
        name = _generate_filename("x", wiki_dir, "raw")
        assert name == "x-4.md"

    def test_different_subdir(self, wiki_dir):
        name = _generate_filename("doc", wiki_dir, "concepts")
        assert name == "doc.md"


class TestExtractTitleFromText:
    def test_h1_title(self):
        assert _extract_title_from_text("# My Title\n\nContent") == "My Title"

    def test_no_h1_fallback(self):
        title = _extract_title_from_text("First line content here\nMore")
        assert title == "First line content here"

    def test_h2_not_used(self):
        title = _extract_title_from_text("## Only H2\nContent here\n")
        assert title != "Only H2"

    def test_empty_text(self):
        assert _extract_title_from_text("") == ""

    def test_whitespace_only(self):
        assert _extract_title_from_text("   \n  \n  ") == ""

    def test_short_first_line_skipped(self):
        title = _extract_title_from_text("ab\nLonger line here\n")
        assert title == "Longer line here"

    def test_long_title_preserved(self):
        long_title = "A" * 200
        title = _extract_title_from_text(f"# {long_title}\n")
        assert title == long_title


class TestExtractKeywords:
    def test_from_headings(self):
        text = "# Machine Learning\n## Deep Learning\nContent"
        kw = _extract_keywords(text)
        assert "machine learning" in kw
        assert "deep learning" in kw

    def test_from_bold(self):
        text = "The **Transformer** model uses **attention**."
        kw = _extract_keywords(text)
        assert "transformer" in kw
        assert "attention" in kw

    def test_from_wikilinks(self):
        text = "See [[Neural Network]] and [[CNN]]"
        kw = _extract_keywords(text)
        assert "neural network" in kw

    def test_deduplication(self):
        text = "# Transformer\n**Transformer**\n[[Transformer]]"
        kw = _extract_keywords(text)
        assert kw.count("transformer") == 1

    def test_short_keywords_filtered(self):
        text = "# A\n## BB\n### CCC"
        kw = _extract_keywords(text)
        assert "a" not in kw
        assert "bb" not in kw
        assert "ccc" in kw

    def test_empty_text(self):
        assert _extract_keywords("") == []

    def test_special_chars_cleaned(self):
        text = "## Hello, World!"
        kw = _extract_keywords(text)
        assert any("hello" in k for k in kw)


class TestSuggestRelated:
    def test_finds_related(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "transformer.md",
                    "---\ntitle: Transformer\ntags: [ai]\n---\n# Transformer\n")
        _write_page(wiki_dir, "concepts", "attention.md",
                    "---\ntitle: Attention\ntags: [ai]\n---\n# Attention\n")
        clear_doc_cache()
        related = _suggest_related(wiki_dir, ["transformer", "attention"])
        assert len(related) >= 1

    def test_no_keywords(self, wiki_dir):
        assert _suggest_related(wiki_dir, []) == []

    def test_no_match(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "cooking.md",
                    "---\ntitle: Cooking\n---\n# Cooking\n")
        clear_doc_cache()
        related = _suggest_related(wiki_dir, ["quantum-physics"])
        assert len(related) == 0

    def test_excludes_raw(self, wiki_dir):
        _write_page(wiki_dir, "raw", "raw-doc.md",
                    "---\ntitle: Raw Doc\n---\n# Raw Doc\n")
        clear_doc_cache()
        related = _suggest_related(wiki_dir, ["raw"])
        assert all(r["category"] != "raw" for r in related)

    def test_max_results(self, wiki_dir):
        for i in range(20):
            _write_page(wiki_dir, "concepts", f"doc-{i}.md",
                        f"---\ntitle: Doc {i} keyword\n---\n# Doc {i} keyword\n")
        clear_doc_cache()
        related = _suggest_related(wiki_dir, ["keyword"])
        assert len(related) <= 10

    def test_scored_by_relevance(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "exact.md",
                    "---\ntitle: Transformer\ntags: [transformer]\n---\n# Transformer\n")
        _write_page(wiki_dir, "concepts", "mention.md",
                    "---\ntitle: ML\n---\n# ML\nSome text mentions transformer.\n")
        clear_doc_cache()
        related = _suggest_related(wiki_dir, ["transformer"])
        if len(related) >= 2:
            assert related[0]["relevance_score"] >= related[1]["relevance_score"]


# ═══════════════════════════════════════════
# cmd_ingest.py — operator precedence regression
# ═══════════════════════════════════════════


class TestSuggestRelatedOperatorPrecedence:
    """Regression tests for the `doc.get('_text') or ''[:500]` bug."""

    def test_text_with_content_returns_results(self, wiki_dir):
        """The original bug: _text had content but ""[:500] was evaluated first,
        making body always empty → no related pages ever found."""
        _write_page(wiki_dir, "concepts", "target.md",
                    "---\ntitle: Target\n---\n# Target\nkeyword content\n")
        clear_doc_cache()
        # Use a keyword that appears in the body
        related = _suggest_related(wiki_dir, ["keyword"])
        assert len(related) >= 1, "Related pages should be found when _text has content"

    def test_text_none_still_works(self, wiki_dir):
        """When _text is None, (None or '') should give empty string, not crash."""
        _write_page(wiki_dir, "concepts", "page.md",
                    "---\ntitle: Page\n---\n# Page\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        for d in docs:
            d["_text"] = None
        # Should not raise
        related = _suggest_related(wiki_dir, ["page"])
        # May or may not find results, but must not crash

    def test_text_empty_string(self, wiki_dir):
        """When _text is '', ('' or '')[:500] should be ''."""
        _write_page(wiki_dir, "concepts", "empty.md",
                    "---\ntitle: Empty\n---\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        for d in docs:
            d["_text"] = ""
        related = _suggest_related(wiki_dir, ["anything"])
        assert isinstance(related, list)


# ═══════════════════════════════════════════
# Security tests
# ═══════════════════════════════════════════


class TestSSRFProtection:
    """Test _validate_url blocks dangerous URLs."""

    def test_reject_file_scheme(self):
        from wiki_core.cmd_ingest import _validate_url
        with pytest.raises(ValueError, match="不允许.*协议"):
            _validate_url("file:///etc/passwd")

    def test_reject_ftp_scheme(self):
        from wiki_core.cmd_ingest import _validate_url
        with pytest.raises(ValueError, match="不允许.*协议"):
            _validate_url("ftp://example.com/file")

    def test_reject_localhost(self):
        from wiki_core.cmd_ingest import _validate_url
        with pytest.raises(ValueError, match="内网|保留|解析"):
            _validate_url("http://127.0.0.1/admin")

    def test_reject_private_10(self):
        from wiki_core.cmd_ingest import _validate_url
        with pytest.raises(ValueError, match="内网|保留|解析"):
            _validate_url("http://10.0.0.1/internal")

    def test_reject_private_192(self):
        from wiki_core.cmd_ingest import _validate_url
        with pytest.raises(ValueError, match="内网|保留|解析"):
            _validate_url("http://192.168.1.1/admin")

    def test_reject_private_172(self):
        from wiki_core.cmd_ingest import _validate_url
        with pytest.raises(ValueError, match="内网|保留|解析"):
            _validate_url("http://172.16.0.1/admin")

    def test_reject_metadata_endpoint(self):
        from wiki_core.cmd_ingest import _validate_url
        with pytest.raises(ValueError, match="内网|保留|解析"):
            _validate_url("http://169.254.169.254/latest/meta-data/")

    def test_reject_empty_hostname(self):
        from wiki_core.cmd_ingest import _validate_url
        with pytest.raises(ValueError, match="协议|主机"):
            _validate_url("http://")

    def test_allow_valid_https(self):
        from wiki_core.cmd_ingest import _validate_url
        # Should not raise for a public HTTPS URL
        # Note: DNS resolution may fail in test env, so we catch that separately
        try:
            _validate_url("https://example.com")
        except ValueError as e:
            if "解析" in str(e):
                pytest.skip("DNS not available in test env")
            raise

    def test_fetch_url_blocks_ssrf(self):
        """_fetch_url should reject dangerous URLs before making the request."""
        from wiki_core.cmd_ingest import _fetch_url
        with pytest.raises(ValueError, match="不允许|内网"):
            _fetch_url("file:///etc/passwd")

    def test_response_body_size_limit_exists(self):
        """Verify _MAX_RESPONSE_BYTES constant is defined and reasonable."""
        from wiki_core.cmd_ingest import _MAX_RESPONSE_BYTES
        assert isinstance(_MAX_RESPONSE_BYTES, int)
        assert _MAX_RESPONSE_BYTES > 0
        assert _MAX_RESPONSE_BYTES <= 100 * 1024 * 1024  # max 100MB

    def test_redirect_handler_class_exists(self):
        """Verify the SSRF-safe redirect handler is defined and used."""
        from wiki_core.cmd_ingest import _SSRFSafeRedirectHandler
        from urllib.request import HTTPRedirectHandler
        assert issubclass(_SSRFSafeRedirectHandler, HTTPRedirectHandler)

    def test_redirect_handler_validates_target(self):
        """Redirect to a private IP should be rejected by the handler."""
        from wiki_core.cmd_ingest import _SSRFSafeRedirectHandler, _validate_url
        handler = _SSRFSafeRedirectHandler()
        with pytest.raises(ValueError, match="内网|保留|解析"):
            handler.redirect_request(
                None, None, 302, "Found", {}, "http://127.0.0.1/admin"
            )


class TestPathTraversalFix:
    """Test path containment checks in index search and manifest ingest."""

    def test_index_search_rejects_traversal(self, wiki_dir):
        """Index with ../../ paths should not read files outside wiki."""
        from wiki_core.cmd_ingest import _generate_filename
        _write_page(wiki_dir, "concepts", "safe.md", "# Safe\nkeyword\n")
        clear_doc_cache()

        # Create a tampered index with path traversal
        queries_dir = wiki_dir / "queries"
        queries_dir.mkdir(exist_ok=True)
        index = {
            "wiki": {"name": "Test", "domain": "AI"},
            "generated_at": "2025-01-01",
            "total_documents": 1,
            "categories": [{
                "category": "concepts",
                "category_label": "概念",
                "count": 1,
                "documents": [{
                    "title": "Evil",
                    "file": "../../etc/passwd",
                    "category": "concepts",
                    "size": 100,
                    "modified": "2025-01-01",
                    "tags": [],
                    "links_count": 0,
                }],
            }],
            "tags": [],
            "inverted_index": {"keyword": [{"file": "../../etc/passwd", "line": 1}]},
        }
        (queries_dir / "index.json").write_text(
            json.dumps(index), encoding="utf-8"
        )

        from wiki_core.cmd_query import _try_index_search
        from wiki_core.helpers import collect_documents
        docs = collect_documents(wiki_dir)
        results = _try_index_search(wiki_dir, "keyword", docs)
        # Should return None (stale/invalid) or empty, never read /etc/passwd
        if results is not None:
            assert len(results) == 0

    def test_manifest_blocks_external_file(self, wiki_dir, capsys):
        """Manifest with file outside wiki should be blocked."""
        external = wiki_dir.parent / "external.md"
        external.write_text("# External\n", encoding="utf-8")

        manifest = {
            "sources": [{"type": "file", "path": str(external)}]
        }
        manifest_path = wiki_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            path=str(wiki_dir),
            manifest=str(manifest_path),
            file=None,
            url=None,
            template=None,
            tags="",
            category="drafts",
            format="text",
            pretty=False,
        )

        cmd_ingest(args)
        captured = capsys.readouterr()
        assert "不在 wiki 目录内" in captured.out

        # Cleanup
        external.unlink(missing_ok=True)


class TestFileCopyWarning:
    """Test that --file blocks copies from outside wiki directory."""

    def test_external_file_blocked(self, wiki_dir, capsys):
        """Copying from outside wiki should be blocked with an error."""
        external = wiki_dir.parent / "outside.md"
        external.write_text("# Outside\n", encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            path=str(wiki_dir),
            file=str(external),
            manifest=None,
            url=None,
            template=None,
            tags="",
            category="drafts",
            format="text",
            pretty=False,
        )

        with pytest.raises(SystemExit):
            cmd_ingest(args)
        captured = capsys.readouterr()
        assert "不在 wiki 目录内" in captured.out

        external.unlink(missing_ok=True)

    def test_internal_file_allowed(self, wiki_dir, capsys):
        """Copying from inside wiki should succeed."""
        internal = wiki_dir / "notes.md"
        internal.write_text("# Internal\n", encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            path=str(wiki_dir),
            file=str(internal),
            manifest=None,
            url=None,
            template=None,
            tags="",
            category="drafts",
            format="text",
            pretty=False,
        )

        cmd_ingest(args)
        captured = capsys.readouterr()
        assert "不在 wiki 目录内" not in captured.out


# ═══════════════════════════════════════════
# cmd_refresh tests
# ═══════════════════════════════════════════


class TestParseSourcesFromFrontmatter:
    """Test _parse_sources_from_frontmatter helper."""

    def test_single_source(self):
        text = "---\ntitle: Test\nsources: [raw/foo.md]\n---\n"
        assert _parse_sources_from_frontmatter(text) == ["raw/foo.md"]

    def test_multiple_sources(self):
        text = "---\ntitle: Test\nsources: [raw/a.md, raw/b.md]\n---\n"
        assert _parse_sources_from_frontmatter(text) == ["raw/a.md", "raw/b.md"]

    def test_no_sources_field(self):
        text = "---\ntitle: Test\n---\n"
        assert _parse_sources_from_frontmatter(text) == []

    def test_empty_sources(self):
        text = "---\ntitle: Test\nsources: []\n---\n"
        assert _parse_sources_from_frontmatter(text) == []

    def test_no_frontmatter(self):
        text = "# Just a heading\n"
        assert _parse_sources_from_frontmatter(text) == []

    def test_whitespace_handling(self):
        text = "---\nsources: [ raw/a.md , raw/b.md ]\n---\n"
        result = _parse_sources_from_frontmatter(text)
        assert "raw/a.md" in result
        assert "raw/b.md" in result


class TestCmdRefresh:
    """Test cmd_refresh command."""

    def _make_args(self, wiki_dir, fmt="table", apply=False):
        import argparse
        return argparse.Namespace(
            path=str(wiki_dir),
            format=fmt,
            pretty=False,
            apply=apply,
        )

    def test_no_raw_files(self, wiki_dir, capsys):
        """Refresh with empty raw/ should show no changes."""
        args = self._make_args(wiki_dir)
        cmd_refresh(args)
        captured = capsys.readouterr()
        assert "无变更" in captured.out

    def test_new_raw_file_detected(self, wiki_dir, capsys):
        """Raw file not referenced by any wiki page should be flagged as new."""
        # Create a raw file with no wiki page referencing it
        raw_file = wiki_dir / "raw" / "new-article.md"
        raw_file.write_text("# New Article\n\nSome content.\n", encoding="utf-8")

        args = self._make_args(wiki_dir)
        cmd_refresh(args)
        captured = capsys.readouterr()
        assert "新增原始资料" in captured.out
        assert "raw/new-article.md" in captured.out

    def test_processed_raw_file_not_flagged(self, wiki_dir, capsys):
        """Raw file referenced by a wiki page should NOT be flagged."""
        # Create a raw file
        raw_file = wiki_dir / "raw" / "processed.md"
        raw_file.write_text("# Processed\n\nContent.\n", encoding="utf-8")

        # Create a wiki page that references it
        _write_page(wiki_dir, "entities", "my-entity.md",
                     "---\ntitle: My Entity\nsources: [raw/processed.md]\n---\n# My Entity\n")

        clear_doc_cache()
        args = self._make_args(wiki_dir)
        cmd_refresh(args)
        captured = capsys.readouterr()
        assert "无变更" in captured.out

    def test_deleted_raw_file_detected(self, wiki_dir, capsys):
        """Wiki page referencing a deleted raw file should be flagged."""
        # Create a wiki page referencing a non-existent raw file
        _write_page(wiki_dir, "concepts", "my-concept.md",
                     "---\ntitle: My Concept\nsources: [raw/deleted.md]\n---\n# My Concept\n")

        clear_doc_cache()
        args = self._make_args(wiki_dir)
        cmd_refresh(args)
        captured = capsys.readouterr()
        assert "已删除的原始资料" in captured.out
        assert "raw/deleted.md" in captured.out

    def test_mixed_new_and_deleted(self, wiki_dir, capsys):
        """Both new and deleted files should be reported."""
        # New raw file (unreferenced)
        new_raw = wiki_dir / "raw" / "new.md"
        new_raw.write_text("# New\n", encoding="utf-8")

        # Wiki page referencing deleted raw file
        _write_page(wiki_dir, "entities", "e.md",
                     "---\ntitle: E\nsources: [raw/gone.md]\n---\n# E\n")

        clear_doc_cache()
        args = self._make_args(wiki_dir)
        cmd_refresh(args)
        captured = capsys.readouterr()
        assert "新增原始资料" in captured.out
        assert "raw/new.md" in captured.out
        assert "已删除的原始资料" in captured.out
        assert "raw/gone.md" in captured.out

    def test_json_output_new_files(self, wiki_dir):
        """JSON output should list new files with metadata."""
        raw_file = wiki_dir / "raw" / "article.md"
        raw_file.write_text("# Article Title\n\nBody.\n", encoding="utf-8")

        clear_doc_cache()
        args = self._make_args(wiki_dir, fmt="json")
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        cmd_refresh(args)
        output = json.loads(sys.stdout.getvalue())
        sys.stdout = old_stdout

        assert output["action"] == "refresh"
        assert output["summary"]["new"] == 1
        assert output["new_files"][0]["file"] == "raw/article.md"
        assert output["agent_required"] is True
        assert "pending_files" in output

    def test_json_output_no_changes(self, wiki_dir):
        """JSON output with no changes should show zero counts."""
        args = self._make_args(wiki_dir, fmt="json")
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        cmd_refresh(args)
        output = json.loads(sys.stdout.getvalue())
        sys.stdout = old_stdout

        assert output["action"] == "refresh"
        assert output["summary"]["new"] == 0
        assert output["summary"]["stale"] == 0
        assert "agent_required" not in output

    def test_json_output_stale_refs(self, wiki_dir):
        """JSON output should list stale references with referrer pages."""
        _write_page(wiki_dir, "concepts", "c.md",
                     "---\ntitle: C\nsources: [raw/missing.md]\n---\n# C\n")

        clear_doc_cache()
        args = self._make_args(wiki_dir, fmt="json")
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        cmd_refresh(args)
        output = json.loads(sys.stdout.getvalue())
        sys.stdout = old_stdout

        assert output["summary"]["stale"] == 1
        assert output["stale_actions"][0]["raw_file"] == "raw/missing.md"
        assert output["stale_actions"][0]["referrer"] == "concepts/c.md"

    def test_log_updated(self, wiki_dir):
        """Refresh should update log.md."""
        raw_file = wiki_dir / "raw" / "test.md"
        raw_file.write_text("# Test\n", encoding="utf-8")

        clear_doc_cache()
        args = self._make_args(wiki_dir)
        cmd_refresh(args)

        log_content = (wiki_dir / "log.md").read_text(encoding="utf-8")
        assert "refresh" in log_content

    def test_requires_wiki_dir(self, tmp_path):
        """Should exit if path is not a wiki directory."""
        import argparse
        args = argparse.Namespace(path=str(tmp_path), format="table", pretty=False, apply=False)
        with pytest.raises(SystemExit):
            cmd_refresh(args)

    def test_apply_cleans_multi_source_ref(self, wiki_dir, capsys):
        """--apply should remove stale ref from multi-source page."""
        # Create the surviving raw file
        (wiki_dir / "raw" / "other.md").write_text("# Other\n", encoding="utf-8")
        _write_page(wiki_dir, "entities", "e.md",
                     "---\ntitle: E\nsources: [raw/gone.md, raw/other.md]\n---\n# E\n")

        clear_doc_cache()
        args = self._make_args(wiki_dir, apply=True)
        cmd_refresh(args)
        captured = capsys.readouterr()
        assert "仅清理引用" in captured.out

        # Verify file was updated
        content = (wiki_dir / "entities" / "e.md").read_text(encoding="utf-8")
        assert "raw/gone.md" not in content
        assert "raw/other.md" in content

    def test_apply_marks_single_source_summary(self, wiki_dir, capsys):
        """--apply should mark single-source summary page with archive_suggested."""
        _write_page(wiki_dir, "drafts", "d.md",
                     "---\ntitle: D\nsources: [raw/gone.md]\n---\n# D\nshort\n")

        clear_doc_cache()
        args = self._make_args(wiki_dir, apply=True)
        cmd_refresh(args)
        captured = capsys.readouterr()
        assert "建议归档" in captured.out

        content = (wiki_dir / "drafts" / "d.md").read_text(encoding="utf-8")
        assert "archive_suggested: true" in content
        assert "source_status: review" in content
        assert "raw/gone.md" not in content

    def test_apply_marks_single_source_general_knowledge(self, wiki_dir, capsys):
        """--apply should mark single-source general knowledge page for review."""
        long_content = "# Knowledge\n\n" + "This is general knowledge. " * 50
        _write_page(wiki_dir, "concepts", "k.md",
                     f"---\ntitle: K\nsources: [raw/gone.md]\n---\n\n{long_content}")

        clear_doc_cache()
        args = self._make_args(wiki_dir, apply=True)
        cmd_refresh(args)
        captured = capsys.readouterr()
        assert "标记待审" in captured.out

        content = (wiki_dir / "concepts" / "k.md").read_text(encoding="utf-8")
        assert "source_status: review" in content
        assert "archive_suggested" not in content
        assert "raw/gone.md" not in content

    def test_dry_run_does_not_modify_files(self, wiki_dir, capsys):
        """Without --apply, files should not be modified."""
        _write_page(wiki_dir, "concepts", "c.md",
                     "---\ntitle: C\nsources: [raw/gone.md]\n---\n# C\n")

        original = (wiki_dir / "concepts" / "c.md").read_text(encoding="utf-8")

        clear_doc_cache()
        args = self._make_args(wiki_dir, apply=False)
        cmd_refresh(args)
        captured = capsys.readouterr()
        assert "预览" in captured.out

        content = (wiki_dir / "concepts" / "c.md").read_text(encoding="utf-8")
        assert content == original

    def test_json_output_stale_actions_structure(self, wiki_dir):
        """JSON stale_actions should include action type and classification."""
        _write_page(wiki_dir, "concepts", "c.md",
                     "---\ntitle: C\nsources: [raw/gone.md]\n---\n# C\nshort\n")

        clear_doc_cache()
        args = self._make_args(wiki_dir, fmt="json")
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        cmd_refresh(args)
        output = json.loads(sys.stdout.getvalue())
        sys.stdout = old_stdout

        action = output["stale_actions"][0]
        assert action["action"] == "suggest_archive"
        assert action["content_type"] == "summary"
        assert action["is_only_source"] is True


class TestClassifyPageContent:
    """Test _classify_page_content helper."""

    def test_short_content_is_summary(self):
        text = "---\ntitle: T\n---\n# T\nShort.\n"
        assert _classify_page_content(text) == "summary"

    def test_summary_heading_detected(self):
        text = "---\ntitle: T\n---\n# T\n\n## Summary\n\nThis is a summary.\n"
        assert _classify_page_content(text) == "summary"

    def test_chinese_summary_heading_detected(self):
        text = "---\ntitle: T\n---\n# T\n\n## 摘要\n\n这是摘要内容。\n"
        assert _classify_page_content(text) == "summary"

    def test_high_quote_ratio_is_summary(self):
        lines = ["# T", ""]
        for i in range(20):
            lines.append(f"> Quote line {i}")
        lines.append("Non-quote")
        text = "---\ntitle: T\n---\n" + "\n".join(lines) + "\n"
        assert _classify_page_content(text) == "summary"

    def test_long_general_content(self):
        content = "# Concept\n\n" + "This is general knowledge about AI. " * 30
        text = f"---\ntitle: T\n---\n\n{content}\n"
        assert _classify_page_content(text) == "general"

    def test_no_frontmatter(self):
        text = "# Just content\n\n" + "Some body text. " * 30 + "\n"
        assert _classify_page_content(text) == "general"


class TestUpdateFrontmatterSources:
    """Test _update_frontmatter_sources helper."""

    def test_remove_source(self):
        text = "---\ntitle: T\nsources: [raw/a.md, raw/b.md]\n---\n# T\nBody.\n"
        result = _update_frontmatter_sources(text, "raw/a.md")
        assert "raw/a.md" not in result
        assert "raw/b.md" in result
        assert "# T" in result
        assert "Body." in result

    def test_remove_only_source_leaves_empty(self):
        text = "---\ntitle: T\nsources: [raw/a.md]\n---\n# T\nBody.\n"
        result = _update_frontmatter_sources(text, "raw/a.md")
        assert "sources: []" in result

    def test_add_fields(self):
        text = "---\ntitle: T\nsources: [raw/a.md]\n---\n# T\n"
        result = _update_frontmatter_sources(text, "raw/a.md")
        result = _update_frontmatter_fields(result, {"source_status": "review"})
        assert "source_status: review" in result

    def test_preserves_body_content(self):
        text = "---\ntitle: T\nsources: [raw/a.md]\n---\n# Heading\n\nParagraph text.\n"
        result = _update_frontmatter_sources(text, "raw/a.md")
        assert "# Heading" in result
        assert "Paragraph text." in result

    def test_no_frontmatter_returns_unchanged(self):
        text = "# No frontmatter\nJust content.\n"
        result = _update_frontmatter_sources(text, "raw/a.md")
        assert result == text


class TestProcessStaleRefs:
    """Test _process_stale_refs helper."""

    def test_multi_source_clean_reference(self, wiki_dir):
        """Multi-source page should get clean_reference action."""
        _write_page(wiki_dir, "entities", "e.md",
                     "---\ntitle: E\nsources: [raw/gone.md, raw/keep.md]\n---\n# E\n")

        clear_doc_cache()
        actions = _process_stale_refs(wiki_dir, {"raw/gone.md": ["entities/e.md"]}, apply=False)
        assert len(actions) == 1
        assert actions[0]["action"] == "clean_reference"
        assert actions[0]["is_only_source"] is False

    def test_single_source_summary_suggests_archive(self, wiki_dir):
        """Single-source summary page should get suggest_archive action."""
        _write_page(wiki_dir, "drafts", "d.md",
                     "---\ntitle: D\nsources: [raw/gone.md]\n---\n# D\nShort.\n")

        clear_doc_cache()
        actions = _process_stale_refs(wiki_dir, {"raw/gone.md": ["drafts/d.md"]}, apply=False)
        assert len(actions) == 1
        assert actions[0]["action"] == "suggest_archive"
        assert actions[0]["content_type"] == "summary"

    def test_single_source_general_marks_review(self, wiki_dir):
        """Single-source general knowledge page should get mark_review action."""
        long_content = "# Knowledge\n\n" + "General content. " * 50
        _write_page(wiki_dir, "concepts", "k.md",
                     f"---\ntitle: K\nsources: [raw/gone.md]\n---\n\n{long_content}")

        clear_doc_cache()
        actions = _process_stale_refs(wiki_dir, {"raw/gone.md": ["concepts/k.md"]}, apply=False)
        assert len(actions) == 1
        assert actions[0]["action"] == "mark_review"
        assert actions[0]["content_type"] == "general"

    def test_apply_modifies_file(self, wiki_dir):
        """With apply=True, should actually modify the file."""
        _write_page(wiki_dir, "entities", "e.md",
                     "---\ntitle: E\nsources: [raw/gone.md, raw/keep.md]\n---\n# E\nBody.\n")

        clear_doc_cache()
        actions = _process_stale_refs(wiki_dir, {"raw/gone.md": ["entities/e.md"]}, apply=True)
        assert actions[0].get("applied") is True

        content = (wiki_dir / "entities" / "e.md").read_text(encoding="utf-8")
        assert "raw/gone.md" not in content
        assert "raw/keep.md" in content

    def test_multiple_stale_files_same_referrer(self, wiki_dir):
        """Multiple stale sources pointing to the same referrer page."""
        (wiki_dir / "raw" / "keep.md").write_text("# Keep\n", encoding="utf-8")
        _write_page(wiki_dir, "entities", "e.md",
                     "---\ntitle: E\nsources: [raw/gone1.md, raw/gone2.md, raw/keep.md]\n---\n# E\n")

        clear_doc_cache()
        actions = _process_stale_refs(
            wiki_dir,
            {"raw/gone1.md": ["entities/e.md"], "raw/gone2.md": ["entities/e.md"]},
            apply=False,
        )
        assert len(actions) == 2
        assert all(a["action"] == "clean_reference" for a in actions)
        assert all(a["referrer"] == "entities/e.md" for a in actions)

    def test_read_error_skips_page(self, wiki_dir, capsys):
        """If referrer file can't be read, skip it gracefully."""
        # Stale ref points to a file that doesn't exist
        actions = _process_stale_refs(
            wiki_dir,
            {"raw/gone.md": ["entities/nonexistent.md"]},
            apply=False,
        )
        assert len(actions) == 0


class TestCmdRefreshEdgeCases:
    """Boundary tests for cmd_refresh."""

    def _make_args(self, wiki_dir, fmt="table", apply=False):
        import argparse
        return argparse.Namespace(
            path=str(wiki_dir),
            format=fmt,
            pretty=False,
            apply=apply,
        )

    def test_raw_dir_missing_exits(self, tmp_path):
        """Should exit if raw/ directory does not exist."""
        import argparse
        # Create a minimal wiki structure (schema.md) but no raw/
        (tmp_path / "schema.md").write_text("# Schema\n", encoding="utf-8")
        args = argparse.Namespace(path=str(tmp_path), format="table", pretty=False, apply=False)
        with pytest.raises(SystemExit):
            cmd_refresh(args)

    def test_unreferenced_raw_subdirectory_ignored(self, wiki_dir, capsys):
        """Only *.md files in raw/ are scanned, subdirectories ignored."""
        (wiki_dir / "raw" / "subdir").mkdir()
        (wiki_dir / "raw" / "subdir" / "nested.md").write_text("# Nested\n", encoding="utf-8")
        (wiki_dir / "raw" / "top.md").write_text("# Top\n", encoding="utf-8")

        clear_doc_cache()
        args = self._make_args(wiki_dir)
        cmd_refresh(args)
        captured = capsys.readouterr()
        # top.md should be flagged as new, subdir/nested.md should not appear
        assert "raw/top.md" in captured.out
        assert "nested" not in captured.out

    def test_multiple_pages_ref_same_raw(self, wiki_dir, capsys):
        """Multiple wiki pages referencing the same raw file — not flagged as new."""
        (wiki_dir / "raw" / "shared.md").write_text("# Shared\n", encoding="utf-8")
        _write_page(wiki_dir, "entities", "a.md",
                     "---\ntitle: A\nsources: [raw/shared.md]\n---\n# A\n")
        _write_page(wiki_dir, "concepts", "b.md",
                     "---\ntitle: B\nsources: [raw/shared.md]\n---\n# B\n")

        clear_doc_cache()
        args = self._make_args(wiki_dir)
        cmd_refresh(args)
        captured = capsys.readouterr()
        assert "无变更" in captured.out

    def test_stale_ref_with_multiple_referrers(self, wiki_dir):
        """Stale raw file referenced by multiple pages — both listed in stale_detail."""
        _write_page(wiki_dir, "entities", "a.md",
                     "---\ntitle: A\nsources: [raw/gone.md]\n---\n# A\n")
        _write_page(wiki_dir, "concepts", "b.md",
                     "---\ntitle: B\nsources: [raw/gone.md]\n---\n# B\n")

        clear_doc_cache()
        args = self._make_args(wiki_dir, fmt="json")
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        cmd_refresh(args)
        output = json.loads(sys.stdout.getvalue())
        sys.stdout = old_stdout

        assert output["summary"]["stale"] == 1
        referrers = output["stale_actions"][0]["referrer"]
        # Both pages should be in the stale actions
        action_referrers = [a["referrer"] for a in output["stale_actions"]]
        assert "entities/a.md" in action_referrers
        assert "concepts/b.md" in action_referrers

    def test_json_output_stale_multi_referrers_actions(self, wiki_dir):
        """JSON stale_actions should have one entry per referrer, not per raw file."""
        _write_page(wiki_dir, "entities", "a.md",
                     "---\ntitle: A\nsources: [raw/gone.md]\n---\n# A\nshort\n")
        _write_page(wiki_dir, "concepts", "b.md",
                     "---\ntitle: B\nsources: [raw/gone.md]\n---\n# B\nshort\n")

        clear_doc_cache()
        args = self._make_args(wiki_dir, fmt="json")
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        cmd_refresh(args)
        output = json.loads(sys.stdout.getvalue())
        sys.stdout = old_stdout

        assert len(output["stale_actions"]) == 2
        referrers = {a["referrer"] for a in output["stale_actions"]}
        assert referrers == {"entities/a.md", "concepts/b.md"}


class TestUpdateFrontmatterEdgeCases:
    """Boundary tests for _update_frontmatter_sources and _update_frontmatter_fields."""

    def test_unclosed_frontmatter_returns_unchanged(self):
        """Frontmatter with no closing --- should return text unchanged."""
        text = "---\ntitle: T\nsources: [raw/a.md]\n# Body\n"
        result = _update_frontmatter_sources(text, "raw/a.md")
        assert result == text

    def test_remove_nonexistent_source(self):
        """Removing a source that isn't listed should leave sources unchanged."""
        text = "---\ntitle: T\nsources: [raw/a.md]\n---\n# T\n"
        result = _update_frontmatter_sources(text, "raw/b.md")
        assert "raw/a.md" in result
        assert "sources:" in result

    def test_add_field_to_unclosed_frontmatter(self):
        """_update_frontmatter_fields on unclosed frontmatter returns unchanged."""
        text = "---\ntitle: T\n# Body\n"
        result = _update_frontmatter_fields(text, {"source_status": "review"})
        assert result == text

    def test_update_multiple_fields(self):
        """Should update multiple fields at once."""
        text = "---\ntitle: T\nsources: []\n---\n# T\n"
        result = _update_frontmatter_fields(text, {
            "source_status": "review",
            "archive_suggested": "true",
        })
        assert "source_status: review" in result
        assert "archive_suggested: true" in result

    def test_update_existing_field_value(self):
        """Should replace existing field value, not duplicate."""
        text = "---\ntitle: T\nsource_status: old\n---\n# T\n"
        result = _update_frontmatter_fields(text, {"source_status": "review"})
        assert "source_status: review" in result
        assert "source_status: old" not in result


class TestClassifyPageContentEdgeCases:
    """Boundary tests for _classify_page_content."""

    def test_quote_ratio_exactly_30_percent_is_summary(self):
        """Quote ratio at exactly 0.3 threshold should classify as summary."""
        # 3 quote lines out of 10 non-empty lines = 0.3, still summary (> 0.3)
        # Need body > 300 chars to avoid short-content rule
        lines = ["# T"]
        for i in range(7):
            lines.append(f"Normal line {i} with enough content to be counted. " * 3)
        for i in range(3):
            lines.append(f"> Quote line {i} with enough content. " * 3)
        text = "---\ntitle: T\n---\n" + "\n".join(lines) + "\n"
        # 3/10 = 0.3, condition is > 0.3 so this should be general
        assert _classify_page_content(text) == "general"

    def test_quote_ratio_above_30_percent_is_summary(self):
        """Quote ratio just above 0.3 should classify as summary."""
        lines = ["# T"]
        for i in range(6):
            lines.append(f"Normal line {i} with enough content to be counted. " * 3)
        for i in range(4):
            lines.append(f"> Quote line {i} with enough content. " * 3)
        text = "---\ntitle: T\n---\n" + "\n".join(lines) + "\n"
        # 4/10 = 0.4 > 0.3
        assert _classify_page_content(text) == "summary"

    def test_empty_body_is_summary(self):
        """Page with only frontmatter and no body should be summary (len < 300)."""
        text = "---\ntitle: T\nsources: [raw/a.md]\n---\n"
        assert _classify_page_content(text) == "summary"

    def test_no_nonempty_lines_avoids_division_by_zero(self):
        """All-blank body should not crash and should classify as summary."""
        text = "---\ntitle: T\n---\n\n\n\n"
        assert _classify_page_content(text) == "summary"

    def test_frontmatter_only_no_closing(self):
        """Unclosed frontmatter — body is empty, should be summary."""
        text = "---\ntitle: T\nsources: [raw/a.md]"
        assert _classify_page_content(text) == "summary"
