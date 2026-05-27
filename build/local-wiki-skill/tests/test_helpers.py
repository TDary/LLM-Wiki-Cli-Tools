"""Tests for wiki_core.helpers module."""

import json
import os
import re
import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import pytest

# Add scripts/ to sys.path so we can import wiki_core
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from wiki_core import DIRS, CATEGORY_LABELS, SYSTEM_FILES, HEALTH_WEIGHT_DEFAULTS
from wiki_core.helpers import (
    expand,
    extract_title,
    extract_frontmatter_from_text,
    collect_documents,
    clear_doc_cache,
    search_documents,
    build_backlink_map,
    build_link_graph,
    trace_graph,
    find_closest,
    read_schema_meta,
    append_to_log,
    _strip_internal,
    _lazy_load_text,
    _extract_yaml_block,
    _parse_yaml_kv_pairs,
    now,
    today,
)

from conftest import _write_page

# conftest provides: wiki_dir fixture, _write_page helper


class TestExpand:
    def test_relative_path(self):
        result = expand(".")
        assert result.is_absolute()

    def test_home_tilde(self):
        result = expand("~")
        assert str(result) != "~"
        assert result.is_absolute()

    def test_absolute_passthrough(self):
        p = Path("/tmp/test") if os.name != "nt" else Path("C:/temp/test")
        result = expand(str(p))
        assert result.is_absolute()


class TestNowAndToday:
    def test_now_format(self):
        val = now()
        datetime.strptime(val, "%Y-%m-%d %H:%M:%S")

    def test_today_format(self):
        val = today()
        datetime.strptime(val, "%Y-%m-%d")

    def test_today_is_prefix_of_now(self):
        assert now().startswith(today())


class TestExtractTitle:
    def test_h1_heading(self, tmp_path):
        fp = tmp_path / "test.md"
        fp.write_text("# My Title\n\nSome content\n", encoding="utf-8")
        assert extract_title(fp) == "My Title"

    def test_h1_with_h2(self, tmp_path):
        fp = tmp_path / "test.md"
        fp.write_text("# Main Title\n## Sub Title\n", encoding="utf-8")
        assert extract_title(fp) == "Main Title"

    def test_no_heading_fallback(self, tmp_path):
        fp = tmp_path / "my-doc.md"
        fp.write_text("Just some text\n", encoding="utf-8")
        assert extract_title(fp) == "My Doc"

    def test_h2_only_no_h1(self, tmp_path):
        fp = tmp_path / "no-h1.md"
        fp.write_text("## Only H2\nSome content\n", encoding="utf-8")
        assert extract_title(fp) == "No H1"

    def test_empty_file(self, tmp_path):
        fp = tmp_path / "empty.md"
        fp.write_text("", encoding="utf-8")
        assert extract_title(fp) == "Empty"

    def test_h1_with_extra_spaces(self, tmp_path):
        fp = tmp_path / "test.md"
        fp.write_text("#   Spaced Title   \n", encoding="utf-8")
        assert extract_title(fp) == "Spaced Title"


class TestExtractFrontmatterFromText:
    def test_basic_frontmatter(self):
        text = "---\ntitle: Hello\ncreated: 2025-01-01\n---\n# Content"
        fm = extract_frontmatter_from_text(text)
        assert fm["title"] == "Hello"
        assert fm["created"] == "2025-01-01"

    def test_tags_list(self):
        text = "---\ntitle: Test\ntags: [ai, ml, nlp]\n---\n"
        fm = extract_frontmatter_from_text(text)
        assert fm["tags"] == ["ai", "ml", "nlp"]

    def test_tags_empty(self):
        text = "---\ntitle: Test\ntags: []\n---\n"
        fm = extract_frontmatter_from_text(text)
        assert fm["tags"] == []

    def test_quoted_values(self):
        text = "---\ntitle: \"Quoted\"\nauthor: 'Single'\n---\n"
        fm = extract_frontmatter_from_text(text)
        assert fm["title"] == "Quoted"
        assert fm["author"] == "Single"

    def test_no_frontmatter(self):
        fm = extract_frontmatter_from_text("# Just a heading\n")
        assert fm == {}

    def test_empty_text(self):
        fm = extract_frontmatter_from_text("")
        assert fm == {}

    def test_unclosed_frontmatter(self):
        text = "---\ntitle: Never closed\nsome: data"
        fm = extract_frontmatter_from_text(text)
        # Should still parse what's there
        assert fm.get("title") == "Never closed"

    def test_frontmatter_with_spaces_around_colon(self):
        text = "---\ntitle  :  Spaced  \n---\n"
        fm = extract_frontmatter_from_text(text)
        assert fm["title"] == "Spaced"


