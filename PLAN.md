---
title: Consolidated implementation plan
status: active
updated: 2026-04-20
merged_from:
  - legacy root plan
  - legacy API vision note
  - archived .kilo draft plans
---

## Purpose

This file is the single source of truth for active implementation work. It
replaces the previous draft plans and the API vision note with one ordered,
actionable roadmap.

## Workflow contract

Use this section as the operating contract for any agent that implements work
from this plan.

<workflow>
  <read-first>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/AGENTS.md</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/.github/instructions/python.instructions.md</file>
  </read-first>
  <guardrails>
    <rule>Make minimal, targeted changes.</rule>
    <rule>Do not hand-edit generated files under /home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/progress/data/ or /home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/items/items_rules.default.json.</rule>
    <rule>Regenerate bundled data with /home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/update_snapshot_and_defaults.py when data snapshots or default rules change.</rule>
    <rule>Keep OCR threshold changes aligned between OCR matching and rule lookup, and require corpus replay before shipping a new default threshold.</rule>
    <rule>Do not claim live scan validation unless a real Arc Raiders window was used.</rule>
  </guardrails>
  <task-selection>
    <rule>Pick the highest-priority ready task with no unmet dependency.</rule>
    <rule>Prefer tasks that remove user-facing bugs, security risk, or blockers before new feature work.</rule>
    <rule>Finish the current task completely before opening a parallel track in the same hotspot.</rule>
  </task-selection>
  <execution>
    <step order="1">Read the target files and confirm nearby invariants.</step>
    <step order="2">Implement only the scoped change for the selected task.</step>
    <step order="3">Run the required validation for the files you changed.</step>
    <step order="4">Update this file only if task state, ordering, or acceptance criteria changed.</step>
  </execution>
  <validation>
    <python-change>
      <command>python3 -m uv run ruff check src/ tests/ scripts/</command>
      <command>python3 -m uv run basedpyright src/</command>
      <command>python3 -m uv run pytest</command>
    </python-change>
    <workflow-change>
      <command>python3 -m uv run prek run --files .github/workflows/&lt;name&gt;.yml</command>
    </workflow-change>
    <docs-change>
      <check>Verify file paths, commands, and cross-references manually.</check>
    </docs-change>
  </validation>
  <definition-of-done>
    <item>The scoped acceptance criteria are met.</item>
    <item>Validation appropriate to the changed files has run.</item>
    <item>Unverified behavior is called out explicitly in the summary or PR text.</item>
  </definition-of-done>
</workflow>

## Delivery order

Implement work in waves so the repo stabilizes before larger feature additions.
Dependencies inside each wave are explicit.

<waves>
  <wave id="1" goal="stabilize current OCR and scanning behavior">
    <task-ref id="T010" />
    <task-ref id="T012" />
    <task-ref id="T013" />
    <task-ref id="T015" />
    <task-ref id="T017" />
    <task-ref id="T022" />
  </wave>
  <wave id="2" goal="harden data sourcing and calibration">
    <task-ref id="T014" />
    <task-ref id="T003" depends-on="T014" />
    <task-ref id="T001" />
    <task-ref id="T002" depends-on="T001" />
  </wave>
  <wave id="3" goal="finish alternate data-source features">
    <task-ref id="T016" />
    <task-ref id="T018" />
    <task-ref id="T019" />
    <task-ref id="T020" />
  </wave>
  <wave id="4" goal="evaluate optional UX research work">
    <task-ref id="T021" />
  </wave>
</waves>

## Active tasks

This section keeps only active work. Completed items, duplicate notes, and
speculative backlog entries from older drafts were removed.

<task id="T010" priority="high" size="S" status="ready">
  <title>Refresh the infobox rect on OCR retries.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/scanner/scan_loop.py</file>
  </files>
  <why>This fixes the stale crop bug that can OCR the footer instead of the active infobox.</why>
  <done-when>
    <item>Retry passes capture the window again and re-run infobox detection.</item>
    <item>The retry exits cleanly if the infobox is gone.</item>
    <item>Debug crops no longer show footer text such as TAB or CLOSE during retry.</item>
  </done-when>
</task>

