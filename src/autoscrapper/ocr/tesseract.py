from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
import tessdata
from tesserocr import PSM, PyTessBaseAPI, RIL, iterate_level

_api_lock = threading.Lock()
_api_line_lock = threading.Lock()
_api_single_word_lock = threading.Lock()
_api_sparse_lock = threading.Lock()
_api_init_lock = threading.Lock()
_api: PyTessBaseAPI | None = None
_api_line: PyTessBaseAPI | None = None
_api_single_word: PyTessBaseAPI | None = None
_api_sparse: PyTessBaseAPI | None = None
_tessdata_dir: str | None = None
_backend_info: OcrBackendInfo | None = None


@dataclass(frozen=True, slots=True)
class OcrBackendInfo:
    tesseract_version: str
    tessdata_dir: str | None
    languages: list[str]


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


def _create_api(*, psm: PSM = PSM.SINGLE_BLOCK) -> PyTessBaseAPI:
    """
    Build a shared PyTessBaseAPI instance configured for English.
    """
    global _tessdata_dir
    errors: list[tuple[Path, Exception]] = []
    candidates = _candidate_tessdata_paths()

    for candidate in candidates:
        if not _has_eng(candidate):
            continue
        try:
            os.environ["TESSDATA_PREFIX"] = str(candidate)
            api = PyTessBaseAPI(path=str(candidate), lang="eng", psm=psm)
            api.SetVariable(
                "tessedit_char_whitelist",
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 '-/(),.!?:&+",
            )
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


def _record_backend_info(api: PyTessBaseAPI) -> None:
    global _backend_info
    if _backend_info is not None:
        return

    version = api.Version() if hasattr(api, "Version") else ""
    langs = api.GetAvailableLanguages() or []
    _backend_info = OcrBackendInfo(
        tesseract_version=version.strip(),
        tessdata_dir=_tessdata_dir,
        languages=sorted(langs),
    )


def _get_api() -> PyTessBaseAPI:
    """
    Lazily initialize and return the shared Tesseract API instance.
    """
    global _api
    if _api is not None:
        return _api

    with _api_init_lock:
        if _api is None:
            _api = _create_api()
            _record_backend_info(_api)
    return _api


def _get_api_line() -> PyTessBaseAPI:
    """
    Lazily initialize and return the shared single-line Tesseract API instance (PSM.SINGLE_LINE).
    """
    global _api_line
    if _api_line is not None:
        return _api_line

    with _api_init_lock:
        if _api_line is None:
            _api_line = _create_api(psm=PSM.SINGLE_LINE)
            _record_backend_info(_api_line)
    return _api_line


def _get_api_single_word() -> PyTessBaseAPI:
    """
    Lazily initialize and return the shared single-word Tesseract API instance (PSM.SINGLE_WORD).

    Used as a PSM fallback on OCR retry attempts for the title strip when
    SINGLE_LINE produces no match.
    """
    global _api_single_word
    if _api_single_word is not None:
        return _api_single_word

    with _api_init_lock:
        if _api_single_word is None:
            _api_single_word = _create_api(psm=PSM.SINGLE_WORD)
            _record_backend_info(_api_single_word)
    return _api_single_word


def _get_api_sparse() -> PyTessBaseAPI:
    """
    Lazily initialize and return the shared sparse-text Tesseract API instance (PSM.SPARSE_TEXT).

    Used as a PSM fallback on OCR retry attempts for context-menu crops when
    SINGLE_BLOCK produces no match.
    """
    global _api_sparse
    if _api_sparse is not None:
        return _api_sparse

    with _api_init_lock:
        if _api_sparse is None:
            _api_sparse = _create_api(psm=PSM.SPARSE_TEXT)
            _record_backend_info(_api_sparse)
    return _api_sparse


def initialize_ocr() -> OcrBackendInfo:
    """
    Force initialization so the OCR backend is ready before the first OCR call.
    """
    api = _get_api()
    _get_api_line()
    _get_api_single_word()
    _get_api_sparse()
    _record_backend_info(api)
    if _backend_info is None:  # pragma: no cover - defensive
        raise RuntimeError("OCR backend initialized but metadata is missing.")
    return _backend_info


def get_ocr_backend_info() -> OcrBackendInfo | None:
    """
    Return metadata about the configured OCR backend, if initialized.
    """
    return _backend_info


def _as_pil_image(image: np.ndarray) -> Image.Image:
    if image.ndim == 2:
        return Image.fromarray(image)
    if image.ndim == 3 and image.shape[2] == 3:
        # OpenCV images are BGR; convert to RGB
        return Image.fromarray(image[:, :, ::-1])
    if image.ndim == 3 and image.shape[2] == 4:
        return Image.fromarray(image[:, :, [2, 1, 0, 3]])
    raise ValueError(f"Unsupported image shape for OCR: {image.shape}")


def _empty_data_dict() -> dict[str, list]:
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


def _build_data_dict(iterator) -> dict[str, list]:
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
            word_num = 0
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


DEFAULT_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 '-/(),.!?:&+"


def image_to_string(
    image: np.ndarray,
    *,
    single_line: bool = False,
    use_single_word: bool = False,
    whitelist: str | None = None,
) -> str:
    """
    OCR the provided image and return raw UTF-8 text.

    - ``use_single_word=True`` → PSM.SINGLE_WORD (fallback on retry for title strips).
    - ``single_line=True``     → PSM.SINGLE_LINE (default title-strip mode).
    - Neither set              → PSM.SINGLE_BLOCK.
    - ``whitelist``            → Restrict OCR to these characters (T026).
    """
    if use_single_word:
        api = _get_api_single_word()
        lock = _api_single_word_lock
    elif single_line:
        api = _get_api_line()
        lock = _api_line_lock
    else:
        api = _get_api()
        lock = _api_lock
    pil_img = _as_pil_image(np.ascontiguousarray(image))

    with lock:
        if whitelist:
            api.SetVariable("tessedit_char_whitelist", whitelist)
        api.SetImage(pil_img)
        text = api.GetUTF8Text() or ""
        if whitelist:
            api.SetVariable("tessedit_char_whitelist", DEFAULT_WHITELIST)

    return text


def image_to_data(
    image: np.ndarray,
    *,
    single_line: bool = False,
    use_sparse: bool = False,
    whitelist: str | None = None,
) -> dict[str, list]:
    """
    OCR the provided image and return a dict shaped like pytesseract Output.DICT.

    - ``use_sparse=True``  → PSM.SPARSE_TEXT (fallback on retry for context-menu crops).
    - ``single_line=True`` → PSM.SINGLE_LINE.
    - Neither set          → PSM.SINGLE_BLOCK.
    - ``whitelist``        → Restrict OCR to these characters (T026).
    """
    if use_sparse:
        api = _get_api_sparse()
        lock = _api_sparse_lock
    elif single_line:
        api = _get_api_line()
        lock = _api_line_lock
    else:
        api = _get_api()
        lock = _api_lock
    pil_img = _as_pil_image(np.ascontiguousarray(image))

    with lock:
        if whitelist:
            api.SetVariable("tessedit_char_whitelist", whitelist)
        api.SetImage(pil_img)
        api.Recognize()
        iterator = api.GetIterator()
        if whitelist:
            api.SetVariable("tessedit_char_whitelist", DEFAULT_WHITELIST)

        if iterator is None:
            return _empty_data_dict()
        return _build_data_dict(iterator)
