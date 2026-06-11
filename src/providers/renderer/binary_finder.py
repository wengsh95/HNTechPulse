import shutil
import sys
from pathlib import Path
from typing import Optional


def find_node() -> Optional[str]:
    node = shutil.which("node")
    if not node:
        for p in [
            r"C:\Program Files\nodejs\node.exe",
            str(Path(sys.prefix) / "nodejs" / "node.exe"),
            str(Path.home() / "AppData" / "Local" / "Programs" / "nodejs" / "node.exe"),
        ]:
            if Path(p).exists():
                return p
        return None
    return node


def find_npm(node_path: Optional[str] = None) -> Optional[str]:
    npm = shutil.which("npm")
    if not npm and node_path:
        node_dir = Path(node_path).parent
        candidate = node_dir / "npm.cmd"
        if candidate.exists():
            return str(candidate)
        candidate = node_dir / "npm"
        if candidate.exists():
            return str(candidate)
    return npm or None


def find_npx(node_path: Optional[str] = None) -> Optional[str]:
    npx = shutil.which("npx")
    if not npx and node_path:
        node_dir = Path(node_path).parent
        candidate = node_dir / "npx.cmd"
        if candidate.exists():
            return str(candidate)
        candidate = node_dir / "npx"
        if candidate.exists():
            return str(candidate)
    return npx or None


def find_chrome() -> Optional[str]:
    chrome = shutil.which("chrome") or shutil.which("chromium")
    if chrome:
        return chrome

    for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Chromium\Application\chrome.exe",
    ]:
        if Path(p).exists():
            return p

    macos_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for p in macos_paths:
        if Path(p).exists():
            return p

    linux_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
    ]
    for p in linux_paths:
        if Path(p).exists():
            return p

    return None


def find_ffmpeg() -> Optional[str]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    for p in [
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ]:
        if Path(p).exists():
            return p
    return None


def find_ffprobe(ffmpeg_path: Optional[str] = None) -> Optional[str]:
    """Locate the ffprobe binary.

    Prefers the ffprobe sitting next to a known ffmpeg install (they ship as a
    pair), then falls back to PATH. Returns None if neither is available;
    callers should degrade gracefully rather than fail the whole render.
    """
    if ffmpeg_path:
        sibling = Path(ffmpeg_path).with_name("ffprobe")
        if sibling.exists():
            return str(sibling)
        # Windows: ffmpeg.exe / ffprobe.EXE share a directory.
        for name in ("ffprobe.exe", "ffprobe.EXE", "ffprobe"):
            candidate = Path(ffmpeg_path).parent / name
            if candidate.exists():
                return str(candidate)

    probe = shutil.which("ffprobe")
    if probe:
        return probe
    for p in [
        r"C:\ProgramData\chocolatey\bin\ffprobe.exe",
        r"C:\ffmpeg\bin\ffprobe.exe",
    ]:
        if Path(p).exists():
            return p
    return None
