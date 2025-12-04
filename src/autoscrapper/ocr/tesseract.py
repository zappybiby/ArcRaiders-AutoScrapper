from __future__ import annotations

import os
import threading
from pathlib import Path
import sys
from typing import Dict, List

import numpy as np
from PIL import Image
import tessdata
from tesserocr import PSM, PyTessBaseAPI, RIL, iterate_level

_api_lock = threading.Lock()
_api: PyTessBaseAPI | None = None
_tessdata_dir: str | None = None
_logged_init = False


def _has_eng(path: Path) -> bool:
    return path.is_dir() and (path / "eng.traineddata").exists()


def _candidate_tessdata_paths() -> list[Path]:
    """
    Potential tessdata locations to try, ordered by preference.
    """
    candidates: list[Path] = []

    env_prefix = os.getenv("TESSDATA_PREFIX")
    if env_prefix:
        candidates.append(Path(env_prefix))

    try:
        candidates.append(Path(tessdata.data_path()))
    except Exception:
        pass

    # Site-packages layout: <...>/site-packages/tessdata/share/tessdata
    pkg_dir = Path(tessdata.__file__).resolve().parent
    candidates.append(pkg_dir.parent / "share" / "tessdata")

    appdata = os.getenv("APPDATA")
    if appdata:
        appdata_path = Path(appdata)
        candidates.append(appdata_path / "Python" / "share" / "tessdata")
        py_ver = f"Python{sys.version_info.major}{sys.version_info.minor}"
        candidates.append(appdata_path / "Python" / py_ver / "share" / "tessdata")

    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def _create_api() -> PyTessBaseAPI:
    """
    Build a shared PyTessBaseAPI instance configured for English, single block.
    """
    global _tessdata_dir
    errors: list[tuple[Path, Exception]] = []
    candidates = _candidate_tessdata_paths()

    for candidate in candidates:
        if not _has_eng(candidate):
            continue
        try:
            os.environ["TESSDATA_PREFIX"] = str(candidate)
            api = PyTessBaseAPI(path=str(candidate), lang="eng", psm=PSM.SINGLE_BLOCK)
            _tessdata_dir = str(candidate)
            return api
        except Exception as exc:
            errors.append((candidate, exc))
            continue

    searched = "\n  ".join(str(c) for c in candidates)
    detail_errors = "\n  ".join(f"{p}: {e}" for p, e in errors)
    raise RuntimeError(
        "Could not initialize Tesseract API with any tessdata location. "
        "Checked (eng.traineddata required):\n  "
        + searched
        + ("\nErrors:\n  " + detail_errors if detail_errors else "")
    )


def _log_init(api: PyTessBaseAPI) -> None:
    global _logged_init
    if _logged_init:
        return

    version = api.Version() if hasattr(api, "Version") else ""
    langs = api.GetAvailableLanguages() or []
    langs_desc = ",".join(sorted(langs))
    print(f"[ocr_backend] tesseract={version.strip()} tessdata={_tessdata_dir} langs={langs_desc}", flush=True)
    _logged_init = True


def _get_api() -> PyTessBaseAPI:
    """
    Lazily initialize and return the shared Tesseract API instance.
    """
    global _api
    if _api is None:
        _api = _create_api()
        _log_init(_api)
    return _api


def initialize_ocr() -> None:
    """
    Force initialization so startup logging happens before the first OCR call.
    """
    _get_api()


def _as_pil_image(image: np.ndarray) -> Image.Image:
    if image.ndim == 2:
        return Image.fromarray(image)
    if image.ndim == 3 and image.shape[2] == 3:
        # OpenCV images are BGR; convert to RGB
        return Image.fromarray(image[:, :, ::-1])
    if image.ndim == 3 and image.shape[2] == 4:
        return Image.fromarray(image[:, :, [2, 1, 0, 3]])
    raise ValueError(f"Unsupported image shape for OCR: {image.shape}")


def _empty_data_dict() -> Dict[str, List]:
    return {
        "level": [],
        "page_num": [],
        "block_num": [],
        "par_num": [],
        "line_num": [],
        "word_num": [],
        "left": [],
        "top": [],
        "width": [],
        "height": [],
        "conf": [],
        "text": [],
    }


def _build_data_dict(iterator) -> Dict[str, List]:
    data = _empty_data_dict()
    block_num = 0
    par_num = 0
    line_num = 0
    word_num = 0

    for word in iterate_level(iterator, RIL.WORD):
        if word.IsAtBeginningOf(RIL.BLOCK):
            block_num += 1
            par_num = 0
            line_num = 0
        if word.IsAtBeginningOf(RIL.PARA):
            par_num += 1
            line_num = 0
        if word.IsAtBeginningOf(RIL.TEXTLINE):
            line_num += 1
            word_num = 0

        word_num += 1

        bbox = word.BoundingBox(RIL.WORD)
        if bbox is None:
            continue

        x1, y1, x2, y2 = bbox
        width = max(0, x2 - x1)
        height = max(0, y2 - y1)
        conf_val = word.Confidence(RIL.WORD)
        text = word.GetUTF8Text(RIL.WORD) or ""

        data["level"].append(int(RIL.WORD))
        data["page_num"].append(1)
        data["block_num"].append(block_num or 1)
        data["par_num"].append(par_num or 1)
        data["line_num"].append(line_num or 1)
        data["word_num"].append(word_num)
        data["left"].append(int(x1))
        data["top"].append(int(y1))
        data["width"].append(int(width))
        data["height"].append(int(height))
        data["conf"].append(f"{conf_val:.2f}" if conf_val is not None else "-1")
        data["text"].append(text)

    return data


def image_to_string(image: np.ndarray) -> str:
    """
    OCR the provided image and return raw UTF-8 text.
    """
    api = _get_api()
    pil_img = _as_pil_image(np.ascontiguousarray(image))

    with _api_lock:
        api.SetImage(pil_img)
        text = api.GetUTF8Text() or ""

    return text


def image_to_data(image: np.ndarray) -> Dict[str, List]:
    """
    OCR the provided image and return a dict shaped like pytesseract Output.DICT.
    """
    api = _get_api()
    pil_img = _as_pil_image(np.ascontiguousarray(image))

    with _api_lock:
        api.SetImage(pil_img)
        api.Recognize()
        iterator = api.GetIterator()
        if iterator is None:
            return _empty_data_dict()
        return _build_data_dict(iterator)
