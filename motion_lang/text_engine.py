# motion_lang/text_engine.py
"""Dynamic typography for Motion Language: local + Google Fonts loading.

``load_font("Poppins", weight="bold")`` resolves to a ``.ttf`` file path
usable anywhere a ``font=`` is accepted (``text("Hi", font=...)``):

1. explicit ``url=`` (direct ``.ttf``/``.otf`` link, or a Google Fonts
   ``css2`` stylesheet URL — the ``.ttf`` is extracted automatically),
2. fonts already installed on the system (``/usr/share/fonts``,
   ``~/.fonts``, ``~/.local/share/fonts``, ``fc-match``),
3. Google Fonts fetched on demand and cached under
   ``~/.cache/motion_lang/fonts/`` (Fontsource CDN TTFs, with the legacy
   Google CSS API as fallback).

Everything degrades gracefully: on any failure (notably offline machines)
``load_font`` returns ``None`` and the engine falls back to its default font.
"""

from __future__ import annotations

import os
import re
import shutil
from functools import lru_cache
from typing import Dict, List, Optional

try:
    import requests as _requests
except Exception:  # pragma: no cover - offline / minimal installs
    _requests = None  # type: ignore

_FONT_DIRS = (
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    ".",
)

_WEIGHTS: Dict[str, int] = {
    "thin": 100, "extralight": 200, "ultralight": 200, "light": 300,
    "regular": 400, "normal": 400, "book": 400, "medium": 500,
    "semibold": 600, "demibold": 600, "bold": 700, "extrabold": 800,
    "ultrabold": 800, "black": 900, "heavy": 900,
}

_STYLE_SUFFIXES = ("", "-Regular", "-Bold", "-Italic", "-BoldItalic")

_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "motion_lang", "fonts")

_UA_TTF = {"User-Agent": "curl/8.0"}  # legacy Google CSS API -> truetype URLs
_TIMEOUT = 12


def weight_value(weight: str | int) -> int:
    """Normalise ``"bold"`` / ``700`` to a numeric font weight."""
    if isinstance(weight, int):
        return weight
    try:
        return int(weight)
    except (TypeError, ValueError):
        return _WEIGHTS.get(str(weight or "").strip().lower(), 400)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


@lru_cache(maxsize=256)
def find_local_font(name: str, weight: int = 400) -> Optional[str]:
    """Search installed fonts for ``name`` (weight-aware when possible)."""
    if os.path.isfile(name):
        return name
    target = _norm(name)
    cands: List[str] = []
    for d in _FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fname in files:
                if not fname.lower().endswith((".ttf", ".otf", ".ttc")):
                    continue
                stem = _norm(os.path.splitext(fname)[0])
                if target and target in stem:
                    cands.append(os.path.join(root, fname))
    if not cands:
        if shutil.which("fc-match"):
            try:
                import subprocess
                out = subprocess.check_output(
                    ["fc-match", "-f", "%{file}\n%{family}", name],
                    stderr=subprocess.DEVNULL).decode().strip().splitlines()
                if len(out) >= 2 and os.path.isfile(out[0]):
                    fams = {_norm(f) for f in out[1].split(",")}
                    # Accept fontconfig substitution only when the family
                    # really matches (else prefer a Google Fonts fetch).
                    if any(target in fam or fam in target for fam in fams):
                        return out[0]
            except Exception:
                pass
        return None
    want_bold = weight >= 600
    want_italic = "italic" in target or "oblique" in target
    def score(path: str) -> int:
        stem = _norm(os.path.splitext(os.path.basename(path))[0])
        s = 0
        if ("bold" in stem) == want_bold:
            s += 2
        if ("italic" in stem or "oblique" in stem) == want_italic:
            s += 1
        if stem == target or stem == target + "regular":
            s += 1
        return s
    cands.sort(key=score, reverse=True)
    return cands[0]


def _cache_path(family: str, weight: int, style: str = "normal") -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", family.replace(" ", ""))
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"{safe}-{weight}-{style}.ttf")


