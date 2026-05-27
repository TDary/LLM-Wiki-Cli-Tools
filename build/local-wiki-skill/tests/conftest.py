"""Shared fixtures for wiki_core tests."""

import sys
import textwrap
from pathlib import Path

import pytest

# Add scripts/ to sys.path so we can import wiki_core
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from wiki_core import DIRS
from wiki_core.helpers import clear_doc_cache


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