<task id="T012" priority="medium" size="S" status="ready">
  <title>Add Roman numeral OCR alias correction to rule lookup.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/core/item_actions.py</file>
  </files>
  <why>This closes a common OCR-to-rule mismatch for tiered weapon names.</why>
  <done-when>
    <item>Normalization corrects common OCR suffix errors such as 1V and 111.</item>
    <item>Canonical item matching still uses the existing shared fuzzy threshold.</item>
    <item>Tests cover corrected and unchanged names.</item>
  </done-when>
</task>

<task id="T013" priority="medium" size="S" status="ready">
  <title>Filter weapon swap UI text from item-name detection.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/inventory_vision.py</file>
  </files>
  <why>This prevents overlay text from being mistaken for the actual item title.</why>
  <done-when>
    <item>Known swap-related UI strings are ignored on the first title pass.</item>
    <item>The retry path expands enough to reach the real item name below the UI line.</item>
    <item>The change does not weaken unrelated title extraction logic.</item>
  </done-when>
</task>

<task id="T014" priority="high" size="M" status="ready">
  <title>Remove the Supabase dependency from data snapshot updates.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/progress/data_update.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/update_snapshot_and_defaults.py</file>
  </files>
  <why>This removes a committed credential and keeps the updater on supported sources.</why>
  <done-when>
    <item>MetaForge item fetching uses includeComponents instead of Supabase.</item>
    <item>All Supabase constants and helpers are deleted.</item>
    <item>The snapshot updater runs without any Supabase call path.</item>
  </done-when>
</task>

<task id="T015" priority="low" size="S" status="ready">
  <title>Change the default stop key from Escape to F9.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/interaction/keybinds.py</file>
  </files>
  <why>This avoids colliding with the in-game Escape menu.</why>
  <done-when>
    <item>The default stop key is F9.</item>
    <item>The display mapping shows F9 correctly anywhere the key is rendered.</item>
  </done-when>
</task>

<task id="T016" priority="medium" size="L" status="in-progress">
  <title>Complete Direct Stash Sync through arctracker.io.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/api/__init__.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/api/client.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/api/datasource.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/api/models.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/config.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/tui/api_settings.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/tui/scan.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/scanner/engine.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/progress/progress_config.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/tests/api/test_client.py</file>
  </files>
  <why>This adds a non-OCR scan path and progress sync path while preserving OCR fallback.</why>
  <api-contract>
    <auth>Use the dual-key user flow for user endpoints.</auth>
    <endpoint>GET /api/v2/user/stash</endpoint>
    <endpoint>GET /api/v2/user/hideout</endpoint>
    <endpoint>GET /api/v2/user/projects</endpoint>
    <rate-limit>Track and respect the 500 requests per hour app limit.</rate-limit>
  </api-contract>
  <done-when>
    <item>The client handles auth, rate-limit state, retry behavior, and common failure codes.</item>
    <item>The settings UI lets users configure keys and test connectivity.</item>
    <item>API scan mode applies the same decision logic as OCR scan mode.</item>
    <item>Hideout and project progress can sync from the API.</item>
    <item>Failures fall back cleanly to OCR instead of breaking scans.</item>
    <item>Tests cover rate-limit and error paths.</item>
  </done-when>
</task>

<task id="T017" priority="low" size="S" status="ready">
  <title>Make ScanSettingsScreen a real abstract base class.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/tui/settings.py</file>
  </files>
  <why>This turns a silent design bug into an enforced contract.</why>
  <done-when>
    <item>The class inherits from ABC.</item>
    <item>Abstract methods are enforced at instantiation time.</item>
    <item>No new type-checking regressions are introduced.</item>
  </done-when>
</task>

<task id="T018" priority="medium" size="M" status="ready">
  <title>Add a headless scan mode with structured output.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/scanner/cli.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/tests/</file>
  </files>
  <why>This lets users automate scans without the Textual UI.</why>
  <done-when>
    <item>Headless mode runs without launching the TUI.</item>
    <item>JSONL output includes item, decision, page, cell, and timestamp fields.</item>
    <item>CSV output writes the same data to an explicit file path.</item>
    <item>Existing scan behavior remains unchanged when flags are absent.</item>
  </done-when>
</task>