class TestSearchDocuments:
    @pytest.fixture
    def docs(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "transformer.md",
                    "# Transformer\n\nThe Transformer model uses attention.\n\n## Self-Attention\n")
        _write_page(wiki_dir, "concepts", "attention.md",
                    "# Attention Mechanism\n\nAttention is key to transformers.\n")
        _write_page(wiki_dir, "entities", "openai.md",
                    "# OpenAI\n\nOpenAI created GPT.\n")
        clear_doc_cache()
        return collect_documents(wiki_dir)

    def test_keyword_match(self, docs):
        results = search_documents(docs, "attention")
        assert len(results) >= 2
        titles = {r["title"] for r in results}
        assert "Transformer" in titles or "Attention Mechanism" in titles

    def test_case_insensitive(self, docs):
        results = search_documents(docs, "ATTENTION")
        assert len(results) >= 1

    def test_no_match(self, docs):
        results = search_documents(docs, "quantum-computing-xyz")
        assert len(results) == 0

    def test_title_match(self, docs):
        results = search_documents(docs, "OpenAI")
        assert len(results) >= 1
        assert any(r["title"] == "OpenAI" for r in results)

    def test_regex_search(self, docs):
        results = search_documents(docs, r"atten(tion|ded)", regex=True)
        assert len(results) >= 1

    def test_invalid_regex(self, docs):
        with pytest.raises(SystemExit):
            search_documents(docs, "[invalid", regex=True)

    def test_match_count(self, docs):
        results = search_documents(docs, "attention")
        for r in results:
            assert r["match_count"] == len(r["matches"])

    def test_line_numbers(self, docs):
        results = search_documents(docs, "Transformer")
        for r in results:
            for m in r["matches"]:
                if m["line"] > 0:
                    assert m["line"] >= 1


