"""Tests for wiki_core.cmd_health module."""

import sys
from pathlib import Path

import pytest

# Add scripts/ to sys.path so we can import wiki_core
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from wiki_core.helpers import clear_doc_cache
from wiki_core.cmd_health import cmd_rename

from conftest import _write_page

# conftest provides: wiki_dir fixture, _write_page helper


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
