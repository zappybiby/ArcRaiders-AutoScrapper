---

name: repo-janitor
description: "Orchestrates a six-step sequential repository cleanup: separating code from docs, organizing folder structure, removing legacy code, removing script clutter, pruning documentation sprawl, and cleaning documentation content (emojis, hyperbole, 'comprehensive'). Use when asked to clean up a repository, organize a project, remove legacy code, prune AI-generated docs, clean documentation style, run janitor, or perform a full repo cleanup. Triggers on: 'clean up repo', 'janitor', 'organize repository', 'remove legacy', 'prune docs', 'doc sprawl', 'clean docs', 'remove emojis from docs', 'repo cleanup', 'tidy repo', 'remove script clutter'."

# Repo Janitor

<overview>
Six-step sequential repository cleanup. Each step must complete before the next starts - parallel execution causes file collisions. Ask the user before deleting anything uncertain.
</overview>

## Steps

<steps>
Execute in this exact order:

**1. Separate Code from Docs** - Non-deployable content (docs, planning notes, reference material) must be at a different top-level path from deployable code. Refactor if needed; confirm with user before touching deployment-affecting paths.

**2. Organize Structure** - Assess folder hierarchy. Group similar content with judicious use of subfolders. Verify no path changes break functionality before executing any move.

**3. Remove Legacy Code** - Starting from the main entry point, identify abandoned or deprecated code paths and delete them. Ask user if uncertain.

**4. Remove Script Clutter** - Delete single-purpose diagnostic/testing scripts and their wrapping elements. Consolidate where appropriate; refactor first. Ask user if uncertain.

**5. Remove Documentation Sprawl** - Delete AI-generated docs describing individual edits, time-limited info, or agent activity logs. Prefer integrating useful content into the main README over keeping separate files. Eliminate root-level sprawl first.

**6. Clean Documentation Content** - On all remaining documentation markdown files (skip prompt files and agent instruction files): remove emojis, remove "comprehensive", remove hyperbolic/promotional language, apply style conformity. Badges and graphics are fine; text must be accurate and succinct.
</steps>

## Rules

<rules>
- Sequential only - never run steps in parallel
- Ask before deleting if any doubt about safety
- Verify refactoring before any structural move
- Extra caution on deployment-affecting changes
- Report completion of each step to user
- Final summary: enumerate every change made
</rules>

## Identifying Documentation vs Prompt Files

<doc-detection>
Documentation: README.md, docs/, any public-facing .md describing features, setup, or API.
Skip (do not clean content): files in prompts/, .claude/commands/, .claude/agents/, any file whose content is instructions to an LLM agent.
</doc-detection>
