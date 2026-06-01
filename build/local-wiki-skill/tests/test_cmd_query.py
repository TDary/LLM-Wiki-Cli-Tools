"""Tests for wiki_core.cmd_query module."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from wiki_core.helpers import clear_doc_cache
from wiki_core.cmd_query import cmd_list, cmd_search, cmd_backlinks, cmd_tags, cmd_stats, cmd_index

from conftest import _write_page


def _make_list_args(wiki_dir, fmt="text", category="", tags="", include_raw=False, pretty=False):
    args = type("Args", (), {})()
    args.path = str(wiki_dir)
    args.format = fmt
    args.category = category
    args.tags = tags
    args.include_raw = include_raw
    args.pretty = pretty
    return args


def _make_search_args(wiki_dir, keyword, fmt="text", no_raw=False, regex=False, use_index=False, pretty=False):
    args = type("Args", (), {})()
    args.path = str(wiki_dir)
    args.keyword = keyword
    args.format = fmt
    args.no_raw = no_raw
    args.regex = regex
    args.use_index = use_index
    args.pretty = pretty
    return args


def _make_backlinks_args(wiki_dir, page, fmt="text", pretty=False):
    args = type("Args", (), {})()
    args.path = str(wiki_dir)
    args.page = page
    args.format = fmt
    args.pretty = pretty
    return args


def _make_tags_args(wiki_dir, fmt="text", sort="count", pretty=False):
    args = type("Args", (), {})()
    args.path = str(wiki_dir)
    args.format = fmt
    args.sort = sort
    args.pretty = pretty
    return args


def _make_stats_args(wiki_dir, fmt="text", pretty=False):
    args = type("Args", (), {})()
    args.path = str(wiki_dir)
    args.format = fmt
    args.pretty = pretty
    return args


def _make_index_args(wiki_dir, output="", pretty=False):
    args = type("Args", (), {})()
    args.path = str(wiki_dir)
    args.output = output
    args.pretty = pretty
    return args


class TestCmdList:
    """Tests for cmd_list."""

    def test_list_shows_documents(self, wiki_dir, capsys):
        """List displays documents in the wiki."""
        _write_page(wiki_dir, "concepts", "test.md",
                    "---\ntitle: Test\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Test\n")
        clear_doc_cache()

        args = _make_list_args(wiki_dir)
        cmd_list(args)

        captured = capsys.readouterr()
        assert "Test" in captured.out

    def test_list_json_format(self, wiki_dir, capsys):
        """List with --format json outputs valid JSON."""
        _write_page(wiki_dir, "concepts", "test.md",
                    "---\ntitle: Test\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Test\n")
        clear_doc_cache()

        args = _make_list_args(wiki_dir, fmt="json")
        cmd_list(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total" in data
        assert data["total"] >= 1

    def test_list_filter_by_category(self, wiki_dir, capsys):
        """List with --category filters to specific directory."""
        _write_page(wiki_dir, "concepts", "c1.md",
                    "---\ntitle: C1\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# C1\n")
        _write_page(wiki_dir, "entities", "e1.md",
                    "---\ntitle: E1\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: entity\ntags: [AI]\nsources: []\n---\n\n# E1\n")
        clear_doc_cache()

        args = _make_list_args(wiki_dir, fmt="json", category="concepts")
        cmd_list(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for doc in data["documents"]:
            assert doc["category"] == "concepts"

    def test_list_filter_by_tags(self, wiki_dir, capsys):
        """List with --tags filters by tag."""
        _write_page(wiki_dir, "concepts", "ai.md",
                    "---\ntitle: AI Doc\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# AI\n")
        _write_page(wiki_dir, "concepts", "math.md",
                    "---\ntitle: Math Doc\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [math]\nsources: []\n---\n\n# Math\n")
        clear_doc_cache()

        args = _make_list_args(wiki_dir, fmt="json", tags="AI")
        cmd_list(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for doc in data["documents"]:
            assert "AI" in doc.get("tags", [])

    def test_list_excludes_raw_by_default(self, wiki_dir, capsys):
        """List excludes raw/ and normalized/ by default."""
        _write_page(wiki_dir, "concepts", "c.md",
                    "---\ntitle: C\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# C\n")
        _write_page(wiki_dir, "raw", "r.md", "# Raw\n")
        clear_doc_cache()

        args = _make_list_args(wiki_dir, fmt="json")
        cmd_list(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for doc in data["documents"]:
            assert doc["category"] not in ("raw", "normalized")

    def test_list_include_raw(self, wiki_dir, capsys):
        """List with --include-raw includes raw/ and normalized/."""
        _write_page(wiki_dir, "concepts", "c.md",
                    "---\ntitle: C\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# C\n")
        _write_page(wiki_dir, "raw", "r.md", "# Raw\n")
        clear_doc_cache()

        args = _make_list_args(wiki_dir, fmt="json", include_raw=True)
        cmd_list(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        categories = {doc["category"] for doc in data["documents"]}
        assert "raw" in categories


class TestCmdSearch:
    """Tests for cmd_search."""

    def test_search_finds_keyword(self, wiki_dir, capsys):
        """Search finds documents containing the keyword."""
        _write_page(wiki_dir, "concepts", "transformer.md",
                    "---\ntitle: Transformer\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Transformer\n\nThe transformer architecture uses attention.\n")
        clear_doc_cache()

        args = _make_search_args(wiki_dir, "attention")
        cmd_search(args)

        captured = capsys.readouterr()
        assert "Transformer" in captured.out
        assert "attention" in captured.out.lower()

    def test_search_json_format(self, wiki_dir, capsys):
        """Search with --format json outputs valid JSON."""
        _write_page(wiki_dir, "concepts", "test.md",
                    "---\ntitle: Test\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Test\n\nHello world.\n")
        clear_doc_cache()

        args = _make_search_args(wiki_dir, "hello", fmt="json")
        cmd_search(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total" in data
        assert data["total"] >= 1

    def test_search_no_results(self, wiki_dir, capsys):
        """Search returns empty for non-matching keyword."""
        _write_page(wiki_dir, "concepts", "test.md",
                    "---\ntitle: Test\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Test\n")
        clear_doc_cache()

        args = _make_search_args(wiki_dir, "nonexistent", fmt="json")
        cmd_search(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total"] == 0

    def test_search_regex(self, wiki_dir, capsys):
        """Search with --regex supports regex patterns."""
        _write_page(wiki_dir, "concepts", "test.md",
                    "---\ntitle: Test\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Test\n\nfoo123 bar456\n")
        clear_doc_cache()

        args = _make_search_args(wiki_dir, r"foo\d+", regex=True, fmt="json")
        cmd_search(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total"] >= 1

    def test_search_no_raw(self, wiki_dir, capsys):
        """Search with --no-raw excludes raw/ and normalized/."""
        _write_page(wiki_dir, "concepts", "c.md",
                    "---\ntitle: C\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# C\n\nkeyword here\n")
        _write_page(wiki_dir, "raw", "r.md", "# Raw\n\nkeyword here\n")
        clear_doc_cache()

        args = _make_search_args(wiki_dir, "keyword", no_raw=True, fmt="json")
        cmd_search(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for r in data["results"]:
            assert r["category"] not in ("raw", "normalized")


class TestCmdBacklinks:
    """Tests for cmd_backlinks."""

    def test_backlinks_finds_references(self, wiki_dir, capsys):
        """Backlinks finds pages linking to the target."""
        _write_page(wiki_dir, "concepts", "target.md",
                    "---\ntitle: Target\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Target\n")
        _write_page(wiki_dir, "concepts", "ref.md",
                    "---\ntitle: Ref\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Ref\n\nSee [[target]] for details.\n")
        clear_doc_cache()

        args = _make_backlinks_args(wiki_dir, "target", fmt="json")
        cmd_backlinks(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total"] >= 1

    def test_backlinks_no_results(self, wiki_dir, capsys):
        """Backlinks returns empty for unreferenced page."""
        _write_page(wiki_dir, "concepts", "orphan.md",
                    "---\ntitle: Orphan\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Orphan\n")
        clear_doc_cache()

        args = _make_backlinks_args(wiki_dir, "orphan", fmt="json")
        cmd_backlinks(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total"] == 0

    def test_backlinks_strips_md_extension(self, wiki_dir, capsys):
        """Backlinks handles page names with .md extension."""
        _write_page(wiki_dir, "concepts", "target.md",
                    "---\ntitle: Target\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Target\n")
        _write_page(wiki_dir, "concepts", "ref.md",
                    "---\ntitle: Ref\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Ref\n\nSee [[target]].\n")
        clear_doc_cache()

        args = _make_backlinks_args(wiki_dir, "target.md", fmt="json")
        cmd_backlinks(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total"] >= 1


class TestCmdTags:
    """Tests for cmd_tags."""

    def test_tags_lists_tags(self, wiki_dir, capsys):
        """Tags lists all tags with counts."""
        _write_page(wiki_dir, "concepts", "c1.md",
                    "---\ntitle: C1\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI, tech]\nsources: []\n---\n\n# C1\n")
        _write_page(wiki_dir, "concepts", "c2.md",
                    "---\ntitle: C2\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# C2\n")
        clear_doc_cache()

        args = _make_tags_args(wiki_dir, fmt="json")
        cmd_tags(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total"] >= 2
        tag_names = [t["tag"] for t in data["tags"]]
        assert "AI" in tag_names
        assert "tech" in tag_names

    def test_tags_sort_by_name(self, wiki_dir, capsys):
        """Tags with --sort name sorts alphabetically."""
        _write_page(wiki_dir, "concepts", "c1.md",
                    "---\ntitle: C1\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [zebra, alpha]\nsources: []\n---\n\n# C1\n")
        clear_doc_cache()

        args = _make_tags_args(wiki_dir, fmt="json", sort="name")
        cmd_tags(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        tag_names = [t["tag"] for t in data["tags"]]
        assert tag_names == sorted(tag_names, key=str.lower)

    def test_tags_excludes_raw(self, wiki_dir, capsys):
        """Tags excludes tags from raw/ and normalized/ documents."""
        _write_page(wiki_dir, "concepts", "c.md",
                    "---\ntitle: C\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# C\n")
        _write_page(wiki_dir, "raw", "r.md",
                    "---\ntitle: R\ntags: [rawtag]\nsources: []\n---\n\n# R\n")
        clear_doc_cache()

        args = _make_tags_args(wiki_dir, fmt="json")
        cmd_tags(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        tag_names = [t["tag"] for t in data["tags"]]
        assert "rawtag" not in tag_names


class TestCmdStats:
    """Tests for cmd_stats."""

    def test_stats_shows_counts(self, wiki_dir, capsys):
        """Stats shows document counts and tag stats."""
        _write_page(wiki_dir, "concepts", "c.md",
                    "---\ntitle: C\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# C\n\n[[other]]\n")
        clear_doc_cache()

        args = _make_stats_args(wiki_dir, fmt="json")
        cmd_stats(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total_documents" in data
        assert data["total_documents"] >= 1
        assert "unique_tags" in data
        assert "link_density" in data
        assert "orphan_count" in data

    def test_stats_empty_wiki(self, wiki_dir, capsys):
        """Stats handles empty wiki gracefully."""
        args = _make_stats_args(wiki_dir, fmt="json")
        cmd_stats(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total_documents"] == 0


class TestCmdIndex:
    """Tests for cmd_index."""

    def test_index_generates_json(self, wiki_dir, capsys):
        """Index generates a valid JSON index file."""
        _write_page(wiki_dir, "concepts", "test.md",
                    "---\ntitle: Test\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Test\n\nHello world.\n")
        clear_doc_cache()

        args = _make_index_args(wiki_dir)
        cmd_index(args)

        index_path = wiki_dir / "queries" / "index.json"
        assert index_path.exists()

        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert "total_documents" in data
        assert "inverted_index" in data
        assert "categories" in data
        assert data["total_documents"] >= 1

    def test_index_inverted_index_has_entries(self, wiki_dir, capsys):
        """Index builds inverted index with word entries."""
        _write_page(wiki_dir, "concepts", "test.md",
                    "---\ntitle: Test\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Test\n\nTransformer architecture.\n")
        clear_doc_cache()

        args = _make_index_args(wiki_dir)
        cmd_index(args)

        index_path = wiki_dir / "queries" / "index.json"
        data = json.loads(index_path.read_text(encoding="utf-8"))
        inv = data["inverted_index"]
        assert "transformer" in inv
        assert "architecture" in inv

    def test_index_custom_output_path(self, wiki_dir, capsys):
        """Index with --output writes to custom path."""
        _write_page(wiki_dir, "concepts", "test.md",
                    "---\ntitle: Test\ncreated: 2025-01-01\nupdated: 2025-01-01\ntype: concept\ntags: [AI]\nsources: []\n---\n\n# Test\n")
        clear_doc_cache()

        custom_path = str(wiki_dir / "custom" / "idx.json")
        args = _make_index_args(wiki_dir, output=custom_path)
        cmd_index(args)

        assert Path(custom_path).exists()
