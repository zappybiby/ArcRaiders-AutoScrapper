---

name: gh-cli
description: Routes GitHub tasks to the right `gh` or `git` command family. Use when working with repositories, issues, pull requests, Actions, releases, or GitHub search from the terminal.

# GitHub CLI (gh)

Use this skill as a routing aid, not a full manual. Pick the smallest command family that matches the task, inspect flags with `--help` when needed, and prefer read-only commands before mutation.

## Usage

Use `gh` for GitHub-hosted state and `git` for local branch/history work.

## When to use

- Inspect or edit a repository: `gh repo ...`
- Work with issues: `gh issue ...`
- Work with pull requests: `gh pr ...`
- Investigate CI or trigger workflows: `gh run ...` / `gh workflow ...`
- Manage releases: `gh release ...`
- Search GitHub: `gh search ...`
- Fall back to raw APIs: `gh api ...`
- Local branch/history work: `git ...`

## Workflow

1. Start with `list`, `view`, `status`, or `diff` to confirm the target.
2. Use the narrowest mutating command that matches the request.
3. Prefer structured output (`--json`, `--jq`) for automation or summarization.
4. Respect environment-specific guardrails around auth, push, and protected branches.

## Common paths

- Inspect a PR: `gh pr view <number> --comments --json title,body,files`
- Check CI for a PR/branch: `gh run list` -> `gh run view <run-id> --log`
- Create or update an issue: `gh issue create ...` / `gh issue edit ...`
- Search across GitHub: `gh search code ...` / `gh search prs ...`
- Inspect local changes: `git status` -> `git diff` -> `git log --oneline`

## Guardrails

- Avoid broad or destructive mutations until the target has been confirmed.
- Use `gh api` only when higher-level commands do not expose the needed operation.
- Prefer repo-local automation or MCP tools when the environment offers safer equivalents.

## Examples

### Inspect a pull request

```bash
gh pr view 123 --comments --json title,body,files
```

### Trigger and watch a workflow

gh workflow run ci.yml --ref main
gh run list --workflow ci.yml --limit 1 --json databaseId \
 --jq '.[0].databaseId' | xargs gh run watch

### Search for matching pull requests

gh search prs "is:open review:required label:bugfix"

## References

- Manual: <https://cli.github.com/manual/>, REST API: <https://docs.github.com/en/rest>, GraphQL API: <https://docs.github.com/en/graphql>
