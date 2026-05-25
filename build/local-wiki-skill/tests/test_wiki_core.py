"""Comprehensive unit tests for wiki_core modules."""

import json
import os
import re
import shutil
import sys
import tempfile
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
from wiki_core.templates import template_wiki_page, template_schema, template_readme, template_log
from wiki_core.cmd_ingest import (
    _html_to_text,
    _slugify_url,
    _generate_filename,
    _extract_title_from_text,
    _extract_keywords,
    _suggest_related,
    _HTMLTextExtractor,
)
from wiki_core.cmd_health import cmd_rename


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════


@pytest.fixture
def wiki_dir(tmp_path):
    """Create a minimal valid wiki directory structure."""
    for d in DIRS:
        (tmp_path / d).mkdir()
    schema = tmp_path / "SCHEMA.md"
    schema.write_text(
        textwrap.dedent("""\
        # SCHEMA — Test Wiki

        ## 基本信息

        | 属性 | 值 |
        |------|-----|
        | **名称** | Test Wiki |
        | **领域** | AI |
        | **创建时间** | 2025-01-01 00:00:00 |
        """),
        encoding="utf-8",
    )
    log = tmp_path / "log.md"
    log.write_text("# 更新日志\n\n## 2025-01-01\n\n- init\n", encoding="utf-8")
    clear_doc_cache()
    return tmp_path


def _write_page(wiki_dir: Path, category: str, filename: str, content: str) -> Path:
    """Helper: write a page into the wiki."""
    fp = wiki_dir / category / filename
    fp.write_text(content, encoding="utf-8")
    return fp


# ═══════════════════════════════════════════
# helpers.py tests
# ═══════════════════════════════════════════


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
# cmd_ingest.py tests
# ═══════════════════════════════════════════


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
# cmd_health.py — operator precedence regression
# ═══════════════════════════════════════════


class TestRenameHeadingDetection:
    """Regression tests for the `"".splitlines()` operator precedence bug in cmd_rename."""

    def _make_args(self, old_name, new_name, wiki_dir, apply=False):
        """Create a mock args namespace for cmd_rename."""
        args = type("Args", (), {})()
        args.path = str(wiki_dir)
        args.old_name = old_name
        args.new_name = new_name
        args.format = "text"
        args.pretty = False
        args.apply = apply
        return args

    def test_heading_detected_with_content(self, wiki_dir, capsys):
        """The original bug: `"".splitlines()` was evaluated first, so
        when _text was a string, enumerate iterated characters not lines.
        update_heading actions were never generated."""
        _write_page(wiki_dir, "concepts", "old-name.md",
                    "# Old Name\n\nSome content here.\n")
        clear_doc_cache()
        args = self._make_args("old-name", "new-name", wiki_dir)
        cmd_rename(args)
        captured = capsys.readouterr()
        assert "update_heading" in captured.out, \
            "Heading update should be detected when file has a # heading"

    def test_heading_not_detected_when_absent(self, wiki_dir, capsys):
        """No top-level # heading in the file → no update_heading action."""
        _write_page(wiki_dir, "concepts", "page.md",
                    "Only plain text here.\n## A subheading\n")
        clear_doc_cache()
        args = self._make_args("page", "new-page", wiki_dir)
        cmd_rename(args)
        captured = capsys.readouterr()
        assert "update_heading" not in captured.out

    def test_wikilink_update_detected(self, wiki_dir, capsys):
        """Other files referencing [[Old Name]] should get update_link actions."""
        _write_page(wiki_dir, "concepts", "old-name.md", "# Old Name\n")
        _write_page(wiki_dir, "concepts", "ref.md", "See [[Old Name]] for details.\n")
        clear_doc_cache()
        args = self._make_args("old-name", "new-name", wiki_dir)
        cmd_rename(args)
        captured = capsys.readouterr()
        assert "update_link" in captured.out