<task id="T019" priority="medium" size="S" status="ready">
  <title>Write a per-session decision log for later rule review.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/scanner/</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/config.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/README.md</file>
  </files>
  <why>This creates a durable record of decisions without replacing the OCR failure corpus.</why>
  <done-when>
    <item>Each session can append JSONL decision records when logging is enabled.</item>
    <item>The log includes timestamp, raw text, decision, location, score, and source.</item>
    <item>The feature is opt-in and does not slow normal scans.</item>
  </done-when>
</task>

<task id="T020" priority="medium" size="M" status="ready">
  <title>Add safe recycle protection against active quest requirements.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/core/item_actions.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/progress/</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/tests/</file>
  </files>
  <why>This prevents the scanner from recycling items that active quests still need.</why>
  <done-when>
    <item>Recycle decisions are cross-checked against active quest requirements.</item>
    <item>Conflicts override the decision to KEEP and record the quest reason.</item>
    <item>The feature degrades gracefully when progress data is absent.</item>
  </done-when>
</task>

<task id="T021" priority="low" size="M" status="research">
  <title>Assess Raider Lens overlay ideas before integration.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/tui/</file>
  </files>
  <why>This is optional exploratory work and should not start until higher-value tasks land.</why>
  <done-when>
    <item>A written assessment identifies what can be reused safely.</item>
    <item>Any prototype stays isolated from OCR correctness and scan performance risk.</item>
  </done-when>
</task>

<task id="T022" priority="low" size="S" status="ready">
  <title>Make pytest available in documented install paths.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/pyproject.toml</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/README.md</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/setup-linux.sh</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/setup-windows.ps1</file>
  </files>
  <why>This removes setup drift for contributors and CI-like local environments.</why>
  <done-when>
    <item>The docs point contributors to the install path that includes pytest.</item>
    <item>Fresh setup instructions align with the dependency groups in pyproject.toml.</item>
  </done-when>
</task>

<task id="T001" priority="medium" size="M" status="ready">
  <title>Calibrate the default OCR item-name threshold from the live failure corpus.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/inventory_vision.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/failure_corpus.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/replay_ocr_failure_corpus.py</file>
  </files>
  <why>This replaces a hand-picked threshold with corpus-backed evidence.</why>
  <done-when>
    <item>Corpus samples capture the fields needed to score matching accuracy.</item>
    <item>The replay script compares candidate integer thresholds and reports accuracy.</item>
    <item>The default threshold changes only when replay shows no regression.</item>
  </done-when>
</task>

<task id="T002" priority="low" size="S" status="blocked" depends-on="T001">
  <title>Benchmark tessdata.best-eng against tessdata.fast-eng.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/tesseract.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/benchmark_tessdata_models.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/pyproject.toml</file>
  </files>
  <why>This is only worth doing after the threshold corpus is stable.</why>
  <done-when>
    <item>The benchmark uses the same corpus produced by T001.</item>
    <item>Accuracy and per-image latency are compared for both models.</item>
    <item>The repo changes models only if the latency trade-off is acceptable.</item>
  </done-when>
</task>

<task id="T003" priority="medium" size="M" status="blocked" depends-on="T014">
  <title>Enrich snapshot updates with a hybrid MetaForge plus wiki pipeline.</title>
  <files>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/progress/data_update.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/update_snapshot_and_defaults.py</file>
    <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/README.md</file>
  </files>
  <why>This extends the updater after the unsupported Supabase dependency is gone.</why>
  <done-when>
    <item>MetaForge remains primary and RaidTheory fallback remains intact.</item>
    <item>Wiki enrichment fills gaps for workshop, expedition, and project-use data.</item>
    <item>Dry-run output reports coverage without writing tracked files.</item>
    <item>Metadata records the origin of enriched fields.</item>
  </done-when>
</task>

## Suggested next picks

Start with the smallest high-value ready items, then move into blocker
removal.

<next-picks>
  <pick rank="1" task="T010">High-severity bug, small change, isolated blast radius.</pick>
  <pick rank="2" task="T014">Security and maintenance fix that unblocks downstream data work.</pick>
  <pick rank="3" task="T017">Very small correctness improvement with immediate type-safety value.</pick>
  <pick rank="4" task="T012">Small OCR normalization fix with direct user impact.</pick>
</next-picks>

## Superseded material

The older draft plans contained duplicated arctracker notes, completed items,
and broad speculative backlog entries. Those details are intentionally removed
here so this file stays implementation-focused.
