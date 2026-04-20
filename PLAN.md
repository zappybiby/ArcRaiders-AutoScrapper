---

title: Consolidated implementation plan
status: active
updated: 2026-04-20
merged_from:
legacy root plan
legacy API vision note
archived .kilo draft plans

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
 <task-ref id="T023" />
 <task-ref id="T024" depends-on="T023" />
 <task-ref id="T025" depends-on="T023" />
 <task-ref id="T026" />
 <task-ref id="T027" />
 <task-ref id="T028" />
 </wave>
 <wave id="2" goal="harden data sourcing and calibration">
 <task-ref id="T014" />
 <task-ref id="T003" depends-on="T014" />
 <task-ref id="T001" />
 <task-ref id="T002" depends-on="T001" />
 <task-ref id="T029" />
 <task-ref id="T030" />
 <task-ref id="T031" depends-on="T001" />
 <task-ref id="T032" />
 <task-ref id="T033" />
 <wave id="3" goal="finish alternate data-source features">
 <task-ref id="T016" />
 <task-ref id="T018" />
 <task-ref id="T019" />
 <task-ref id="T020" />
 <wave id="4" goal="evaluate optional UX research work">
 <task-ref id="T021" />
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
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/core/item_actions.py</file>
 <why>This closes a common OCR-to-rule mismatch for tiered weapon names.</why>
 <item>Normalization corrects common OCR suffix errors such as 1V and 111.</item>
 <item>Canonical item matching still uses the existing shared fuzzy threshold.</item>
 <item>Tests cover corrected and unchanged names.</item>

<task id="T013" priority="medium" size="S" status="ready">
 <title>Filter weapon swap UI text from item-name detection.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/inventory_vision.py</file>
 <why>This prevents overlay text from being mistaken for the actual item title.</why>
 <item>Known swap-related UI strings are ignored on the first title pass.</item>
 <item>The retry path expands enough to reach the real item name below the UI line.</item>
 <item>The change does not weaken unrelated title extraction logic.</item>

<task id="T014" priority="high" size="M" status="ready">
 <title>Remove the Supabase dependency from data snapshot updates.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/progress/data_update.py</file>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/update_snapshot_and_defaults.py</file>
 <why>This removes a committed credential and keeps the updater on supported sources.</why>
 <item>MetaForge item fetching uses includeComponents instead of Supabase.</item>
 <item>All Supabase constants and helpers are deleted.</item>
 <item>The snapshot updater runs without any Supabase call path.</item>

<task id="T015" priority="low" size="S" status="ready">
 <title>Change the default stop key from Escape to F9.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/interaction/keybinds.py</file>
 <why>This avoids colliding with the in-game Escape menu.</why>
 <item>The default stop key is F9.</item>
 <item>The display mapping shows F9 correctly anywhere the key is rendered.</item>

<task id="T016" priority="medium" size="L" status="in-progress">
 <title>Complete Direct Stash Sync through arctracker.io.</title>
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
 <why>This adds a non-OCR scan path and progress sync path while preserving OCR fallback.</why>
 <api-contract>
 <auth>Use the dual-key user flow for user endpoints.</auth>
 <endpoint>GET /api/v2/user/stash</endpoint>
 <endpoint>GET /api/v2/user/hideout</endpoint>
 <endpoint>GET /api/v2/user/projects</endpoint>
 <rate-limit>Track and respect the 500 requests per hour app limit.</rate-limit>
 </api-contract>
 <item>The client handles auth, rate-limit state, retry behavior, and common failure codes.</item>
 <item>The settings UI lets users configure keys and test connectivity.</item>
 <item>API scan mode applies the same decision logic as OCR scan mode.</item>
 <item>Hideout and project progress can sync from the API.</item>
 <item>Failures fall back cleanly to OCR instead of breaking scans.</item>
 <item>Tests cover rate-limit and error paths.</item>

<task id="T017" priority="low" size="S" status="ready">
 <title>Make ScanSettingsScreen a real abstract base class.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/tui/settings.py</file>
 <why>This turns a silent design bug into an enforced contract.</why>
 <item>The class inherits from ABC.</item>
 <item>Abstract methods are enforced at instantiation time.</item>
 <item>No new type-checking regressions are introduced.</item>

