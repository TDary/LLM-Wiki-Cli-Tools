"""Tests for wiki_core.templates module."""

import sys
from pathlib import Path

import pytest

# Add scripts/ to sys.path so we can import wiki_core
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from wiki_core.templates import template_wiki_page, template_schema, template_readme, template_log
from wiki_core.helpers import today


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
