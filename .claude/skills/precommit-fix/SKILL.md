---
name: precommit-fix
description: Diagnose and fix pre-commit hook failures in this repo. Covers rumdl frontmatter, stale staged entries, and large-file check issues.
---

# Pre-commit Fix

Diagnose and fix pre-commit hook failures for this repo.

## Common Failures

### rumdl MD041 / MD065 — YAML frontmatter not recognised

**Symptom**: `MD041 First line in file should be a level 1 heading` or
`MD065 Missing blank line after horizontal rule [fixed]` on `.claude/agents/*.md`
or `.claude/skills/*/SKILL.md`.

**Cause**: rumdl treats a lone `---` as a Markdown horizontal rule, not as the
start of YAML frontmatter. It inserts a blank line after `---` (breaking the
frontmatter) and then fails MD041 because the H1 is no longer the first line.

**Fix**: Every agent/skill Markdown file must use a proper opening **and**
closing `---` delimiter:

```markdown
---
name: my-agent
description: Short description under 80 chars.
mode: subagent
---

# My Agent
```

Rules:

- Closing `---` is required — without it rumdl cannot identify the block as frontmatter.
- `description:` must be ≤ 80 characters (MD013 applies inside unrecognised frontmatter).
- First non-frontmatter line must be `# Heading` (MD041).

### check-added-large-files — stale staged entries

**Symptom**: `check-added-large-files` fails with
`No such file or directory` for a path that no longer exists in the working tree.

**Cause**: A previous stash / pop cycle left ghost entries in the index that
point to files no longer on disk.

**Fix**:

```bash
git reset HEAD -- .        # unstage everything
git add <files to commit>  # re-stage only the intended files
git commit -m "..."
```

### pre-commit passes but rumdl auto-modifies files

**Symptom**: commit fails, then the same files appear modified even though
rumdl says "Passed".

**Cause**: `rumdl-fmt` auto-fixed whitespace / blank-line issues; the hook
stashes/restores unstaged changes, leaving the auto-fixed version in the index
but the original in the working tree.

**Fix**: Re-stage the auto-fixed files and re-run the commit.

```bash
git add <auto-fixed files>
git commit -m "..."
```

## Checklist

When a commit fails pre-commit:

1. Read the hook error line — identify which hook failed and which file.
2. For **rumdl**: ensure `---...---` frontmatter with `description` < 80 chars
   and an H1 immediately after the closing `---`.
3. For **check-added-large-files**: run `git reset HEAD -- .`, re-stage only
   the intended files, and retry.
4. For **rumdl auto-fixes**: re-stage the modified files and retry.
5. Never use `--no-verify`; fix the root cause.
