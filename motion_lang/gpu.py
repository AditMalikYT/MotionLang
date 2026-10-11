# motion_lang/gpu.py
"""NVIDIA GPU (NVENC) support for Motion Language rendering.

Compositing itself runs on the CPU (Pillow/numpy/MoviePy), but the final
``ffmpeg`` encode -- usually 30-60% of ``--render`` wall time at 1080p+ --
can be offloaded to NVIDIA NVENC when available:

    motion file.hmg --render --gpu

Detected stack on this machine (example)::

    GPU: NVIDIA GeForce RTX 2050 (4GB, driver 550.x)
    ffmpeg encoders: h264_nvenc, hevc_nvenc, av1_nvenc
    hwaccels: cuda, vdpau, vaapi, ...

If ``--gpu`` is requested but NVENC is unavailable (no NVIDIA GPU, ffmpeg
built without ``--enable-nvenc``), rendering falls back to ``libx264`` with
a warning instead of failing.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Dict, List, Optional


CODEC_ALIASES = {
    "h264": "h264_nvenc",
    "h264_nvenc": "h264_nvenc",
    "libx264": "h264_nvenc",
    "hevc": "hevc_nvenc",
    "h265": "hevc_nvenc",
    "hevc_nvenc": "hevc_nvenc",
    "av1": "av1_nvenc",
    "av1_nvenc": "av1_nvenc",
}

CPU_FALLBACK = {
    "h264_nvenc": "libx264",
    "hevc_nvenc": "libx265",
    "av1_nvenc": "libaom-av1",
}


def _run(cmd: List[str], timeout: int = 10) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (out.stdout or "") + (out.stderr or "")
    except Exception:
        return ""


def has_nvidia_gpu() -> bool:
    """True when ``nvidia-smi`` reports at least one GPU."""
    if shutil.which("nvidia-smi") is None:
        return False
    out = _run(["nvidia-smi", "--query-gpu=name",
                "--format=csv,noheader"])
    return bool(out.strip())


def gpu_names() -> List[str]:
    if shutil.which("nvidia-smi") is None:
        return []
    out = _run(["nvidia-smi", "--query-gpu=name",
                "--format=csv,noheader"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def ffmpeg_encoders() -> str:
    if shutil.which("ffmpeg") is None:
        return ""
    return _run(["ffmpeg", "-hide_banner", "-encoders"])


def has_nvenc(codec: str = "h264_nvenc") -> bool:
    """True when this ffmpeg build ships the given NVENC encoder."""
    return codec in ffmpeg_encoders()


def available_nvenc_encoders() -> List[str]:
    found = []
    table = ffmpeg_encoders()
    for enc in ("h264_nvenc", "hevc_nvenc", "av1_nvenc"):
        if enc in table:
            found.append(enc)
    return found


def get_gpu_info() -> Dict:
    """Probe GPU + ffmpeg and return a JSON-serialisable status dict."""
    names = gpu_names()
    encoders = available_nvenc_encoders()
    smi = ""
    if shutil.which("nvidia-smi"):
        smi = _run(["nvidia-smi",
                    "--query-gpu=name,driver_version,memory.total",
                    "--format=csv"]).strip()
    return {
        "nvidia_gpu": bool(names),
        "gpus": names,
        "nvidia_smi": smi,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "nvenc_encoders": encoders,
        "gpu_ready": bool(names) and bool(encoders),
    }


def print_gpu_info() -> Dict:
    info = get_gpu_info()
    print("[GPU] NVIDIA GPUs:", ", ".join(info["gpus"]) or "none found")
    if info["nvidia_smi"]:
        print(info["nvidia_smi"])
    print("[GPU] ffmpeg:", "found" if info["ffmpeg"] else "NOT found")
    print("[GPU] NVENC encoders:",
          ", ".join(info["nvenc_encoders"]) or "none (ffmpeg without --enable-nvenc?)")
    if info["gpu_ready"]:
        print("[GPU] Ready: use `motion file.hmg --render --gpu`")
    else:
        print("[GPU] Not ready: --gpu will fall back to libx264 with a warning.")
    return info


def resolve_encoder(requested: Optional[str] = None) -> str:
    """Normalise ``--gpu-codec h264|hevc|av1`` to an ffmpeg encoder name."""
    if not requested:
        return "h264_nvenc"
    key = str(requested).strip().lower()
    return CODEC_ALIASES.get(key, "h264_nvenc")


def nvenc_extra_params(bitrate: Optional[str] = None,
                       cq: Optional[int] = None) -> List[str]:
    """Quality params appended *after* moviepy's own flags.

    NOTE: ``-preset`` is passed via ``write_videofile(preset=...)`` and the
    output ``-pix_fmt yuv420p`` is enforced by the Popen interceptor
    (:func:`patched_ffmpeg_popen`), because MoviePy 2.x unconditionally
    appends ``-preset medium`` (invalid for NVENC, which wants ``p1..p7``)
    and ``-pix_fmt yuva420p`` (rejected by NVENC) around ``ffmpeg_params``.
    """
    if bitrate:
        params = ["-b:v", str(bitrate)]
    else:
        params = ["-rc", "vbr", "-cq", str(19 if cq is None else int(cq))]
    # NVENC has no RGB input: force yuv420p. (For h264_nvenc MoviePy also
    # appends its own pix_fmt flag, which the Popen interceptor normalises
    # to yuv420p; a duplicate identical flag is harmless. For hevc/av1
    # MoviePy adds none, so this is the only thing keeping ffmpeg from
    # negotiating gbrp/yuva444, which NVENC rejects.)
    return params + ["-pix_fmt", "yuv420p"]


def normalise_preset(preset: str = "p4") -> str:
    """Validate an NVENC preset (``p1`` fastest .. ``p7`` best quality)."""
    preset = (preset or "p4").strip().lower()
    if preset not in {f"p{i}" for i in range(1, 8)}:
        print(f"[GPU] Unknown preset '{preset}', using 'p4'.")
        preset = "p4"
    return preset


def system_ffmpeg() -> Optional[str]:
    """Path to the system ffmpeg (which ships NVENC), or None."""
    return shutil.which("ffmpeg")


def patched_ffmpeg_popen():
    """Context manager rewriting MoviePy's ffmpeg calls for NVENC.

    Two MoviePy 2.x behaviours break NVENC encodes and are fixed here on
    the command line, without touching site-packages:

    1. MoviePy shells out to its bundled imageio-ffmpeg binary, which is
       built *without* NVENC. Any command selecting an ``*_nvenc`` encoder
       is re-pointed at the system ``ffmpeg``.
    2. MoviePy appends ``-pix_fmt yuva420p`` (alpha) after ``ffmpeg_params``
       for even-sized clips. NVENC rejects alpha pixel formats, so it is
       rewritten to ``yuv420p`` (correct for opaque MP4 output anyway).

    Non-NVENC commands (audio temp files, version probes) pass through
    untouched.
    """
    from contextlib import contextmanager
    from unittest import mock
    import subprocess as _sp

    sys_ff = system_ffmpeg()
    real_popen = _sp.Popen

    def _spy(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and any(
                enc in cmd for enc in
                ("h264_nvenc", "hevc_nvenc", "av1_nvenc")):
            cmd = list(cmd)
            if sys_ff:
                cmd[0] = sys_ff
            cmd = ["yuv420p" if c == "yuva420p" else c for c in cmd]
            return real_popen(cmd, *args, **kwargs)
        return real_popen(cmd, *args, **kwargs)

    @contextmanager
    def _ctx():
        with mock.patch.object(_sp, "Popen", _spy):
            yield

    return _ctx()


def select_render_codec(use_gpu: bool,
                        gpu_codec: Optional[str] = None,
                        gpu_preset: str = "p4",
                        gpu_bitrate: Optional[str] = None,
                        gpu_cq: Optional[int] = None) -> Dict:
    """Pick the ``write_videofile`` settings for a render.

    Returns ``{"codec", "preset", "ffmpeg_params", "gpu", "fallback",
    "message"}``. Never raises: on any problem it returns the libx264
    CPU fallback.
    """
    if not use_gpu:
        return {"codec": "libx264", "preset": "medium",
                "ffmpeg_params": None, "gpu": False,
                "fallback": False, "message": "cpu libx264"}
    encoder = resolve_encoder(gpu_codec)
    if not has_nvidia_gpu():
        return {"codec": CPU_FALLBACK.get(encoder, "libx264"),
                "preset": "medium", "ffmpeg_params": None,
                "gpu": False, "fallback": True,
                "message": "no NVIDIA GPU found (nvidia-smi empty); "
                           "falling back to CPU encode"}
    if system_ffmpeg() is None:
        return {"codec": "libx264", "preset": "medium",
                "ffmpeg_params": None, "gpu": False, "fallback": True,
                "message": "system ffmpeg not found; "
                           "falling back to CPU encode"}
    if not has_nvenc(encoder):
        avail = available_nvenc_encoders()
        if avail:
            encoder = avail[0]
            print(f"[GPU] Requested encoder unavailable, using {encoder}.")
        else:
            return {"codec": "libx264", "preset": "medium",
                    "ffmpeg_params": None,
                    "gpu": False, "fallback": True,
                    "message": "ffmpeg has no NVENC encoders; "
                               "falling back to CPU encode"}
    preset = normalise_preset(gpu_preset)
    params = nvenc_extra_params(bitrate=gpu_bitrate, cq=gpu_cq)
    return {"codec": encoder, "preset": preset, "ffmpeg_params": params,
            "gpu": True, "fallback": False,
            "message": f"NVENC {encoder} -preset {preset} {' '.join(params)}"}
