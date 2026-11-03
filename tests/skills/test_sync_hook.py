"""Behavior tests for .githooks/lib/sync-skills.sh.

The hook mirrors skills/ into the live agent runtimes. It must only publish the
default branch: a checkout, rebase or commit on a feature branch (often in a
linked worktree) must never push unreviewed skill instructions to the runtimes.
Each test builds a throwaway git repo with the real hook and a fake
scripts/sync_skills.sh that only records that it ran.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".githooks" / "lib" / "sync-skills.sh"
BASH = shutil.which("bash") or "/bin/bash"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    marker = tmp_path / "synced"
    (repo / "skills" / "demo").mkdir(parents=True)
    (repo / "skills" / "demo" / "SKILL.md").write_text("demo\n")
    (repo / "scripts").mkdir()
    sync = repo / "scripts" / "sync_skills.sh"
    sync.write_text(f"#!/usr/bin/env bash\necho ran >> '{marker}'\n")
    sync.chmod(0o755)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return repo, marker


def _run_hook(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run([BASH, str(HOOK)], cwd=repo, capture_output=True, text=True, check=False)


def test_hook_syncs_on_main(tmp_path):
    repo, marker = _repo(tmp_path)
    result = _run_hook(repo)
    assert result.returncode == 0
    assert marker.read_text() == "ran\n"
    assert "skills synced" in result.stdout


def test_hook_skips_feature_branch(tmp_path):
    repo, marker = _repo(tmp_path)
    _git(repo, "switch", "-q", "-c", "feat/wip")
    (repo / "skills" / "demo" / "SKILL.md").write_text("unreviewed\n")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "wip")
    result = _run_hook(repo)
    assert result.returncode == 0
    assert not marker.exists()
    assert result.stdout == ""
    assert not (repo / ".git" / "skills-sync.stamp").exists()


def test_hook_skips_detached_head(tmp_path):
    repo, marker = _repo(tmp_path)
    _git(repo, "switch", "-q", "--detach")
    result = _run_hook(repo)
    assert result.returncode == 0
    assert not marker.exists()
