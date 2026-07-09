"""test_cli_facade — the scripts.cli command table is importable, forwards
argv to its targets, and rejects unknown commands.

The command names in scripts.cli.COMMANDS are a frozen contract
(CLAUDE.md §11): vault PROCESS docs and scheduled tasks call only these.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys

import pytest

from scripts import cli
from scripts.wiki_lib.locations import vault_path, work_path

EXPECTED_COMMANDS = {
    "build",
    "mirror",
    "embed",
    "query",
    "serve",
    "fetch",
    "stage",
    "dedup",
    "cleanup",
    "vocab-sync",
    "notion-regen",
    "vault-init",
}

PROCESS_DOCS = ("PROCESS_HEALTH_CHECK.md", "PROCESS_NEW_FILE.md", "PROCESS_QUERY.md")
_RAW_PHASE_CMD = re.compile(r"python3? -m scripts\.(build|serve|ingest|maintenance)\b")


def test_command_table_is_exactly_the_frozen_contract():
    assert set(cli.COMMANDS) == EXPECTED_COMMANDS


def test_every_target_module_resolves():
    missing = {
        name: target for name, (target, _desc) in cli.COMMANDS.items() if importlib.util.find_spec(target) is None
    }
    assert not missing, f"facade targets that do not import: {missing}"


def test_bare_invocation_prints_table_and_exits_0(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for name in cli.COMMANDS:
        assert name in out, f"help table missing command {name!r}"


def test_unknown_command_exits_2_with_table(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["frobnicate"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "unknown command: frobnicate" in err
    assert "vocab-sync" in err


def test_forwarding_reaches_target_help():
    """`cli vocab-sync --help` must exit 0 with the TARGET's argparse help.

    Run in a subprocess: runpy re-executes the target under __main__, which
    would RuntimeWarning if the module is already imported in this process.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.cli", "vocab-sync", "--help"],
        capture_output=True,
        text=True,
        cwd=str(work_path()),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "usage" in proc.stdout.lower()
    assert "check_vocab_sync" in proc.stdout or "vocab" in proc.stdout.lower()


@pytest.mark.needs_vault
def test_process_docs_call_only_the_facade():
    """Vault PROCESS docs must invoke scripts.cli, never phase modules
    directly (CLAUDE.md §11). Prose paths like scripts/build/index.py are
    fine — only runnable `python -m scripts.<phase>` commands are banned."""
    vault = vault_path()
    offenders = []
    missing = []
    for doc in PROCESS_DOCS:
        path = vault / doc
        if not path.exists():
            missing.append(doc)
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _RAW_PHASE_CMD.search(line):
                offenders.append(f"{doc}:{lineno}: {line.strip()}")
    assert not offenders, (
        "PROCESS docs must call `python -m scripts.cli <command>`, not phase modules directly:\n" + "\n".join(offenders)
    )
    if missing:
        pytest.fail(f"PROCESS docs missing from vault: {missing}")
