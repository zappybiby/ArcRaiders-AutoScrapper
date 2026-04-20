# Scan TODOs

Find TODO/FIXME/HACK comments and predict next work item.

**Command:** `git grep -n -E "(TODO|FIXME|HACK|XXX)\b" -- ':!*.lock' ':!node_modules'`

**Usage:** Use to triage outstanding work and identify the best next step.

**With GitHub issues:**
```bash
gh issue list --search "TODO in:title" --state open --limit 20
```

**Tip:** Prioritizes TODOs in recently modified files and hot-path areas.
