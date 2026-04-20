# Changelog

All notable changes to ArcRaiders-AutoScrapper are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.9.0] – 2026-04-02

### Changed

- Daily Metaforge snapshot and default rules regenerated (automated bot PR #21)

### CI

- Fixed CI to ignore timestamp-only diffs in daily data updates
- Removed create-pull-request action dependency from daily updater workflow

## [0.8.0] – 2026-03-04

### Added

- Automated daily data updater - GitHub Actions workflow that snapshots Metaforge item/quest data and opens a PR when changes are detected
- TUI: allow manual snapshot update once per app session

Removed frozen sync requirement in daily updater
Disabled setup-uv cache (lockfile untracked)
Fixed YAML quoting in daily data update workflow

## [0.7.0] – 2026-02-17

Progress-based rules engine (PR #19) - item actions now adapt based on quest completion and workshop level
Graph-based quest inference for accurate active-quest detection
Quest status cycling in the review list
Rule changes summary displayed after progress setup
Startup warmup flow with thread-safe OCR initialisation
Adaptive infobox detector with dominant-edge bounding box
Configurable stop key and advanced scan timing settings
Alternating scroll setting; removed manual page controls

Calibrated scroll cycle replacing manual scroll settings
Redesigned rules editor with search-first workflow
Refined rules filter shortcuts, save status display, and layout
Normalised TUI back-key behaviour (removed b-as-back)
Scan CLI now routes through Textual (--dry-run flag supported)
Split scan settings into per-category screens
Highlighted recommended menu option in orange
Stopped per-keystroke autosave in rules screen
Aligned quest setup and review interaction patterns
Window detection moved to UI thread

### Fixed

Quest inference fallback for non-linear active quest sets
Quest reward semantics and keep logic
Rules editor scrolling, reasons display, and layout
ScanScreen timer attribute collision
MSS capture across scan threads
TUI keybindings; removed `ctrl+enter` reliance

### Refactored

Progress TUI split into package modules
Scanner engine split into focused helper stages
Legacy text-menu CLI removed; consolidated rule/warning helpers for Textual
Legacy stop key helpers and legacy rules artefacts removed
Entrypoint: TUI is now the default surface; scan is the only standalone CLI command

## [0.6.0] – 2026-01-30

Textual TUI shell - full interactive UI replacing the plain CLI menu
Textual scan screen with live progress
Progress wizard with quest review and workshop picker
Advanced rules viewer with search and hotkeys
Rich home menu with one-time default-rules warning
Arrow-key and unified menu navigation
Cross-platform key reader and list UI helpers
Config support for progress flags and UI options

Ported all CLI flows to the Textual UI
Streamlined CLI home menu
Unified menu navigation across screens
Clarified "personalized rules" menu label
Refactored inventory scanner into focused modules

- Rules viewer navigation when filtered list is empty
- rich.Group import

## [0.5.0] – 2026-01-22

Rich scanning UI (PR #16) - live item-by-item output with colour and progress indicators
Default/custom item rules support
Progress-based rules engine integration (initial wiring)
Confirmations added to setup scripts (PR #15)
Dev extra for Black formatter

False "borderless fullscreen" warning
Invalid PEP 508 dependency strings
UV install directory set to prevent shell-refresh requirement after setup

### Docs

- Simplified dependency information in README
- Updated Linux notes

## [0.4.0] – 2025-12-31

4×5 inventory grid support replacing previous layout (PR #14)
Experimental Linux support with uv integration (PR #13)
Black formatting GitHub Actions workflow and pre-commit config (PR #10, #11)
Contributing guidelines and repository contributor guide

- Updated grid ROI for 4×5 layout
- Added dev extra for Black

## [0.3.0] – 2025-12-16

Scan configuration menu with adjustable timing and behaviour options (PR #6)
OCR retry functionality; scanner stops after two consecutive empty cells (PR #8)
Post-action delay after sell/recycle actions
Increased last-row menu delay multiplier

- Refactored project structure and CLI menu (PR #3)
- Clarified what causes `<unreadable>` item titles in output

## [0.2.0] – 2025-12-02

Auto stash-page detection - scanner detects and advances pages automatically (PR #2)
Scan overview summary after each run
Interactive rules CLI for configuring item actions
Item rules documented in README

Switched screen capture from dxcam → MSS for broader compatibility
Updated item action decisions and last-row click position
Increased last-row menu delay

- Showed raw OCR text when item title is unreadable

## [0.1.0] – 2025-11-26

Initial release of ArcRaiders-AutoScrapper
OCR-based inventory scanner using Tesseract / tesserocr
Contour-based grid detection scaled to active window size
Carousel-friendly scrolling with empty-slot detection to stop after blank rows
Tolerance-based infobox detection with single OCR pass
Tesseract auto-detection helper
Dry-run mode
dxcam screen capture with monitor display logging
OCR debug hooks and raw-text fallback for unreadable cells
Basic README with setup and usage instructions

[Unreleased]: https://github.com/zappybiby/ArcRaiders-AutoScrapper/compare/HEAD...HEAD
[0.9.0]: https://github.com/zappybiby/ArcRaiders-AutoScrapper/commits/main
[0.8.0]: https://github.com/zappybiby/ArcRaiders-AutoScrapper/compare/1a2d903...cc22f46
[0.7.0]: https://github.com/zappybiby/ArcRaiders-AutoScrapper/compare/a47c087...8a445ff
[0.6.0]: https://github.com/zappybiby/ArcRaiders-AutoScrapper/compare/a47c087...25bd0da
[0.5.0]: https://github.com/zappybiby/ArcRaiders-AutoScrapper/compare/7db7bc7...ab7ba16
[0.4.0]: https://github.com/zappybiby/ArcRaiders-AutoScrapper/compare/cb7b036...bf28b9e
[0.3.0]: https://github.com/zappybiby/ArcRaiders-AutoScrapper/compare/e00320c...2bacaaa
[0.2.0]: https://github.com/zappybiby/ArcRaiders-AutoScrapper/compare/c75e3d8...e00320c
[0.1.0]: https://github.com/zappybiby/ArcRaiders-AutoScrapper/commit/c75e3d8