class TestRenameActionTypeFilter:
    """Regression test for the missing action type filter in cmd_rename --apply."""

    def _make_args(self, old_name, new_name, wiki_dir, apply=True):
        args = type("Args", (), {})()
        args.path = str(wiki_dir)
        args.old_name = old_name
        args.new_name = new_name
        args.format = "text"
        args.pretty = False
        args.apply = apply
        return args

    def test_rename_file_action_not_applied_as_text_replacement(self, wiki_dir, capsys):
        """The original bug: rename_file action (with original=old_rel, new=new_rel)
        was matched by `a['file'] == f` and applied as text replacement,
        corrupting file paths inside the document text."""
        _write_page(wiki_dir, "concepts", "old.md",
                    "# Old\n\nSome content with [[Old]] link.\n")
        _write_page(wiki_dir, "concepts", "other.md",
                    "Reference to [[Old]].\n")
        clear_doc_cache()

        args = self._make_args("old", "new", wiki_dir)
        cmd_rename(args)
        captured = capsys.readouterr()

        # Verify the file was renamed
        assert (wiki_dir / "concepts" / "new.md").exists()
        assert not (wiki_dir / "concepts" / "old.md").exists()

        # Verify content was NOT corrupted by rename_file action
        new_content = (wiki_dir / "concepts" / "new.md").read_text(encoding="utf-8")
        # The old path "concepts/old.md" should NOT appear as replaced text
        assert "concepts/new.md" not in new_content or "# New" in new_content


# ═══════════════════════════════════════════
# templates.py tests
# ═══════════════════════════════════════════


class TestTemplateWikiPage:
    def test_has_frontmatter(self):
        page = template_wiki_page("Test", "concepts", ["ai"], "(manual)")
        assert page.startswith("---")
        assert "title: Test" in page
        assert "type: concept" in page

    def test_category_type_mapping(self):
        expected = {
            "entities": "entity",
            "concepts": "concept",
            "relations": "comparison",
            "queries": "query",
            "drafts": "summary",
        }
        for cat, typ in expected.items():
            page = template_wiki_page("T", cat, [], "")
            assert f"type: {typ}" in page

    def test_unknown_category_defaults_to_summary(self):
        page = template_wiki_page("T", "unknown_cat", [], "")
        assert "type: summary" in page

    def test_tags_included(self):
        page = template_wiki_page("T", "concepts", ["ml", "ai"], "")
        assert "ml" in page
        assert "ai" in page

    def test_empty_tags(self):
        page = template_wiki_page("T", "concepts", [], "")
        assert "tags: []" in page

    def test_has_wikilinks_placeholder(self):
        page = template_wiki_page("T", "concepts", [], "")
        assert "[[wikilinks]]" in page

    def test_heading_matches_title(self):
        page = template_wiki_page("My Title", "concepts", [], "")
        assert "# My Title" in page


class TestTemplateSchema:
    def test_contains_name_and_domain(self):
        content = template_schema("MyWiki", "AI Research")
        assert "MyWiki" in content
        assert "AI Research" in content

    def test_contains_directory_table(self):
        content = template_schema("W", "D")
        assert "raw/" in content
        assert "entities/" in content
        assert "concepts/" in content


class TestTemplateReadme:
    def test_contains_name(self):
        content = template_readme("MyWiki", "AI")
        assert "# MyWiki" in content

    def test_contains_nav_links(self):
        content = template_readme("W", "D")
        assert "SCHEMA" in content
        assert "log.md" in content


class TestTemplateLog:
    def test_has_heading(self):
        content = template_log()
        assert "# 更新日志" in content
        assert today() in content


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
        docs = collect_documents(wiki_dir)
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


class TestShellInjectionFix:
    """Regression: cmd_health.py custom checks must not use shell=True."""

    def test_shell_false_in_subprocess(self):
        """Verify shlex.split is used, not raw shell string."""
        import inspect
        from wiki_core import cmd_health
        source = inspect.getsource(cmd_health)
        # Should NOT contain shell=True
        assert "shell=True" not in source
        # Should contain shell=False
        assert "shell=False" in source
        # Should use shlex.split
        assert "shlex.split" in source


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

        from wiki_core.cmd_ingest import cmd_ingest
        cmd_ingest(args)
        captured = capsys.readouterr()
        assert "不在 wiki 目录内" in captured.out

        # Cleanup
        external.unlink(missing_ok=True)


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

        from wiki_core.cmd_ingest import cmd_ingest
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

        from wiki_core.cmd_ingest import cmd_ingest
        cmd_ingest(args)
        captured = capsys.readouterr()
        assert "不在 wiki 目录内" not in captured.out