<task id="T018" priority="medium" size="M" status="ready">
 <title>Add a headless scan mode with structured output.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/scanner/cli.py</file>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/tests/</file>
 <why>This lets users automate scans without the Textual UI.</why>
 <item>Headless mode runs without launching the TUI.</item>
 <item>JSONL output includes item, decision, page, cell, and timestamp fields.</item>
 <item>CSV output writes the same data to an explicit file path.</item>
 <item>Existing scan behavior remains unchanged when flags are absent.</item>

<task id="T019" priority="medium" size="S" status="ready">
 <title>Write a per-session decision log for later rule review.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/scanner/</file>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/README.md</file>
 <why>This creates a durable record of decisions without replacing the OCR failure corpus.</why>
 <item>Each session can append JSONL decision records when logging is enabled.</item>
 <item>The log includes timestamp, raw text, decision, location, score, and source.</item>
 <item>The feature is opt-in and does not slow normal scans.</item>

<task id="T020" priority="medium" size="M" status="ready">
 <title>Add safe recycle protection against active quest requirements.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/progress/</file>
 <why>This prevents the scanner from recycling items that active quests still need.</why>
 <item>Recycle decisions are cross-checked against active quest requirements.</item>
 <item>Conflicts override the decision to KEEP and record the quest reason.</item>
 <item>The feature degrades gracefully when progress data is absent.</item>

<task id="T021" priority="low" size="M" status="research">
 <title>Assess Raider Lens overlay ideas before integration.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/tui/</file>
 <why>This is optional exploratory work and should not start until higher-value tasks land.</why>
 <item>A written assessment identifies what can be reused safely.</item>
 <item>Any prototype stays isolated from OCR correctness and scan performance risk.</item>

<task id="T022" priority="low" size="S" status="ready">
 <title>Make pytest available in documented install paths.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/pyproject.toml</file>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/setup-linux.sh</file>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/setup-windows.ps1</file>
 <why>This removes setup drift for contributors and CI-like local environments.</why>
 <item>The docs point contributors to the install path that includes pytest.</item>
 <item>Fresh setup instructions align with the dependency groups in pyproject.toml.</item>

<task id="T001" priority="medium" size="M" status="ready">
 <title>Calibrate the default OCR item-name threshold from the live failure corpus.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/failure_corpus.py</file>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/replay_ocr_failure_corpus.py</file>
 <why>This replaces a hand-picked threshold with corpus-backed evidence.</why>
 <item>Corpus samples capture the fields needed to score matching accuracy.</item>
 <item>The replay script compares candidate integer thresholds and reports accuracy.</item>
 <item>The default threshold changes only when replay shows no regression.</item>

<task id="T002" priority="low" size="S" status="blocked" depends-on="T001">
 <title>Benchmark tessdata.best-eng against tessdata.fast-eng.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/tesseract.py</file>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/scripts/benchmark_tessdata_models.py</file>
 <why>This is only worth doing after the threshold corpus is stable.</why>
 <item>The benchmark uses the same corpus produced by T001.</item>
 <item>Accuracy and per-image latency are compared for both models.</item>
 <item>The repo changes models only if the latency trade-off is acceptable.</item>

<task id="T003" priority="medium" size="M" status="blocked" depends-on="T014">
 <title>Enrich snapshot updates with a hybrid MetaForge plus wiki pipeline.</title>
 <why>This extends the updater after the unsupported Supabase dependency is gone.</why>
 <item>MetaForge remains primary and RaidTheory fallback remains intact.</item>
 <item>Wiki enrichment fills gaps for workshop, expedition, and project-use data.</item>
 <item>Dry-run output reports coverage without writing tracked files.</item>
 <item>Metadata records the origin of enriched fields.</item>

<task id="T023" priority="high" size="S" status="ready">
 <title>Replace mean-based polarity check with population-based detection in preprocess_for_ocr.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/inventory_vision.py</file>
 <why>Live ocr_debug/ artifacts show many title_strip_fail_processed.webp samples where the centre-mean check inverts the wrong polarity (biased by bright icons or dark gradients), feeding Tesseract white-on-black text and producing garbage OCR. tessdoc/ImproveQuality requires dark text on light background.</why>
 <reference>tesseract-ocr/tessdoc ImproveQuality.md (binarisation, polarity)</reference>
 <done-when>
 <item>preprocess_for_ocr counts foreground vs background pixels after Otsu and inverts when fg &gt; bg, replacing the np.mean(centre) &lt; 128 heuristic at L884-895.</item>
 <item>Logic is symmetric across dark and light UI themes (dark context menu vs cream item card).</item>
 <item>scripts/replay_ocr_failure_corpus.py shows zero regressions and a measurable win on inversion-class failures.</item>
 <item>A fresh autoscrapper scan --dry-run against a live Arc Raiders window produces fewer title_strip_fail_*.webp dumps than the pre-change baseline.</item>
 </done-when>
