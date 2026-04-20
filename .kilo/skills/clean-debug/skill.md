---
name: clean-debug
description: Prune stale ocr_debug/ images older than N hours (default 24). Prevents the folder from accumulating hundreds of PNGs between sessions.
disable-model-invocation: true

Delete OCR debug images older than the specified age:

```bash
---

# Default: delete files older than 24 hours
python3 -c "
import os, time, pathlib, sys

hours = float(sys.argv[1]) if len(sys.argv) > 1 else 24
cutoff = time.time() - hours * 3600
debug_dir = pathlib.Path('ocr_debug')

if not debug_dir.exists():
 print('ocr_debug/ does not exist, nothing to clean.')
 raise SystemExit(0)

deleted = []
for f in debug_dir.glob('*.png'):
 if f.stat().st_mtime < cutoff:
 f.unlink()
 deleted.append(f.name)

remaining = len(list(debug_dir.glob('*.png')))
print(f'Deleted {len(deleted)} files older than {hours}h. {remaining} files remain.')
" "${1:-}"
```

**Usage:**

- `/clean-debug 4` - delete files older than 4h
- `/clean-debug 0` - delete all debug images

**When to run:**

- Before committing (keeps repo clean)
- After a scan session produces many debug images
- When `ocr_debug/` appears in `git status`
