"""The inline JavaScript in every page has to parse.

Nothing else in this suite can catch a syntax error there. The pages render server-side, the
API tests never run a browser, and a template with a broken script returns HTTP 200 with the
right bytes -- it simply draws the heading and then nothing at all. That is exactly how the
workbook page shipped: one stray backslash closed a string early and the whole file failed to
parse, silently.

`node --check` is the cheapest real parser available. Where node is absent the check is skipped
with a reason rather than passing quietly, because a skipped check that reads as a pass is the
same failure in a different place.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parent.parent / "zaco" / "web" / "templates"
SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)

#: Jinja inside a script block is not JavaScript and node cannot be expected to read it. None of
#: the pages do this today; the guard is here so that one starting to does not fail confusingly.
JINJA = re.compile(r"\{%|\{\{")


def _pages() -> list[Path]:
    return sorted(TEMPLATES.glob("*.html"))


def test_there_are_pages_to_check() -> None:
    """A glob that silently matches nothing would make every case below vacuously true."""
    assert len(_pages()) >= 5


@pytest.mark.parametrize("page", _pages(), ids=lambda p: p.name)
def test_the_inline_script_parses(page: Path, tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH, so the inline scripts cannot be parsed")

    blocks = [b for b in SCRIPT.findall(page.read_text(encoding="utf-8")) if b.strip()]
    for index, block in enumerate(blocks):
        if JINJA.search(block):
            continue
        scratch = tmp_path / f"{page.stem}-{index}.js"
        scratch.write_text(block, encoding="utf-8")
        result = subprocess.run(
            [node, "--check", str(scratch)], capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, (
            f"{page.name} block {index + 1} does not parse:\n{result.stderr}"
        )


@pytest.mark.parametrize("page", _pages(), ids=lambda p: p.name)
def test_every_page_extends_the_shell(page: Path) -> None:
    """A page that forgets to extend `base.html` renders without the nav and without the styles,
    which looks like a broken deploy rather than a missing line."""
    text = page.read_text(encoding="utf-8")
    if page.name == "base.html":
        assert "{% block content %}" in text
        return
    assert text.lstrip().startswith('{% extends "base.html" %}'), (
        f"{page.name} does not extend the shell"
    )
