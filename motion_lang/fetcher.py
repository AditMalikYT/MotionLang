# motion_lang/fetcher.py
"""Asset fetching with disk caching + concurrent downloads."""

from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw

_DEFAULT_CACHE_DIR = Path(os.environ.get("MOTION_CACHE_DIR", ".cache"))
_CACHE_LOCK = threading.Lock()


def get_cache_dir() -> Path:
    d = Path(os.environ.get("MOTION_CACHE_DIR", str(_DEFAULT_CACHE_DIR)))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hash_key(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _cache_path(name: str) -> Path:
    return get_cache_dir() / name


def clear_cache(cache_dir=None) -> int:
    """Wipe stored asset cutouts. Returns number of files removed."""
    target = Path(cache_dir) if cache_dir else get_cache_dir()
    if not target.exists():
        print(f"[Cache] Nothing to clean (missing {target}).")
        return 0
    count = 0
    for p in target.glob("*"):
        try:
            if p.is_file():
                p.unlink()
                count += 1
        except OSError as exc:
            print(f"[Cache] Could not remove {p}: {exc}")
    print(f"[Cache] Cleaned {count} file(s) from {target}.")
    return count


def cache_stats(cache_dir=None) -> Dict:
    target = Path(cache_dir) if cache_dir else get_cache_dir()
    if not target.exists():
        return {"dir": str(target), "files": 0, "bytes": 0}
    files = [p for p in target.glob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    return {"dir": str(target), "files": len(files), "bytes": total}


def _remove_background(image_bytes: bytes) -> bytes:
    from rembg import remove
    return remove(image_bytes)


def fetch_wikimedia_image(query: str, use_cache: bool = True):
    """Queries Wikimedia Commons API (URL mapping cached on disk)."""
    cache_key = _hash_key(f"wiki-url::{query.lower().strip()}")
    cache_file = _cache_path(f"wiki_url_{cache_key}.json")
    if use_cache and cache_file.exists():
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            if time.time() - float(payload.get("ts", 0)) < 7 * 86400:
                print(f"[Cache] Wikimedia URL hit for '{query}'.")
                return payload.get("url")
        except Exception:
            pass
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrlimit": 5,
        "prop": "imageinfo",
        "iiprop": "url|mime",
    }
    headers = {"User-Agent": "MotionLangCompiler/1.0 (contact@example.com)"}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        data = res.json()
        pages = data.get("query", {}).get("pages", {})
        for _pid, page in pages.items():
            image_info = page.get("imageinfo", [])
            if image_info:
                img_url = image_info[0].get("url")
                mime = image_info[0].get("mime", "")
                if img_url and any(ext in mime for ext in ["png", "jpeg", "jpg", "webp"]):
                    if use_cache:
                        try:
                            with _CACHE_LOCK:
                                cache_file.write_text(json.dumps({"url": img_url, "ts": time.time()}), encoding="utf-8")
                        except OSError:
                            pass
                    return img_url
    except Exception as e:
        print(f"[Debug] Wikimedia API Error for '{query}': {e}")
    return None


def create_fallback_image(text: str, width: int = 500, height: int = 500) -> Image.Image:
    """Fallback generator when image search fails."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([50, 50, width - 50, height - 50], fill=(220, 50, 50, 200), outline=(255, 255, 255, 255), width=4)
    draw.text((width // 4, height // 2 - 10), f"[{text}]", fill=(255, 255, 255, 255))
    return img


def get_web_transparent_image(query: str, use_cache: bool = True) -> Image.Image:
    """Downloads image from Wikimedia and removes background (cached)."""
    cache_key = _hash_key(f"web-cutout::{query.lower().strip()}")
    cache_file = _cache_path(f"web_{cache_key}.png")
    if use_cache and cache_file.exists():
        try:
            print(f"[Cache] Hit for web query '{query}'.")
            return Image.open(cache_file).convert("RGBA")
        except Exception as exc:
            print(f"[Cache] Corrupt entry {cache_file}: {exc}; refetching.")
    print(f"[Fetcher] Searching Wikimedia for: '{query}'")
    img_url = fetch_wikimedia_image(query, use_cache=use_cache)
    if img_url:
        print(f"[Fetcher] Found URL: {img_url}")
        try:
            headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
            res = requests.get(img_url, headers=headers, timeout=12)
            if res.status_code == 200:
                print("[Fetcher] Removing background with rembg...")
                nobg_bytes = _remove_background(res.content)
                img = Image.open(io.BytesIO(nobg_bytes)).convert("RGBA")
                if use_cache:
                    try:
                        with _CACHE_LOCK:
                            img.save(cache_file, format="PNG")
                        print(f"[Cache] Stored web cutout -> {cache_file}")
                    except Exception as exc:
                        print(f"[Cache] Could not store {cache_file}: {exc}")
                return img
            print(f"[Debug] HTTP {res.status_code} downloading image.")
        except Exception as e:
            print(f"[Debug] Image download/rembg error: {e}")
    print(f"[Fallback] Search or background removal failed for '{query}'. Using placeholder.")
    return create_fallback_image(query)


def get_local_transparent_image(file_path: str, remove_bg: bool = True, use_cache: bool = True) -> Image.Image:
    """Loads a local image file and strips background using rembg (cached)."""
    if not os.path.exists(file_path):
        print(f"[Error] Local file not found: '{file_path}'. Using fallback.")
        return create_fallback_image(os.path.basename(file_path))
    if not remove_bg:
        return Image.open(file_path).convert("RGBA")
    try:
        with open(file_path, "rb") as fh:
            raw = fh.read()
        digest = _hash_bytes(raw)
    except OSError as exc:
        print(f"[Error] Could not read '{file_path}': {exc}.")
        return create_fallback_image(os.path.basename(file_path))
    cache_file = _cache_path(f"local_{digest}.png")
    if use_cache and cache_file.exists():
        try:
            print(f"[Cache] Hit for local file '{file_path}'.")
            return Image.open(cache_file).convert("RGBA")
        except Exception as exc:
            print(f"[Cache] Corrupt entry {cache_file}: {exc}; reprocessing.")
    print(f"[Fetcher] Loading local file: '{file_path}'")
    try:
        img = Image.open(io.BytesIO(raw))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        nobg_bytes = _remove_background(buf.getvalue())
        out = Image.open(io.BytesIO(nobg_bytes)).convert("RGBA")
        if use_cache:
            try:
                with _CACHE_LOCK:
                    out.save(cache_file, format="PNG")
                print(f"[Cache] Stored local cutout -> {cache_file}")
            except Exception as exc:
                print(f"[Cache] Could not store {cache_file}: {exc}")
        return out
    except Exception as exc:
        print(f"[Debug] Local rembg error for '{file_path}': {exc}. Using original.")
        return Image.open(io.BytesIO(raw)).convert("RGBA")


def get_web_transparent_images(queries, use_cache: bool = True, max_workers: int = 4) -> Dict:
    """Fetch multiple web cutouts concurrently. Returns query -> PIL image."""
    unique = list(dict.fromkeys(queries))
    if not unique:
        return {}
    print(f"[Fetcher] Concurrent fetch of {len(unique)} web asset(s) (workers={max_workers})...")
    results: Dict = {}
    def _one(q):
        try:
            return q, get_web_transparent_image(q, use_cache=use_cache)
        except Exception as exc:
            print(f"[Fetcher] Concurrent fetch failed for '{q}': {exc}")
            return q, create_fallback_image(q)
    workers = min(max_workers, len(unique))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for q, img in pool.map(_one, unique):
            results[q] = img
    return results


def prefetch_web_images(queries, use_cache: bool = True, max_workers: int = 4) -> Dict:
    """Alias used by parser to warm cache before compiling."""
    return get_web_transparent_images(queries, use_cache=use_cache, max_workers=max_workers)


def get_local_transparent_images(paths, remove_bg: bool = True, use_cache: bool = True, max_workers: int = 4) -> Dict:
    """Concurrently process multiple local images."""
    unique = list(dict.fromkeys(paths))
    if not unique:
        return {}
    results: Dict = {}
    def _one(p):
        try:
            return p, get_local_transparent_image(p, remove_bg=remove_bg, use_cache=use_cache)
        except Exception as exc:
            print(f"[Fetcher] Local fetch failed for '{p}': {exc}")
            return p, create_fallback_image(os.path.basename(p))
    workers = min(max_workers, len(unique))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for p, img in pool.map(_one, unique):
            results[p] = img
    return results
