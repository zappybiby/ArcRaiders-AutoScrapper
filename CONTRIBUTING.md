# Contributing

## Prerequisites

1. `mise` is a required tool, use [their installation guide](https://mise.jdx.dev/installing-mise.html) to set it up

## Project Setup

```bash
mise install
mise x uv -- uv sync
```

## Using UV

### With a Virtual Environment

```bash
source .venv/bin/activate
python -m autoscrapper
```

### Using UV directly

```bash
mise x uv -- uv run -m autoscrapper
```
