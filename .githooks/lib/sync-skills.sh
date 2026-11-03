#!/usr/bin/env bash
# Shared implementation for the post-merge / post-checkout / post-rewrite hooks.
#
# Purpose: after the repository changes, push the skills to the agent runtimes
# so a pull is enough to update them. The repo stays the source of truth; the
# runtime directories are mirrors.
#
# This runs on every checkout and every pull, so it must be cheap when nothing
# changed. It fingerprints the tracked contents of skills/ and exits immediately
# when that fingerprint matches the last successful sync.
#
# Git ignores the exit code of post-* hooks, so this can never block a pull.
# It still exits 0 explicitly, and reports failures loudly rather than silently.

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[[ -n "$REPO_ROOT" ]] || exit 0

SYNC="$REPO_ROOT/scripts/sync_skills.sh"
[[ -x "$SYNC" ]] || exit 0

# Only the default branch is published. A feature branch or detached HEAD
# (usually a linked worktree) holds unreviewed skill text that must not reach
# the live runtimes on a checkout, rebase or commit.
BRANCH="$(git symbolic-ref --short -q HEAD 2>/dev/null)" || exit 0
[[ "$BRANCH" == "main" ]] || exit 0

GIT_DIR="$(git rev-parse --git-dir)"
STAMP="$GIT_DIR/skills-sync.stamp"

# Fingerprint the tracked skill sources. `ls-files -s` prints mode, blob hash
# and path, so this changes exactly when skill content changes — not when a
# timestamp moves. The sync script itself is included: changing how the mirror
# is written should also trigger a re-sync.
fingerprint() {
  git -C "$REPO_ROOT" ls-files -s -- skills/ scripts/sync_skills.sh 2>/dev/null \
    | sha256sum | cut -d' ' -f1
}

CURRENT="$(fingerprint)"
[[ -n "$CURRENT" ]] || exit 0

if [[ -f "$STAMP" ]] && [[ "$(cat "$STAMP" 2>/dev/null)" == "$CURRENT" ]]; then
  exit 0
fi

echo "==> skills changed — syncing to the agent runtimes"

if "$SYNC" --apply; then
  printf '%s\n' "$CURRENT" > "$STAMP"
  echo "==> skills synced"
else
  # Do not write the stamp: leaving it stale means the next pull retries.
  echo "!! skill sync FAILED — runtimes may be stale." >&2
  echo "!! run manually: $SYNC --apply" >&2
fi

exit 0