</task>

<task id="T024" priority="high" size="S" status="ready" depends-on="T023">
 <title>Dual-polarity OCR with fuzzy-score arbitration for title strips.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/inventory_vision.py</file>
 <why>Belt-and-suspenders for T023. When the first OCR pass yields no fuzzy match, run Tesseract on both polarities and keep the result with the higher WRatio score. Eliminates remaining inversion failures even when pixel populations are near-tied.</why>
 <done-when>
 <item>ocr_title_strip retry path runs both binary and bitwise_not(binary) when no fuzzy match is found.</item>
 <item>The candidate with the higher match score is kept; ties favour the original polarity.</item>
 <item>Cache key includes polarity so dual-pass results are not collapsed.</item>
 <item>Corpus replay shows no regressions.</item>
 </done-when>
</task>

<task id="T025" priority="high" size="S" status="ready" depends-on="T023">
 <title>Auto-dump polarity-flip OCR failures to the failure corpus.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/inventory_vision.py</file>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/failure_corpus.py</file>
 <why>Closes the feedback loop on T023/T024 by collecting evidence whenever the polarity heuristic flips and the result still fails to match.</why>
 <done-when>
 <item>When polarity inversion fires and the OCR still fails fuzzy match, raw ROI plus both binarisations are written to artifacts/ocr/polarity_failures/.</item>
 <item>Existing ocr_debug dump path is unchanged.</item>
 <item>Disk writes are gated behind the existing debug flag.</item>
 </done-when>
</task>

<task id="T026" priority="high" size="S" status="ready">
 <title>Add tessedit_char_whitelist for item-name OCR passes.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/tesseract.py</file>
 <why>Tesseract considers the full Latin alphabet including diacritics and produces I/l/1, O/0, S/5 confusions that are currently patched up with regex. Whitelisting reduces that error surface.</why>
 <reference>tesseract-ocr/tessdoc ImproveQuality.md (dictionaries and whitelists)</reference>
 <done-when>
 <item>image_to_string and image_to_data wrappers accept a whitelist arg and call api.SetVariable("tessedit_char_whitelist", ...) before each run, clearing after.</item>
 <item>Item-name passes use uppercase, lowercase, digits, space, hyphen, apostrophe, period.</item>
 <item>Numeric and quantity ROIs keep their existing digit-only whitelist (gate per call, do not regress).</item>
 <item>Roman numeral regex still runs as a safety net.</item>
 </done-when>
</task>

<task id="T027" priority="high" size="M" status="ready">
 <title>Feed rules_store.get_item_names() to Tesseract as user_words and disable the system dawg.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/tesseract.py</file>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/items/rules_store.py</file>
 <why>Tesseract's LSTM has no domain prior; "BASTION CROSSBOW" competes with "BASKET CROSSBOW" purely on pixels. tessdoc explicitly recommends user_words for non-prose vocabulary.</why>
 <done-when>
 <item>initialize_ocr writes known item-name tokens to a temp file and loads them via SetVariable("user_words_suffix", ...).</item>
 <item>load_system_dawg is set to 0 to remove English-dictionary noise.</item>
 <item>Re-init occurs after rules_store custom-overrides change, with an integration test.</item>
 <item>Corpus replay shows no regressions.</item>
 </done-when>
</task>

<task id="T028" priority="medium" size="S" status="ready">
 <title>Pad all four sides of OCR title-strip ROIs.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/inventory_vision.py</file>
 <why>tessdoc warns that tightly-cropped text reduces accuracy. _crop_title_strip currently only adds left padding via _TITLE_LEFT_PAD.</why>
 <done-when>
 <item>Top, bottom, and right edges receive symmetric _TITLE_PAD pixels of median background colour.</item>
 <item>The retry path keeps its existing extra expansion behaviour.</item>
 <item>Corpus replay shows no regressions.</item>
 </done-when>
</task>

