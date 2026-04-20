---
name: upstream-sync
description: Use when user wants to Sync fork from upstream (zappybiby/ArcRaiders-AutoScrapper) before pushing. Run this before any push or PR creation to avoid merge conflicts.
disable-model-invocation: true
---

# Upstream Sync

Syncs your fork from `upstream` (`https://github.com/zappybiby/ArcRaiders-AutoScrapper`) before pushing.

## Steps

### 1. Check upstream remote

```bash
git remote -v | grep upstream
```

If missing, add it:

git remote add upstream <https://github.com/zappybiby/ArcRaiders-AutoScrapper.git>

### 2. Fetch and sync

git fetch upstream
git pull --autostash upstream main

`--autostash` stashes any uncommitted local changes, applies the upstream merge, then re-applies the stash automatically.

### 3. Resolve conflicts if any

If there are merge conflicts:

git status

## Edit conflicted files, then

git add <resolved-files>
git merge --continue

### 4. Push

git push origin main

### Notes

- Run this before every push: upstream may have data updates from the daily CI job
- `progress/data/` and `items_rules.default.json` are auto-generated - if upstream updated them, accept upstream's version and regenerate locally with `/data-snapshot-updater` only if you have newer local data
- If the autostash re-apply fails, run `git stash pop` manually after resolving conflicts
