"""Tests of the privacy tooling. Only invented terms are used here."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
sys.path.insert(0, str(TOOLS))

import privacy  # noqa: E402

TERMS = ["Zorglubcorp", r"Qwer[a-z]+x"]
ZERO_SHA = "0" * 40


def _env(**extra: str) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_") and not k.startswith("REDACTECH_")
    }
    env["REDACTECH_DENYLIST"] = "\n".join(TERMS)
    env.update(extra)
    return env


def _run(args: list[str | Path], cwd: Path, env: dict[str, str], stdin: str | None = None):
    return subprocess.run(
        [str(a) for a in args],
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _git(repo: Path, *args: str) -> str:
    res = _run(["git", *args], repo, _env())
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "work"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.name", "Tester")
    _git(r, "config", "user.email", "tester@example.invalid")
    _git(r, "config", "commit.gpgsign", "false")
    return r


# --- scan_text -----------------------------------------------------------------


def test_whole_word_case_insensitive():
    hits = privacy.scan_text("a ZORGLUBCORP b\nclean line\nzorglubcorp.", TERMS)
    assert [m.line for m in hits] == [1, 3]


def test_no_match_inside_a_longer_word():
    assert privacy.scan_text("xZorglubcorpy and Zorglubcorps", TERMS) == []


def test_regex_term():
    hits = privacy.scan_text("see Qwertyx here", TERMS)
    assert len(hits) == 1


def test_allowlist_exempts_exact_string():
    text = "contact Zorglubcorp"
    assert privacy.scan_text(text, TERMS, allow=["contact Zorglubcorp"]) == []
    assert len(privacy.scan_text("other Zorglubcorp", TERMS, allow=["contact Zorglubcorp"])) == 1


def test_masking_never_leaks_the_term():
    hits = privacy.scan_text("hello Zorglubcorp and Qwertyx!", TERMS, source="f.txt")
    assert len(hits) == 1
    shown = str(hits[0])
    assert "***" in shown
    assert "zorglubcorp" not in shown.lower()
    assert "qwertyx" not in shown.lower()
    assert hits[0].excerpt == "hello *** and ***!"


def test_scan_paths_masks_file_names(tmp_path: Path):
    f = tmp_path / "notes_Zorglubcorp.txt"
    f.write_text("nothing\n", encoding="utf-8")
    hits = privacy.scan_paths([f], TERMS, root=tmp_path)
    assert len(hits) == 1
    assert "zorglubcorp" not in str(hits[0]).lower()


# --- denylist loading ----------------------------------------------------------


def test_env_denylist_override(monkeypatch):
    monkeypatch.setenv("REDACTECH_DENYLIST", "Alpha\n# comment\n\nBeta")
    assert privacy.load_denylist() == ["Alpha", "Beta"]


def test_denylist_file_override(monkeypatch, tmp_path: Path):
    f = tmp_path / "deny.txt"
    f.write_text("# c\nGamma\n", encoding="utf-8")
    monkeypatch.delenv("REDACTECH_DENYLIST", raising=False)
    monkeypatch.setenv("REDACTECH_DENYLIST_FILE", str(f))
    assert privacy.load_denylist() == ["Gamma"]


def test_denylist_found_in_main_checkout_from_a_worktree(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("REDACTECH_DENYLIST", raising=False)
    monkeypatch.delenv("REDACTECH_DENYLIST_FILE", raising=False)
    main = tmp_path / "main"
    main.mkdir()
    env = _env()
    _run(["git", "init", "-q"], main, env)
    for k, v in (("user.name", "T"), ("user.email", "t@example.invalid")):
        _run(["git", "config", k, v], main, env)
    (main / "a.txt").write_text("x", encoding="utf-8")
    _run(["git", "add", "."], main, env)
    _run(["git", "commit", "-q", "-m", "init"], main, env)
    wt = tmp_path / "wt"
    res = _run(["git", "worktree", "add", "-q", str(wt), "-b", "side"], main, env)
    assert res.returncode == 0, res.stderr
    (main / ".agents").mkdir()
    (main / ".agents" / "denylist.txt").write_text("Delta\n", encoding="utf-8")
    assert privacy.main_checkout(wt).resolve() == main.resolve()
    assert privacy.load_denylist(wt) == ["Delta"]


def test_no_denylist_notice_and_exit_zero(repo: Path):
    env = _env()
    del env["REDACTECH_DENYLIST"]
    res = _run([sys.executable, TOOLS / "privacy.py", "scan", "--tracked"], repo, env)
    assert res.returncode == 0
    assert "no denylist" in (res.stdout + res.stderr).lower()


def test_cli_text_file_hit_and_clean(tmp_path: Path):
    bad = tmp_path / "bad.txt"
    bad.write_text("ok\nthe Zorglubcorp deal\n", encoding="utf-8")
    good = tmp_path / "good.txt"
    good.write_text("nothing here\n", encoding="utf-8")
    res = _run([sys.executable, TOOLS / "privacy.py", "scan", "--text-file", bad], tmp_path, _env())
    assert res.returncode == 1
    out = res.stdout + res.stderr
    assert "***" in out and "zorglubcorp" not in out.lower()
    res = _run([sys.executable, TOOLS / "privacy.py", "scan", "--text-file", good], tmp_path, _env())
    assert res.returncode == 0


# --- hooks ---------------------------------------------------------------------


def test_commit_msg_rejects_term(tmp_path: Path):
    msg = tmp_path / "MSG"
    msg.write_text("Add feature for Zorglubcorp\n", encoding="utf-8")
    res = _run([sys.executable, TOOLS / "hooks" / "commit_msg.py", msg], tmp_path, _env())
    assert res.returncode == 1
    assert "zorglubcorp" not in (res.stdout + res.stderr).lower()


def test_commit_msg_rejects_term_on_hash_line(tmp_path: Path):
    msg = tmp_path / "MSG"
    msg.write_text("Fix bug\n#12 Zorglubcorp\n", encoding="utf-8")
    res = _run([sys.executable, TOOLS / "hooks" / "commit_msg.py", msg], tmp_path, _env())
    assert res.returncode == 1
    assert "zorglubcorp" not in (res.stdout + res.stderr).lower()


def test_commit_msg_accepts_clean(tmp_path: Path):
    msg = tmp_path / "MSG"
    msg.write_text("Add feature (#12)\n", encoding="utf-8")
    res = _run([sys.executable, TOOLS / "hooks" / "commit_msg.py", msg], tmp_path, _env())
    assert res.returncode == 0


def test_long_or_padded_clean_name_is_not_a_hit():
    assert privacy.scan_named_content("a/" * 100 + "x.txt", None, TERMS) == []
    assert privacy.scan_named_content(" padded.txt ", None, TERMS) == []


def test_gh_safe_file_args_stdin_and_input():
    sys.path.insert(0, str(TOOLS))
    import gh_safe

    assert gh_safe._file_args(["api", "-F", "k=@-"]) == ([], True)
    assert gh_safe._file_args(["api", "--input", "req.json"]) == (["req.json"], False)
    assert gh_safe._file_args(["api", "-F", "k=@f.txt"]) == (["f.txt"], False)


def test_pre_commit_rejects_staged_content(repo: Path):
    (repo / "a.txt").write_text("line\nZorglubcorp inside\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    res = _run([sys.executable, TOOLS / "hooks" / "pre_commit.py"], repo, _env())
    assert res.returncode == 1
    assert "zorglubcorp" not in (res.stdout + res.stderr).lower()


def test_pre_commit_scans_the_index_not_the_working_tree(repo: Path):
    f = repo / "a.txt"
    f.write_text("clean\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    f.write_text("Zorglubcorp only in working tree\n", encoding="utf-8")
    res = _run([sys.executable, TOOLS / "hooks" / "pre_commit.py"], repo, _env())
    assert res.returncode == 0


def test_pre_commit_rejects_staged_file_name(repo: Path):
    (repo / "Qwertyx_notes.txt").write_text("harmless\n", encoding="utf-8")
    _git(repo, "add", ".")
    res = _run([sys.executable, TOOLS / "hooks" / "pre_commit.py"], repo, _env())
    assert res.returncode == 1
    assert "qwertyx" not in (res.stdout + res.stderr).lower()


def test_pre_commit_accepts_clean(repo: Path):
    (repo / "a.txt").write_text("all good\n", encoding="utf-8")
    _git(repo, "add", ".")
    res = _run([sys.executable, TOOLS / "hooks" / "pre_commit.py"], repo, _env())
    assert res.returncode == 0, res.stderr


def _commit(repo: Path, message: str) -> str:
    (repo / "f.txt").write_text("content\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "--no-verify", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def test_pre_push_rejects_commit_message_without_remote(repo: Path):
    sha = _commit(repo, "Work for Zorglubcorp")
    stdin = f"refs/heads/main {sha} refs/heads/main {ZERO_SHA}\n"
    res = _run([sys.executable, TOOLS / "hooks" / "pre_push.py", "origin", "none"], repo, _env(), stdin)
    assert res.returncode == 1
    assert "zorglubcorp" not in (res.stdout + res.stderr).lower()


def test_pre_push_rejects_diff_content(repo: Path):
    (repo / "f.txt").write_text("Qwertyx leaked\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "--no-verify", "-m", "innocent")
    sha = _git(repo, "rev-parse", "HEAD")
    stdin = f"refs/heads/main {sha} refs/heads/main {ZERO_SHA}\n"
    res = _run([sys.executable, TOOLS / "hooks" / "pre_push.py", "origin", "none"], repo, _env(), stdin)
    assert res.returncode == 1


def test_pre_push_rejects_branch_name(repo: Path):
    sha = _commit(repo, "innocent")
    stdin = f"refs/heads/feat-zorglubcorp {sha} refs/heads/feat-zorglubcorp {ZERO_SHA}\n"
    res = _run([sys.executable, TOOLS / "hooks" / "pre_push.py", "origin", "none"], repo, _env(), stdin)
    assert res.returncode == 1
    assert "zorglubcorp" not in (res.stdout + res.stderr).lower()


def test_pre_push_rejects_annotated_tag_message(repo: Path):
    _commit(repo, "innocent")
    _git(repo, "tag", "-a", "v1", "-m", "release for Zorglubcorp")
    tag_sha = _git(repo, "rev-parse", "v1")
    stdin = f"refs/tags/v1 {tag_sha} refs/tags/v1 {ZERO_SHA}\n"
    res = _run([sys.executable, TOOLS / "hooks" / "pre_push.py", "origin", "none"], repo, _env(), stdin)
    assert res.returncode == 1
    assert "zorglubcorp" not in (res.stdout + res.stderr).lower()


def test_pre_push_accepts_clean_and_deletions(repo: Path):
    sha = _commit(repo, "innocent change")
    stdin = (
        f"refs/heads/main {sha} refs/heads/main {ZERO_SHA}\n"
        f"(delete) {ZERO_SHA} refs/heads/old {sha}\n"
    )
    res = _run([sys.executable, TOOLS / "hooks" / "pre_push.py", "origin", "none"], repo, _env(), stdin)
    assert res.returncode == 0, res.stderr


# --- install_hooks --------------------------------------------------------------


def test_install_hooks_idempotent_and_effective(repo: Path):
    shutil.copytree(TOOLS, repo / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    for _ in range(2):
        res = _run([sys.executable, repo / "tools" / "install_hooks.py"], repo, _env())
        assert res.returncode == 0, res.stderr
    for name in ("pre-commit", "commit-msg", "pre-push"):
        text = (repo / ".git" / "hooks" / name).read_text(encoding="utf-8")
        assert text.startswith("#!/bin/sh")
        assert not (repo / ".git" / "hooks" / f"{name}.orig").exists()
    (repo / "a.txt").write_text("Zorglubcorp\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    res = _run(["git", "commit", "-q", "-m", "x"], repo, _env())
    assert res.returncode != 0
    (repo / "a.txt").write_text("fine\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    res = _run(["git", "commit", "-q", "-m", "ok"], repo, _env())
    assert res.returncode == 0, res.stderr


# --- gh_safe -------------------------------------------------------------------

FAKE_GH = """\
import os, sys
open(os.environ["FAKE_GH_LOG"], "w", encoding="utf-8").write("\\n".join(sys.argv[1:]))
"""


@pytest.fixture
def fake_gh(tmp_path: Path):
    script = tmp_path / "fake_gh.py"
    script.write_text(FAKE_GH, encoding="utf-8")
    log = tmp_path / "gh.log"
    return script, log


def _gh_safe(args: list[str], fake_gh, cwd: Path, stdin: str | None = None):
    script, log = fake_gh
    env = _env(GH_SAFE_GH=str(script), FAKE_GH_LOG=str(log))
    return _run([sys.executable, TOOLS / "gh_safe.py", *args], cwd, env, stdin)


def test_gh_safe_refuses_term_in_title(fake_gh, tmp_path: Path):
    res = _gh_safe(["issue", "create", "--title", "About Zorglubcorp"], fake_gh, tmp_path)
    assert res.returncode == 1
    assert not fake_gh[1].exists()
    assert "zorglubcorp" not in (res.stdout + res.stderr).lower()


def test_gh_safe_refuses_term_in_body_file(fake_gh, tmp_path: Path):
    body = tmp_path / "body.md"
    body.write_text("fine\nbut Qwertyx here\n", encoding="utf-8")
    res = _gh_safe(["pr", "create", "--title", "ok", "--body-file", str(body)], fake_gh, tmp_path)
    assert res.returncode == 1
    assert not fake_gh[1].exists()
    res = _gh_safe(["pr", "create", "-F", str(body)], fake_gh, tmp_path)
    assert res.returncode == 1


def test_gh_safe_calls_gh_when_clean(fake_gh, tmp_path: Path):
    body = tmp_path / "body.md"
    body.write_text("all clean\n", encoding="utf-8")
    res = _gh_safe(
        ["issue", "create", "--title", "Hello", "--body-file", str(body)], fake_gh, tmp_path
    )
    assert res.returncode == 0, res.stderr
    assert fake_gh[1].read_text(encoding="utf-8").split("\n")[:3] == ["issue", "create", "--title"]
