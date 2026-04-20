---
name: todo-scan
description: Use when user wants to Scan the repo for TODO code comments, TODO-titled GitHub issues, and predict the next best work item to tackle. Reusable across any git repository.
---

# TODO Scan + Next-Step Predictor

You are performing a structured triage of outstanding work for the current repository. Execute all three phases, then synthesize a recommendation.

## Phase 1 — Code TODOs

Find all TODO/FIXME/HACK/XXX annotations in tracked source files:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Search source files, exclude common noise dirs
git grep -n --no-color -E "(TODO|FIXME|HACK|XXX)\b" \
  -- ':!*.lock' ':!node_modules' ':!.git' ':!dist' ':!build' ':!__pycache__' ':!*.min.js' \
  2>/dev/null | head -80
```

Group results by file. For each TODO, note:
- File path + line number
- The full comment text
- The surrounding function/class if determinable from context

## Phase 2 — GitHub Issues with TODO in Title

Check if the `gh` CLI is available and the repo has a GitHub remote:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Detect GitHub remote
GH_REMOTE=$(git remote -v 2>/dev/null | grep -oP '(?<=github\.com[/:])[^/]+/[^\s.]+' | head -1)

if command -v gh >/dev/null 2>&1 && [ -n "$GH_REMOTE" ]; then
  echo "=== Open issues with TODO in title ==="
  gh issue list --search "TODO in:title" --state open --limit 20 \
    --json number,title,labels,assignees,createdAt \
    --jq '.[] | "#\(.number) [\(.labels | map(.name) | join(", "))] \(.title)"' 2>/dev/null || \
    gh issue list --search "TODO in:title" --state open --limit 20 2>/dev/null

  echo ""
  echo "=== Open issues with FIXME in title ==="
  gh issue list --search "FIXME in:title" --state open --limit 10 \
    --json number,title --jq '.[] | "#\(.number) \(.title)"' 2>/dev/null
else
  echo "gh CLI not available or no GitHub remote detected. Skipping issue search."
  echo "Remote detected: ${GH_REMOTE:-none}"
fi
```

## Phase 3 — Predict Next Work Item

Gather signals about recent activity and open work:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

echo "=== Recent commits (last 10) ==="
git log --oneline -10 2>/dev/null

echo ""
echo "=== Uncommitted changes ==="
git status --short 2>/dev/null

echo ""
echo "=== Most-changed files (last 30 days) ==="
git log --since="30 days ago" --name-only --format="" 2>/dev/null | \
  grep -v '^$' | sort | uniq -c | sort -rn | head -15

echo ""
echo "=== Open PRs (if gh available) ==="
command -v gh >/dev/null 2>&1 && \
  gh pr list --state open --limit 10 \
    --json number,title,isDraft \
    --jq '.[] | "#\(.number)\(if .isDraft then " [DRAFT]" else "" end) \(.title)"' 2>/dev/null || \
  echo "gh not available"

echo ""
echo "=== Failed CI on recent commits (if gh available) ==="
command -v gh >/dev/null 2>&1 && \
  gh run list --limit 5 --json conclusion,name,headBranch \
    --jq '.[] | select(.conclusion == "failure") | "\(.name) on \(.headBranch)"' 2>/dev/null || \
  echo "gh not available"
```

## Synthesis

After collecting all three phases of data, reason through the following and produce a structured report:

### 1. TODO Inventory
List all code TODOs grouped by severity:
- **Critical** (FIXME, HACK with production impact)
- **Normal** (TODO with clear scope)
- **Minor** (XXX, style/cleanup notes)

### 2. Issue Backlog
List any GitHub issues found, noting if they overlap with code TODOs.

### 3. Next-Step Prediction

Apply this heuristic to pick the single best next item:

| Signal | Weight |
|--------|--------|
| TODO is in a file modified in the last 7 days | High — already in context |
| TODO is in a hot-path file (high commit frequency) | High — high-impact area |
| TODO corresponds to an open GitHub issue | High — tracked and expected |
| FIXME or HACK tag | High — indicates known debt |
| PR is open touching the same file | Medium — coordinate, don't duplicate |
| TODO is in test files only | Low — not blocking |

Output format:

```
## TODO Scan Report — <repo name> — <date>

### Code TODOs (<N> found)
- [CRITICAL] src/foo/bar.py:42 — FIXME: null check missing before deref
- [NORMAL]   src/baz/qux.py:17 — TODO: add retry logic for API timeout
...

### GitHub Issues (<N> found)
- #123 [bug] TODO: fix login race condition
...

### Recommended Next Step
**<file>:<line> — <todo text>**
Reason: <1-2 sentence explanation using signals above>

Alternatives:
1. <second candidate>
2. <third candidate>
```

## Notes

- Works on any git repository — no project-specific config needed
- If `gh` is unavailable, Phases 2 and CI checks are skipped gracefully
- Adjust `head -80` limit in Phase 1 for very large repos
- Run with `/todo-scan` or ask Claude to "scan todos and predict next step"
