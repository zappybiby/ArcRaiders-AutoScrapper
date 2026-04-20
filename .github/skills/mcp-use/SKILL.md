---

name: mcp-use
description: Proactively discover and use MCP servers and MCP tools before native CLI tools. Use when searching, reading, editing, refactoring, planning, or researching so Copilot gets higher-signal results with less context waste

# MCP Use

Use MCP servers and MCP tools first. Prefer MCP-native search, analysis, and editing over shell-builtins or generic CLI commands whenever an MCP tool can do the job more safely or precisely.

## When to Use

- Starting any non-trivial task
- Discovering available MCP servers and tools
- Searching code, symbols, files, or external docs
- Reading or editing files with precision
- Structural refactors and code rewrites
- Multi-step planning, debugging, or investigation
- Research that benefits from GitHub or web context

## MCP-First Rule

1. Check which MCP servers and tools are available.
2. Pick the most specific MCP tool for the task.
3. Fall back to native tools only when no MCP tool fits or when the MCP tool cannot complete the task.
4. Prefer structured MCP output over raw shell output to reduce noise and mistakes.

## Tool Selection

- **Structural code search**: prefer `ast-grep/find_code` over plain text `grep`/`rg`-only searches.
- **Structural refactor**: prefer `ast-grep/rewrite_code` over manual `sed`/search-replace.
- **Static issue scan**: prefer `ast-grep/scan-code` over manual spot checks.
- **GitHub code research**: prefer `octocode/githubSearchCode` over broad web search or raw `gh search code`.
- **Read repo files**: prefer `fast-filesystem/fast_read_file` over `cat`, `sed`, or large raw reads.
- **Write new files**: prefer `fast-filesystem/fast_write_file` over shell heredocs for tracked files.
- **Precise edits**: prefer `fast-filesystem/fast_edit_block` over fragile manual replace flows.
- **Batch file ops**: prefer `fast-filesystem/fast_batch_file_operations` over repeated `cp`/`mv`/`rm` commands.
- **Complex reasoning**: prefer `sequential-thinking/sequentialthinking` over jumping straight into edits.
- **Web research**: prefer `exa/web_search_advanced_exa` over generic search first.

## Workflows

### 1) Start by checking MCP options

- Before using Bash or native editor flows, look for a matching MCP tool.
- If a task combines search + edit + reasoning, keep each step MCP-first.
- Prefer the highest-signal tool, not the most familiar one.

### 2) Search semantically or structurally

- Use `ast-grep/find_code` for AST-aware code matches.
- Use `octocode/githubSearchCode` for cross-repo or GitHub-hosted code examples.
- Use `exa/web_search_advanced_exa` for current docs, release notes, and external references.

### 3) Read and edit with filesystem MCP tools

- Use `fast-filesystem/fast_read_file` to inspect exact file ranges.
- Use `fast-filesystem/fast_edit_block` for surgical replacements in existing files.
- Use `fast-filesystem/fast_write_file` for new files or full rewrites.
- Use `fast-filesystem/fast_batch_file_operations` for coordinated copy/move/delete work.

### 4) Refactor with AST-aware tooling

- Run `ast-grep/scan-code` before or after edits to catch common issues.
- Use `ast-grep/rewrite_code` for repetitive transformations across files.
- Prefer AST rewrites over regex replacements when syntax matters.

### 5) Think before acting on multi-step tasks

- Use `sequential-thinking/sequentialthinking` for planning, tradeoffs, or debugging with uncertainty.
- Use it before large edits, workflow redesigns, or cross-file migrations.

## Examples

### Example: inspect code patterns

Instead of:

```text
rg "TODO|FIXME" .
```

Prefer:

ast-grep/find_code -> search for syntax-aware patterns in the target language
fast-filesystem/fast_read_file -> inspect only the matching file ranges

### Example: perform a safe refactor

rg "oldFunction" . && sed -i ...

ast-grep/find_code -> locate exact call sites
ast-grep/rewrite_code -> apply the structural replacement
ast-grep/scan-code -> check for follow-up issues

### Example: edit a tracked file

cat file && python script.py && mv tmp file

fast-filesystem/fast_read_file -> read the current content
fast-filesystem/fast_edit_block -> patch a precise block
fast-filesystem/fast_write_file -> write a new file when needed

### Example: research a library or pattern

generic web search + manual browsing

exa/web_search_advanced_exa -> find current docs/articles
octocode/githubSearchCode -> inspect real GitHub usage patterns
sequential-thinking/sequentialthinking -> compare options before implementation

### Example: coordinate multiple file operations

cp file1 file2 && mv file3 dir/ && rm file4

fast-filesystem/fast_batch_file_operations -> execute the full batch safely

## Decision Rule

If an MCP tool can search, read, reason, rewrite, or research more precisely than a native tool, use the MCP tool first.
