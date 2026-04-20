# Clean Debug Images

Prune stale OCR debug images from `ocr_debug/`.

**Command:**
```bash
python3 -c "
import os, time, pathlib
hours = 24
cutoff = time.time() - hours * 3600
debug_dir = pathlib.Path('ocr_debug')
if debug_dir.exists():
    for f in debug_dir.glob('*.png'):
        if f.stat().st_mtime < cutoff:
            f.unlink()
    remaining = len(list(debug_dir.glob('*.png')))
    print(f'Deleted files older than {hours}h. {remaining} remain.')
"
```

**Shortcuts:**
- `4` hours - recent session cleanup
- `0` hours - delete all debug images

**When to run:** Before committing, after scan sessions, when `ocr_debug/` appears in `git status`.
