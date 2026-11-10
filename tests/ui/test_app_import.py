"""The UI module can be imported without starting anything; static checks of its source."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "src" / "redactech" / "ui" / "app.py"


@pytest.mark.ui
def test_importing_the_app_starts_nothing():
    import redactech.ui.app as app

    assert callable(app.main) and app.PROJECT == "rt_project"


def test_fixed_widget_keys_are_unique_and_numerous():
    source = APP.read_text(encoding="utf-8")
    keys = re.findall(r'key="([^"{]+)"', source)
    assert len(keys) >= 20 and len(keys) == len(set(keys))
    for needed in ("ws_load", "prepare", "policy_confirm", "accept_all", "write", "doc_select"):
        assert needed in keys


def test_the_app_never_sets_auto_accept():
    source = APP.read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]  # after the module docstring, which names it to deny it
    assert "auto_accept" not in body and "auto-accept" not in body


def test_the_page_is_built_by_main_only():
    source = APP.read_text(encoding="utf-8")
    assert source.rstrip().endswith('if __name__ == "__main__":\n    main()')
    top_level_calls = re.findall(r"^st\.", source, flags=re.MULTILINE)
    assert top_level_calls == []
