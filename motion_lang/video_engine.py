# motion_lang/video_engine.py
"""Video cutting, trimming and retiming for Motion Language.

Thin, version-agnostic wrappers over MoviePy so ``.hmg`` scripts can slice,
splice and retime imported footage without touching clip internals:

* :func:`cut_clip` — ``clip.cut(start, end)`` / ``subclip`` / ``trim``
* :func:`retime_clip` — ``clip.speed(factor)`` (slow-motion ``< 1``,
  time-lapse ``> 1``)
* :func:`split_clip` — ``split_video(source, intervals=[(0, 3), (5, 8)])``

All operations are lazy (MoviePy subclips share frames; speed retiming maps
timestamps), so trimming never duplicates decoded frames and the asset cache
keeps working: identical ``(path, ops)`` specs resolve to one cached entry.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

try:  # moviepy >= 2.0 (with_* API, effect objects)
    from moviepy.video.fx.MultiplySpeed import MultiplySpeed as _MultiplySpeed
    _MPV2 = True
except ImportError:  # moviepy 1.x (.fx() API)
    from moviepy.video.fx.speedx import speedx as _speedx1
    _MPV2 = False


def clip_duration(clip) -> Optional[float]:
    """Best-effort clip duration in seconds (None when unbounded)."""
    try:
        d = clip.duration
        return float(d) if d is not None else None
    except Exception:
        return None


def cut_clip(clip, start: Optional[float] = None,
             end: Optional[float] = None):
    """Restrict ``clip`` to the ``[start, end)`` source window (seconds).

    ``None`` keeps the corresponding bound. Out-of-range bounds are clamped
    to the clip duration instead of raising.
    """
    s = 0.0 if start is None else max(0.0, float(start))
    dur = clip_duration(clip)
    if end is None:
        e = dur
    else:
        e = max(s, float(end))
        if dur is not None:
            e = min(e, dur)
    if e is None or e <= s:
        return clip
    if _MPV2:
        return clip.subclipped(s, e)
    return clip.subclip(s, e)


def retime_clip(clip, factor: float):
    """Change playback speed by ``factor`` (>1 faster, <1 slow-motion).

    ``factor`` must be positive; values are clamped to ``[0.05, 16]`` to keep
    frame timestamps sane.
    """
    f = max(0.05, min(16.0, float(factor)))
    if abs(f - 1.0) < 1e-9:
        return clip
    if _MPV2:
        return clip.with_effects([_MultiplySpeed(f)])
    return clip.fx(_speedx1, f)


def split_clip(clip, intervals: Sequence[Tuple[float, float]]):
    """Split ``clip`` into subclips for each ``(start, end)`` interval."""
    return [cut_clip(clip, s, e) for s, e in intervals]


def apply_ops(clip, source_start=None, source_end=None, speed=None):
    """Apply an accumulated ``(cut, speed)`` op-set; returns ``(clip, used)``.

    ``used`` reports the normalised ``(start, end, speed)`` triple for cache
    keys and diagnostics. Cutting happens before retiming.
    """
    ops = {"start": source_start, "end": source_end, "speed": speed}
    if source_start is not None or source_end is not None:
        clip = cut_clip(clip, source_start, source_end)
    if speed is not None:
        clip = retime_clip(clip, speed)
    dur = clip_duration(clip)
    if source_start is None and source_end is None and dur is not None:
        ops["start"], ops["end"] = 0.0, dur
    return clip, ops


def normalise_interval(value) -> Tuple[Optional[float], Optional[float]]:
    """Coerce ``[s, e]`` / ``(s, e)`` / ``{"start": s, ...}`` to a pair."""
    if isinstance(value, dict):
        return (value.get("start"), value.get("end", value.get("stop")))
    try:
        s, e = value[0], value[1]
        return (None if s is None else float(s), None if e is None else float(e))
    except Exception:
        raise ValueError(f"Bad interval {value!r}: expected [start, end].")


def cache_key(path: str, source_start=None, source_end=None,
              speed=None) -> str:
    """Stable cache key so identical trims share one entry."""
    return f"video::{path}::{source_start}:{source_end}:{speed}"


# Backwards-compatible alias used by older snippets.
trim_clip = cut_clip