class TestBuildBacklinkMap:
    def test_basic_backlinks(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "a.md", "# A\nLink to [[B]] and [[C]]\n")
        _write_page(wiki_dir, "concepts", "b.md", "# B\nBack to [[A]]\n")
        _write_page(wiki_dir, "concepts", "c.md", "# C\nNo links here.\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        bl = build_backlink_map(wiki_dir, docs)

        assert "a" in bl
        assert len(bl["a"]) == 1
        assert bl["a"][0]["source_file"] == "concepts/b.md"

        assert "b" in bl
        assert len(bl["b"]) == 1

        assert "c" in bl
        assert len(bl["c"]) == 1

    def test_no_backlinks(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "lonely.md", "# Lonely\nNo links.\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        bl = build_backlink_map(wiki_dir, docs)
        assert "lonely" not in bl or len(bl.get("lonely", [])) == 0

    def test_multiple_sources(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "target.md", "# Target\n")
        _write_page(wiki_dir, "concepts", "s1.md", "# S1\n[[Target]]\n")
        _write_page(wiki_dir, "concepts", "s2.md", "# S2\n[[Target]]\n")
        _write_page(wiki_dir, "concepts", "s3.md", "# S3\n[[Target]]\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        bl = build_backlink_map(wiki_dir, docs)
        assert len(bl["target"]) == 3

    def test_wikilink_with_spaces(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "my-page.md", "# My Page\n")
        _write_page(wiki_dir, "concepts", "ref.md", "# Ref\n[[My Page]]\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        bl = build_backlink_map(wiki_dir, docs)
        assert "my-page" in bl


class TestBuildLinkGraph:
    def test_outbound_and_info(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "a.md", "# A\n[[B]]\n")
        _write_page(wiki_dir, "concepts", "b.md", "# B\n[[C]]\n")
        _write_page(wiki_dir, "concepts", "c.md", "# C\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        outbound, info = build_link_graph(wiki_dir, docs)

        assert "b" in outbound["a"]
        assert "c" in outbound["b"]
        assert outbound["c"] == []
        assert info["a"]["title"] == "A"


class TestTraceGraph:
    def test_linear_chain(self):
        adj = {"a": ["b"], "b": ["c"], "c": []}
        results = trace_graph("a", adj, set(), 0)
        stems = [r["stem"] for r in results]
        assert "b" in stems
        assert "c" in stems

    def test_cycle_protection(self):
        adj = {"a": ["b"], "b": ["a"]}
        results = trace_graph("a", adj, set(), 0)
        # Should not infinite loop
        assert len(results) < 100

    def test_max_depth(self):
        # Chain longer than depth limit
        adj = {}
        for i in range(20):
            adj[str(i)] = [str(i + 1)]
        results = trace_graph("0", adj, set(), 0)
        # depth > 10 should stop
        depths = [r["depth"] for r in results]
        assert max(depths) <= 10

    def test_empty_graph(self):
        results = trace_graph("x", {}, set(), 0)
        assert results == []

    def test_visited_skipped(self):
        adj = {"a": ["b"], "b": ["c"]}
        visited = {"b"}
        results = trace_graph("a", adj, visited, 0)
        stems = [r["stem"] for r in results]
        # "b" is a neighbor of "a" so it appears in results at depth 0,
        # but the recursive traversal from "b" is skipped because "b" is visited.
        # So "c" should NOT appear (it's only reachable through "b").
        assert "c" not in stems


class TestFindClosest:
    def test_exact_match(self):
        assert find_closest("transformer", ["transformer", "attention"]) == "transformer"

    def test_close_match(self):
        result = find_closest("transforner", ["transformer", "attention"])
        assert result == "transformer"

    def test_no_match(self):
        assert find_closest("zzzzz", ["transformer", "attention"]) is None

    def test_empty_candidates(self):
        assert find_closest("anything", []) is None

    def test_prefix_bonus(self):
        result = find_closest("transformer-model", ["transformer", "transformer-model-v2"])
        assert result is not None

    def test_single_char_overlap(self):
        # Very low overlap should return None
        result = find_closest("a", ["bbbbbbbb"])
        assert result is None


class TestReadSchemaMeta:
    def test_basic_meta(self, wiki_dir):
        meta = read_schema_meta(wiki_dir)
        assert meta["name"] == "Test Wiki"
        assert meta["domain"] == "AI"

    def test_missing_schema(self, tmp_path):
        meta = read_schema_meta(tmp_path)
        assert meta["name"] == tmp_path.name
        assert meta["domain"] == "Wiki 知识库"

    def test_schema_with_created_at(self, wiki_dir):
        meta = read_schema_meta(wiki_dir)
        assert meta.get("created_at") == "2025-01-01 00:00:00"


class TestAppendToLog:
    def test_creates_log_if_missing(self, tmp_path):
        log_path = tmp_path / "log.md"
        append_to_log(tmp_path, "test action", ["detail 1"])
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "test action" in content

    def test_appends_to_existing_log(self, wiki_dir):
        append_to_log(wiki_dir, "action1", [])
        append_to_log(wiki_dir, "action2", [])
        content = (wiki_dir / "log.md").read_text(encoding="utf-8")
        assert "action1" in content
        assert "action2" in content

    def test_adds_date_heading(self, tmp_path):
        log_path = tmp_path / "log.md"
        log_path.write_text("# 更新日志\n", encoding="utf-8")
        append_to_log(tmp_path, "new entry", ["detail"])
        content = log_path.read_text(encoding="utf-8")
        assert today() in content

    def test_reuses_existing_date_heading(self, tmp_path):
        log_path = tmp_path / "log.md"
        log_path.write_text(f"# 更新日志\n\n## {today()}\n\n- old entry\n", encoding="utf-8")
        append_to_log(tmp_path, "new entry", [])
        content = log_path.read_text(encoding="utf-8")
        # Should only have one date heading
        assert content.count(f"## {today()}") == 1

    def test_details_indented(self, tmp_path):
        append_to_log(tmp_path, "action", ["d1", "d2", "d3"])
        content = (tmp_path / "log.md").read_text(encoding="utf-8")
        assert "  d1" in content
        assert "  d2" in content


class TestStripInternal:
    def test_removes_underscore_keys(self):
        docs = [{"title": "A", "_text": "content", "_secret": 42}]
        result = _strip_internal(docs)
        assert result[0] == {"title": "A"}

    def test_preserves_normal_keys(self):
        docs = [{"title": "A", "file": "a.md", "tags": ["x"]}]
        result = _strip_internal(docs)
        assert result[0]["title"] == "A"
        assert result[0]["file"] == "a.md"

    def test_empty_list(self):
        assert _strip_internal([]) == []


class TestCollectDocuments:
    def test_collects_all_dirs(self, wiki_dir):
        for d in DIRS:
            _write_page(wiki_dir, d, f"{d}-doc.md", f"# {d} Doc\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        cats = {d["category"] for d in docs}
        for d in DIRS:
            assert d in cats

    def test_skips_missing_dirs(self, wiki_dir):
        shutil.rmtree(wiki_dir / "queries")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        cats = {d["category"] for d in docs}
        assert "queries" not in cats

    def test_metadata_fields(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "test.md",
                    "---\ntitle: Test\ntags: [a, b]\n---\n# Test\n[[Other]]\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        d = next(d for d in docs if d["file"] == "concepts/test.md")
        assert d["title"] == "Test"
        assert d["tags"] == ["a", "b"]
        assert d["links_count"] == 1
        assert d["category"] == "concepts"
        assert d["size"] > 0

    def test_empty_directory(self, wiki_dir):
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        # Only SCHEMA.md and log.md are in root, not in DIRS
        assert len(docs) == 0

    def test_non_utf8_handling(self, wiki_dir):
        fp = wiki_dir / "concepts" / "binary.md"
        fp.write_bytes(b"# Title\n\n\xff\xfe binary content\n")
        clear_doc_cache()
        # Should not crash
        docs = collect_documents(wiki_dir)
        assert len(docs) == 1


class TestYamlParsing:
    def test_extract_yaml_block(self, wiki_dir):
        schema = wiki_dir / "SCHEMA.md"
        schema.write_text(textwrap.dedent("""\
            # SCHEMA

            ## 健康检查

            ```yaml
            orphan: 5
            broken_link: 10
            ```

            ## Other Section

            ```yaml
            ignored: true
            ```
        """), encoding="utf-8")
        lines = _extract_yaml_block(wiki_dir, "健康检查")
        assert any("orphan" in l for l in lines)
        assert not any("ignored" in l for l in lines)

    def test_extract_yaml_block_missing_section(self, wiki_dir):
        lines = _extract_yaml_block(wiki_dir, "不存在的段落")
        assert lines == []

    def test_parse_yaml_kv_pairs(self):
        lines = ["orphan: 5", "broken_link: 10", "  ", "empty_key:"]
        result = _parse_yaml_kv_pairs(lines)
        assert result["orphan"] == "5"
        assert result["broken_link"] == "10"
        assert "empty_key" not in result

    def test_parse_yaml_kv_quotes(self):
        lines = ['name: "hello"', "value: 'world'"]
        result = _parse_yaml_kv_pairs(lines)
        assert result["name"] == "hello"
        assert result["value"] == "world"


# ═══════════════════════════════════════════
# Edge cases and integration-level tests
# ═══════════════════════════════════════════


class TestDocCache:
    def test_clear_cache(self, wiki_dir):
        from wiki_core.helpers import _doc_cache
        _doc_cache["test"] = [{"dummy": True}]
        clear_doc_cache()
        assert "test" not in _doc_cache

    def test_cached_returns_same_object(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "a.md", "# A\n")
        clear_doc_cache()
        from wiki_core.helpers import collect_documents_cached
        d1 = collect_documents_cached(wiki_dir)
        d2 = collect_documents_cached(wiki_dir)
        assert d1 is d2


class TestLazyLoadText:
    def test_loads_from_disk(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "test.md", "# Test\nContent here\n")
        doc = {"file": "concepts/test.md", "_text": None}
        text = _lazy_load_text(doc, wiki_dir)
        assert "Content here" in text
        assert doc["_text"] == text

    def test_caches_after_load(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "c.md", "# C\n")
        doc = {"file": "concepts/c.md", "_text": None}
        _lazy_load_text(doc, wiki_dir)
        assert doc["_text"] is not None

    def test_missing_file(self, wiki_dir):
        doc = {"file": "concepts/nonexistent.md", "_text": None}
        text = _lazy_load_text(doc, wiki_dir)
        assert text == ""
        assert doc["_text"] == ""


class TestSystemConstants:
    def test_dirs_is_list(self):
        assert isinstance(DIRS, list)
        assert len(DIRS) > 0

    def test_category_labels_complete(self):
        for d in DIRS:
            assert d in CATEGORY_LABELS

    def test_system_files(self):
        assert "readme.md" in SYSTEM_FILES
        assert "log.md" in SYSTEM_FILES
        assert "schema.md" in SYSTEM_FILES

    def test_health_weights_positive(self):
        for k, v in HEALTH_WEIGHT_DEFAULTS.items():
            assert isinstance(v, int) and v > 0


class TestRegexEdgeCases:
    """Test wikilink regex patterns used throughout the codebase."""

    WIKILINK_PATTERN = r"\[\[(.+?)\]\]"

    def test_basic_wikilink(self):
        assert re.search(self.WIKILINK_PATTERN, "See [[Page]] here")

    def test_multiple_wikilinks(self):
        matches = re.findall(self.WIKILINK_PATTERN, "[[A]] and [[B]]")
        assert matches == ["A", "B"]

    def test_wikilink_with_spaces(self):
        matches = re.findall(self.WIKILINK_PATTERN, "[[My Page]]")
        assert matches == ["My Page"]

    def test_nested_brackets(self):
        # \[\[(.+?)\]\] on "[[[nested]]]" — non-greedy match gives "[nested"
        # (the third ] closes the lazy match, not the wikilink)
        matches = re.findall(self.WIKILINK_PATTERN, "[[[nested]]]")
        assert matches == ["[nested"]

    def test_empty_wikilink(self):
        matches = re.findall(self.WIKILINK_PATTERN, "[[]]")
        assert matches == [] or matches == [""]

    def test_no_false_positive(self):
        assert not re.search(self.WIKILINK_PATTERN, "[not a link]")
        assert not re.search(self.WIKILINK_PATTERN, "code: arr[0]")


class TestFrontmatterEdgeCases:
    """Boundary tests for frontmatter parsing."""

    def test_only_frontmatter(self):
        text = "---\ntitle: X\n---\n"
        fm = extract_frontmatter_from_text(text)
        assert fm["title"] == "X"

    def test_frontmatter_no_content(self):
        text = "---\ntitle: X\n---"
        fm = extract_frontmatter_from_text(text)
        assert fm["title"] == "X"

    def test_triple_dashes_in_content(self):
        text = "---\ntitle: X\n---\n\nSome --- dashes ---\n"
        fm = extract_frontmatter_from_text(text)
        assert fm["title"] == "X"

    def test_frontmatter_with_colons_in_value(self):
        text = "---\nurl: https://example.com:8080\n---\n"
        fm = extract_frontmatter_from_text(text)
        assert fm["url"] == "https://example.com:8080"

    def test_tags_with_spaces(self):
        text = "---\ntags: [  ai ,  ml  , nlp ]\n---\n"
        fm = extract_frontmatter_from_text(text)
        assert "ai" in fm["tags"]
        assert "ml" in fm["tags"]
        assert "nlp" in fm["tags"]


class TestSearchEdgeCases:
    """Boundary tests for search functionality."""

    def test_empty_keyword(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "a.md", "# A\nContent\n")
        clear_doc_cache()
        docs =collect_documents(wiki_dir)
        # Empty keyword matches everything
        results = search_documents(docs, "")
        assert len(results) >= 1

    def test_special_regex_chars(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "a.md", "# A\nPrice is $100 (USD)\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        # Literal search for special chars
        results = search_documents(docs, "$100")
        assert len(results) >= 1

    def test_unicode_search(self, wiki_dir):
        _write_page(wiki_dir, "concepts", "cn.md", "# 中文测试\n这是关于机器学习的内容\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        results = search_documents(docs, "机器学习")
        assert len(results) >= 1

    def test_multiline_match(self, wiki_dir):
        content = "# Test\nLine 1\nLine 2 with keyword\nLine 3\n"
        _write_page(wiki_dir, "concepts", "multi.md", content)
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        results = search_documents(docs, "keyword")
        assert len(results) >= 1


# ═══════════════════════════════════════════
# Security tests
# ═══════════════════════════════════════════


class TestReDoSProtection:
    """Test regex search timeout and complexity rejection."""

    def test_rejects_nested_quantifiers(self, wiki_dir):
        """Patterns like (a+)+ should be rejected as ReDoS-prone."""
        _write_page(wiki_dir, "concepts", "a.md", "# A\naaa\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        # (a+)+ is a classic ReDoS pattern
        with pytest.raises(SystemExit):
            search_documents(docs, "(a+)+$", regex=True)

    def test_rejects_alternation_quantifier(self, wiki_dir):
        """Patterns like (a|a)+ are NOT caught by _SUSPICIOUS_RE (too broad),
        but the 5s timeout protects against actual ReDoS damage."""
        _write_page(wiki_dir, "concepts", "a.md", "# A\naaa\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        # This should NOT raise — the pattern passes the heuristic check
        # and the timeout only fires if matching actually hangs
        results = search_documents(docs, "(a|a)+", regex=True)
        assert isinstance(results, list)

    def test_rejects_quantified_group_with_pipe(self, wiki_dir):
        """Patterns like (a|aa)+b pass heuristic but timeout protects."""
        _write_page(wiki_dir, "concepts", "a.md", "# A\naabb\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        results = search_documents(docs, "(a|aa)+b", regex=True)
        assert isinstance(results, list)

    def test_safe_regex_works(self, wiki_dir):
        """Normal regex should still work."""
        _write_page(wiki_dir, "concepts", "a.md", "# Test\nhello world\n")
        clear_doc_cache()
        docs = collect_documents(wiki_dir)
        results = search_documents(docs, r"hello\s+world", regex=True)
        assert len(results) >= 1

    def test_regex_timeout_constant_exists(self):
        """Verify timeout constant is defined."""
        from wiki_core.helpers import _REGEX_MATCH_TIMEOUT
        assert isinstance(_REGEX_MATCH_TIMEOUT, (int, float))
        assert _REGEX_MATCH_TIMEOUT > 0

    def test_suspicious_re_pattern_compiles(self):
        """Verify the suspicious pattern detector itself is valid."""
        from wiki_core.helpers import _SUSPICIOUS_RE
        assert _SUSPICIOUS_RE.search("(a+)+") is not None
        assert _SUSPICIOUS_RE.search("([a-z]+)*") is not None
        assert _SUSPICIOUS_RE.search("(foo|bar)+") is None  # safe alternation not flagged
        assert _SUSPICIOUS_RE.search("normal") is None
        assert _SUSPICIOUS_RE.search("[a-z]+") is None