def _download(url: str, dest: str) -> bool:
    if _requests is None:
        return False
    try:
        with _requests.get(url, timeout=_TIMEOUT, stream=True) as resp:
            if resp.status_code != 200:
                return False
            tmp = dest + ".part"
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(65536):
                    fh.write(chunk)
            os.replace(tmp, dest)
            return os.path.getsize(dest) > 1024
    except Exception:
        return False


def _fontsource_urls(family: str, weight: int, style: str) -> List[str]:
    fid = re.sub(r"\s+", "", family.strip().lower())
    subset = "latin"
    return [(
        f"https://cdn.jsdelivr.net/fontsource/fonts/{fid}@latest/"
        f"{subset}-{weight}-{style}.ttf"
    )]


def _google_css_ttf(family: str, weight: int, style: str) -> List[str]:
    if _requests is None:
        return []
    fam = family.strip().replace(" ", "+")
    axis = "ital,wght" if style == "italic" else "wght"
    spec = f"1,{weight}" if style == "italic" else str(weight)
    url = f"https://fonts.googleapis.com/css?family={fam}:{axis}@{spec}"
    try:
        resp = _requests.get(url, headers=_UA_TTF, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return []
        return re.findall(r"url\((https://[^)]+?\.ttf)\)", resp.text)
    except Exception:
        return []


def fetch_google_font(family: str, weight: int = 400,
                      style: str = "normal") -> Optional[str]:
    """Download a Google Font TTF into the cache; ``None`` on any failure."""
    dest = _cache_path(family, weight, style)
    if os.path.isfile(dest) and os.path.getsize(dest) > 1024:
        return dest
    urls = _fontsource_urls(family, weight, style)
    urls += _google_css_ttf(family, weight, style)
    for url in urls:
        if _download(url, dest):
            return dest
    if os.path.isfile(dest):
        try:
            os.remove(dest)
        except OSError:
            pass
    return None


def _extract_ttf_from_css(css_text: str) -> List[str]:
    return re.findall(r"url\((https://[^)]+?\.ttf)\)", css_text)


def load_font(name: str, weight: str | int = "regular",
              url: Optional[str] = None,
              style: str = "normal") -> Optional[str]:
    """Resolve ``name`` to a ``.ttf`` path (local, URL, or Google Fonts).

    Args:
        name: Family name (``"Poppins"``), local path, or direct font URL.
        weight: ``"regular"`` / ``"bold"`` / ``700`` / ...
        url: Direct ``.ttf``/``.otf`` link or a Google Fonts ``css2`` URL.
        style: ``"normal"`` or ``"italic"``.

    Returns:
        Filesystem path to the font, or ``None`` when unavailable (callers
        fall back to the default font).
    """
    w = weight_value(weight)
    st = "italic" if str(style).lower().startswith("italic") else "normal"
    if url:
        if url.lower().endswith((".ttf", ".otf")):
            dest = _cache_path(name or "custom", w, st)
            if os.path.isfile(dest):
                return dest
            return dest if _download(url, dest) else None
        # Assume a Google Fonts stylesheet URL: extract the TTF for w/st.
        if _requests is not None:
            try:
                resp = _requests.get(url, headers=_UA_TTF, timeout=_TIMEOUT)
                ttf = _extract_ttf_from_css(resp.text if resp.status_code == 200 else "")
                dest = _cache_path(name or "custom", w, st)
                for link in ttf:
                    if _download(link, dest):
                        return dest
            except Exception:
                pass
        return None
    if not name:
        return None
    if name.lower().endswith((".ttf", ".otf", ".ttc")) or os.path.isfile(name):
        return name if os.path.isfile(name) else None
    local = find_local_font(name, w)
    if local:
        return local
    got = fetch_google_font(name, w, st)
    if got:
        print(f"[Fonts] Cached '{name}' ({w}) -> {got}")
    else:
        print(f"[DSL Warning] Font '{name}' not found locally and "
              f"could not be fetched (offline?). Using default font.")
    return got
