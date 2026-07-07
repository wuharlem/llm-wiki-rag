"""Unit tests for wiki_lib.locations path resolution — every tier pinned.

Each test isolates a single resolution tier by clearing all four env vars and
stubbing the lower tiers (sandbox glob, Path.home). No test touches the real
filesystem/env, and none embeds the literal home path (the repo-wide invariant
scan in test_no_hardcoded_username_in_tracked_py would flag this file too).
"""

import subprocess
from pathlib import Path

import pytest
from wiki_lib import locations
from wiki_lib.locations import vault_path, work_path

_ALL_ENV = ("AI_SAFETY_VAULT", "VAULT", "AI_SAFETY_WORK", "WORK")


@pytest.fixture
def clean_env(monkeypatch):
    for name in _ALL_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _no_sandbox(monkeypatch):
    monkeypatch.setattr(locations.glob, "glob", lambda pattern: [])


# --- vault: env tier ---------------------------------------------------------


def test_vault_env_var_wins(clean_env, monkeypatch):
    clean_env.setenv("AI_SAFETY_VAULT", "/tmp/v")

    def _boom(pattern):
        raise AssertionError("sandbox glob must not be consulted when env is set")

    monkeypatch.setattr(locations.glob, "glob", _boom)
    assert vault_path() == Path("/tmp/v")


def test_vault_legacy_name_honored(clean_env, monkeypatch):
    _no_sandbox(monkeypatch)
    clean_env.setenv("VAULT", "/tmp/leg")
    assert vault_path() == Path("/tmp/leg")


def test_vault_canonical_beats_legacy(clean_env, monkeypatch):
    _no_sandbox(monkeypatch)
    clean_env.setenv("AI_SAFETY_VAULT", "/tmp/canon")
    clean_env.setenv("VAULT", "/tmp/leg")
    assert vault_path() == Path("/tmp/canon")


def test_vault_empty_env_is_unset(clean_env, monkeypatch, tmp_path):
    _no_sandbox(monkeypatch)
    clean_env.setenv("VAULT", "")  # empty string counts as unset
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert vault_path() == tmp_path / "Desktop" / "AI Safety" / "AI Safety"


# --- vault: default (home-relative) tier -------------------------------------


def test_vault_default_is_home_relative(clean_env, monkeypatch, tmp_path):
    _no_sandbox(monkeypatch)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # Home-relative: the result is built entirely from the (stubbed) home dir,
    # so no user identifier is hardcoded in the resolver.
    assert vault_path() == tmp_path / "Desktop" / "AI Safety" / "AI Safety"


# --- vault: sandbox-mount tier -----------------------------------------------


def test_vault_sandbox_mount_discovered(clean_env, monkeypatch, tmp_path):
    mount = tmp_path / "mnt"
    mount.mkdir()
    monkeypatch.setattr(locations.glob, "glob", lambda pattern: [str(mount)])
    assert vault_path() == mount


def test_vault_stale_sandbox_path_skipped(clean_env, monkeypatch, tmp_path):
    stale = tmp_path / "a_stale"  # sorts first; never created
    good = tmp_path / "b_good"
    good.mkdir()
    monkeypatch.setattr(locations.glob, "glob", lambda pattern: [str(good), str(stale)])

    real_is_dir = Path.is_dir

    def fake_is_dir(self):
        if self == stale:
            raise PermissionError("stale session mount")
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", fake_is_dir)
    assert vault_path() == good  # stale skipped without raising


# --- work path ---------------------------------------------------------------


def test_work_env_var_wins(clean_env):
    clean_env.setenv("WORK", "/tmp/w")
    assert work_path() == Path("/tmp/w")


def test_work_canonical_beats_legacy(clean_env):
    clean_env.setenv("AI_SAFETY_WORK", "/tmp/cw")
    clean_env.setenv("WORK", "/tmp/w")
    assert work_path() == Path("/tmp/cw")


def test_work_default_is_repo_root(clean_env):
    root = Path(locations.__file__).resolve().parents[2]
    assert work_path() == root
    assert (work_path() / "pyproject.toml").exists()


# --- purity ------------------------------------------------------------------


def test_resolver_is_side_effect_free(clean_env, monkeypatch, tmp_path):
    import os

    _no_sandbox(monkeypatch)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    before = dict(os.environ)
    vault_path()
    work_path()
    assert dict(os.environ) == before  # env untouched
    assert not (tmp_path / "Desktop").exists()  # no dirs created


# --- repo-wide invariant -----------------------------------------------------


def test_no_hardcoded_username_in_tracked_py():
    """No tracked .py file may hardcode the personal home path. End-state gate:
    passes only after every call site has migrated to the resolver."""
    # Built from fragments so this test file does not match its own scan.
    needle = "/Users/" + "harlem"
    repo = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("git not available or not a repository")
    tracked = [line for line in result.stdout.splitlines() if line]
    if not tracked:
        pytest.skip("no tracked .py files found")
    offenders = []
    for rel in tracked:
        try:
            text = (repo / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if needle in text:
            offenders.append(rel)
    assert not offenders, f"hardcoded home path found in: {offenders}"
