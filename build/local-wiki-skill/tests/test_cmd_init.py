"""Tests for wiki_core.cmd_init module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from wiki_core import DIRS
from wiki_core.helpers import clear_doc_cache
from wiki_core.cmd_init import cmd_init, cmd_sync, cmd_bootstrap

from conftest import _write_page


def _make_init_args(path, domain="Wiki 知识库", name="", force=False):
    args = type("Args", (), {})()
    args.path = str(path)
    args.domain = domain
    args.name = name
    args.force = force
    return args


def _make_sync_args(path):
    args = type("Args", (), {})()
    args.path = str(path)
    return args


def _make_bootstrap_args(path, domain="Wiki 知识库", name="", force=False):
    args = type("Args", (), {})()
    args.path = str(path)
    args.domain = domain
    args.name = name
    args.force = force
    return args


class TestCmdInit:
    """Tests for cmd_init."""

    def test_creates_directory_structure(self, tmp_path, capsys):
        """Init creates all 7 subdirectories."""
        target = tmp_path / "mywiki"
        args = _make_init_args(target)
        cmd_init(args)

        for d in DIRS:
            assert (target / d).is_dir(), f"Missing directory: {d}/"

    def test_creates_schema_readme_log(self, tmp_path, capsys):
        """Init creates SCHEMA.md, README.md, log.md."""
        target = tmp_path / "mywiki"
        args = _make_init_args(target)
        cmd_init(args)

        assert (target / "SCHEMA.md").exists()
        assert (target / "README.md").exists()
        assert (target / "log.md").exists()

    def test_schema_contains_domain(self, tmp_path, capsys):
        """SCHEMA.md contains the specified domain."""
        target = tmp_path / "mywiki"
        args = _make_init_args(target, domain="AI Research")
        cmd_init(args)

        content = (target / "SCHEMA.md").read_text(encoding="utf-8")
        assert "AI Research" in content

    def test_skip_if_schema_exists_no_force(self, tmp_path, capsys):
        """Init skips if SCHEMA.md exists and --force is not set."""
        target = tmp_path / "mywiki"
        target.mkdir()
        (target / "SCHEMA.md").write_text("# existing", encoding="utf-8")

        args = _make_init_args(target, force=False)
        cmd_init(args)

        captured = capsys.readouterr()
        assert "检测到已有知识库" in captured.out

    def test_force_overwrites_existing(self, tmp_path, capsys):
        """Init with --force overwrites existing files."""
        target = tmp_path / "mywiki"
        target.mkdir()
        (target / "SCHEMA.md").write_text("# old", encoding="utf-8")

        args = _make_init_args(target, force=True)
        cmd_init(args)

        content = (target / "SCHEMA.md").read_text(encoding="utf-8")
        assert "# old" not in content

    def test_output_shows_completion(self, tmp_path, capsys):
        """Init prints completion message."""
        target = tmp_path / "mywiki"
        args = _make_init_args(target)
        cmd_init(args)

        captured = capsys.readouterr()
        assert "init 完成" in captured.out


class TestCmdSync:
    """Tests for cmd_sync."""

    def test_sync_prints_local_mode(self, wiki_dir, capsys):
        """Sync confirms local-only mode."""
        args = _make_sync_args(wiki_dir)
        cmd_sync(args)

        captured = capsys.readouterr()
        assert "本地模式" in captured.out
        assert "无需同步" in captured.out

    def test_sync_requires_wiki(self, tmp_path, capsys):
        """Sync fails if not a wiki directory."""
        args = _make_sync_args(tmp_path)

        with pytest.raises(SystemExit):
            cmd_sync(args)


class TestCmdBootstrap:
    """Tests for cmd_bootstrap."""

    def test_bootstrap_creates_wiki(self, tmp_path, capsys):
        """Bootstrap creates a new wiki at the given path."""
        target = tmp_path / "bootwiki"
        args = _make_bootstrap_args(target)
        cmd_bootstrap(args)

        assert (target / "SCHEMA.md").exists()
        for d in DIRS:
            assert (target / d).is_dir()

    def test_bootstrap_skip_if_exists(self, tmp_path, capsys):
        """Bootstrap skips if wiki already exists."""
        target = tmp_path / "bootwiki"
        target.mkdir()
        (target / "SCHEMA.md").write_text("# existing", encoding="utf-8")

        args = _make_bootstrap_args(target, force=False)
        cmd_bootstrap(args)

        captured = capsys.readouterr()
        assert "检测到已有知识库" in captured.out

    def test_bootstrap_force_overwrites(self, tmp_path, capsys):
        """Bootstrap with --force overwrites existing wiki."""
        target = tmp_path / "bootwiki"
        target.mkdir()
        (target / "SCHEMA.md").write_text("# old", encoding="utf-8")

        args = _make_bootstrap_args(target, force=True)
        cmd_bootstrap(args)

        content = (target / "SCHEMA.md").read_text(encoding="utf-8")
        assert "# old" not in content
