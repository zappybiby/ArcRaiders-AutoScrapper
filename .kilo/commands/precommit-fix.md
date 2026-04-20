# Fix Pre-commit Issues

Diagnose and fix pre-commit hook failures.

**Common issues:**

**rumdl MD041/MD065 - YAML frontmatter:**
- Ensure files have both opening AND closing `---` delimiters
- Keep `description:` under 80 characters
- First non-frontmatter line must be `# Heading`

**check-added-large-files - stale entries:**
```bash
git reset HEAD -- .
git add <files to commit>
git commit -m "..."
```

**rumdl auto-fixes:**
```bash
git add <auto-fixed files>
git commit -m "..."
```

**Never use `--no-verify`** - always fix the root cause.