<task id="T029" priority="medium" size="M" status="ready">
 <title>Add Sauvola binarisation as a parallel candidate for uneven illumination.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/inventory_vision.py</file>
 <why>Otsu fails on title-band glow and rarity gradients. Sauvola is locally adaptive and fixes those without breaking the easy cases.</why>
 <done-when>
 <item>preprocess_for_ocr_sauvola is implemented either via a 30-line numpy Sauvola or via Tesseract 5's thresholding_method=2 SetVariable hook.</item>
 <item>When the Otsu pass yields no fuzzy match, Sauvola runs and the higher-WRatio result wins.</item>
 <item>No new mandatory dependency is added.</item>
 </done-when>
</task>

<task id="T030" priority="medium" size="S" status="ready">
 <title>Confidence-gated retry instead of match-only retry.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/inventory_vision.py</file>
 <why>Current retry only fires when the fuzzy match fails, missing high-fuzzy/low-confidence cases that produce subtly wrong item names.</why>
 <done-when>
 <item>Primary read switches to image_to_data and computes mean per-character confidence on title-line words.</item>
 <item>Retries fire when mean_conf is below 60 even if a fuzzy match exists.</item>
 <item>Highest-confidence result wins.</item>
 </done-when>
</task>

<task id="T031" priority="medium" size="S" status="ready" depends-on="T001">
 <title>Glyph-aware fuzzy distance for OCR-prone confusions.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/inventory_vision.py</file>
 <why>WRatio penalises O/0, I/1, l/I, 5/S equally with real edits, forcing a loose threshold that admits false matches.</why>
 <done-when>
 <item>match_item_name_result canonicalises 0 to O, 1 to I, 5 to S, 8 to B on both query and choices before scoring.</item>
 <item>Default threshold tightens by approximately 5 points without losing recall in corpus replay.</item>
 <item>OCR matching threshold and rule-lookup threshold remain shared.</item>
 </done-when>
</task>

<task id="T032" priority="low" size="XS" status="ready">
 <title>Set user_defined_dpi=300 on the Tesseract API.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/tesseract.py</file>
 <why>Numpy arrays carry no DPI header so Tesseract guesses, affecting LSTM scale priors. Combined with the existing 2x upscale, an explicit 300 DPI hint is correct.</why>
 <done-when>
 <item>initialize_ocr sets user_defined_dpi to 300.</item>
 <item>No corpus regression.</item>
 </done-when>
</task>

<task id="T033" priority="low" size="S" status="ready">
 <title>Conditional CLAHE before binarisation when contrast is low.</title>
 <file>/home/runner/work/arc-raiders-autoscrapper/arc-raiders-autoscrapper/src/autoscrapper/ocr/inventory_vision.py</file>
 <why>CLAHE on already-clean images degrades; gating on np.std(gray) &lt; 25 keeps it as a targeted contrast booster.</why>
 <done-when>
 <item>preprocess_for_ocr applies cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)) only when np.std(gray) &lt; 25.</item>
 <item>Corpus replay shows wins on low-contrast samples and no regressions elsewhere.</item>
 </done-when>
</task>

## Out of scope (OCR)

The following alternatives were evaluated and rejected. Do not adopt without
new evidence.

<out-of-scope>
 <item>EasyOCR or PaddleOCR engine swap. The Tesseract pipeline is mature; switching engines invalidates the failure corpus and threshold calibration.</item>
 <item>ONNX visual icon matching (per arcraiders-stash-scanner analysis). Heavy dependency for marginal gain over rules-store names.</item>
 <item>LSTM retraining. tessdoc explicitly discourages it unless the script or font is novel.</item>
</out-of-scope>

## Suggested next picks

Start with the smallest high-value ready items, then move into blocker
removal.

<next-picks>
 <pick rank="1" task="T023">Color-inversion fix; visible failure mode in ocr_debug/, smallest diff with biggest accuracy win.</pick>
 <pick rank="2" task="T010">High-severity bug, small change, isolated blast radius.</pick>
 <pick rank="3" task="T026">Whitelist tightening pairs cleanly with T023 in the same OCR review pass.</pick>
 <pick rank="4" task="T014">Security and maintenance fix that unblocks downstream data work.</pick>
 <pick rank="5" task="T017">Very small correctness improvement with immediate type-safety value.</pick>
 <pick rank="6" task="T012">Small OCR normalization fix with direct user impact.</pick>
</next-picks>

## Superseded material

The older draft plans contained duplicated arctracker notes, completed items,
and broad speculative backlog entries. Those details are intentionally removed
here so this file stays implementation-focused.
