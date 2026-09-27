"""Parse `/Imagine`, summarize the desk, render a still, and request a clip."""

from __future__ import annotations

import base64
import os
import re
import struct
import time
import zlib
from collections import Counter
from typing import Any

_TOKEN = re.compile(r"(?<!\S)/Imagine(?!\S)")
_SKIP_ISSUE_TYPES = frozenset({"ai_likeness"})

# Tiny 5x7 glyphs for printable ASCII (32–126). Each glyph is 7 rows of 5 bits.
_GLYPH_W = 5
_GLYPH_H = 7
_GLYPHS: dict[str, tuple[str, ...]] = {
    " ": ("00000",) * 7,
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    '"': ("01010", "01010", "01010", "00000", "00000", "00000", "00000"),
    "#": ("01010", "01010", "11111", "01010", "11111", "01010", "01010"),
    "$": ("00100", "01111", "10100", "01110", "00101", "11110", "00100"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "&": ("01100", "10010", "10100", "01000", "10101", "10010", "01101"),
    "'": ("00100", "00100", "00100", "00000", "00000", "00000", "00000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "*": ("00000", "00100", "10101", "01110", "10101", "00100", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    ",": ("00000", "00000", "00000", "00000", "00100", "00100", "01000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00100", "00100"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("01110", "10001", "00001", "00110", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    ":": ("00000", "00100", "00100", "00000", "00100", "00100", "00000"),
    ";": ("00000", "00100", "00100", "00000", "00100", "00100", "01000"),
    "<": ("00010", "00100", "01000", "10000", "01000", "00100", "00010"),
    "=": ("00000", "00000", "11111", "00000", "11111", "00000", "00000"),
    ">": ("01000", "00100", "00010", "00001", "00010", "00100", "01000"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    "@": ("01110", "10001", "10011", "10101", "10011", "10000", "01110"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01110", "10001", "10000", "01110", "00001", "10001", "01110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "[": ("01110", "01000", "01000", "01000", "01000", "01000", "01110"),
    "\\": ("10000", "01000", "01000", "00100", "00010", "00010", "00001"),
    "]": ("01110", "00010", "00010", "00010", "00010", "00010", "01110"),
    "^": ("00100", "01010", "10001", "00000", "00000", "00000", "00000"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    "`": ("01000", "00100", "00010", "00000", "00000", "00000", "00000"),
    "a": ("00000", "00000", "01110", "00001", "01111", "10001", "01111"),
    "b": ("10000", "10000", "11110", "10001", "10001", "10001", "11110"),
    "c": ("00000", "00000", "01110", "10001", "10000", "10001", "01110"),
    "d": ("00001", "00001", "01111", "10001", "10001", "10001", "01111"),
    "e": ("00000", "00000", "01110", "10001", "11111", "10000", "01110"),
    "f": ("00110", "01001", "01000", "11100", "01000", "01000", "01000"),
    "g": ("00000", "00000", "01111", "10001", "10001", "01111", "00001"),
    "h": ("10000", "10000", "11110", "10001", "10001", "10001", "10001"),
    "i": ("00100", "00000", "01100", "00100", "00100", "00100", "01110"),
    "j": ("00010", "00000", "00110", "00010", "00010", "10010", "01100"),
    "k": ("10000", "10000", "10010", "10100", "11000", "10100", "10010"),
    "l": ("01100", "00100", "00100", "00100", "00100", "00100", "01110"),
    "m": ("00000", "00000", "11010", "10101", "10101", "10101", "10101"),
    "n": ("00000", "00000", "11110", "10001", "10001", "10001", "10001"),
    "o": ("00000", "00000", "01110", "10001", "10001", "10001", "01110"),
    "p": ("00000", "00000", "11110", "10001", "10001", "11110", "10000"),
    "q": ("00000", "00000", "01111", "10001", "10001", "01111", "00001"),
    "r": ("00000", "00000", "10110", "11001", "10000", "10000", "10000"),
    "s": ("00000", "00000", "01111", "10000", "01110", "00001", "11110"),
    "t": ("01000", "01000", "11100", "01000", "01000", "01001", "00110"),
    "u": ("00000", "00000", "10001", "10001", "10001", "10011", "01101"),
    "v": ("00000", "00000", "10001", "10001", "10001", "01010", "00100"),
    "w": ("00000", "00000", "10001", "10001", "10101", "10101", "01010"),
    "x": ("00000", "00000", "10001", "01010", "00100", "01010", "10001"),
    "y": ("00000", "00000", "10001", "10001", "10001", "01111", "00001"),
    "z": ("00000", "00000", "11111", "00010", "00100", "01000", "11111"),
    "{": ("00010", "00100", "00100", "01000", "00100", "00100", "00010"),
    "|": ("00100", "00100", "00100", "00100", "00100", "00100", "00100"),
    "}": ("01000", "00100", "00100", "00010", "00100", "00100", "01000"),
    "~": ("00000", "00000", "01000", "10101", "00010", "00000", "00000"),
}

_BG = (245, 245, 240)
_FG = (28, 28, 32)
_PAD = 12
_LINE_GAP = 4
_CHAR_GAP = 1
_MAX_WIDTH = 640
_MAX_LINES = 18
_SCALE = 2


def parse_imagine(question: str) -> str | None:
    """Return the wish after removing one exact `/Imagine` token, or None."""
    match = _TOKEN.search(question)
    if match is None:
        return None
    rest = f"{question[: match.start()]}{question[match.end() :]}"
    return " ".join(rest.split())


def desk_summary(name: str, papers: list[dict[str, Any]]) -> str:
    """Plain-text summary of papers already on a conference desk."""
    if not papers:
        label = name.strip()
        if label:
            return f"{label} has no papers yet."
        return "This desk has no papers yet."

    lines: list[str] = []
    for paper in papers:
        title = (paper.get("title") or "").strip()
        label = title or str(paper.get("arxiv_id") or "")
        status = paper.get("status") or ""
        counts: Counter[str] = Counter()
        for issue in paper.get("issues") or []:
            issue_type = issue.get("issue_type")
            if not issue_type or issue_type in _SKIP_ISSUE_TYPES:
                continue
            counts[str(issue_type)] += 1
        if counts:
            tally = ", ".join(f"{kind} {n}" for kind, n in sorted(counts.items()))
            lines.append(f"{label}: {status}; {tally}")
        else:
            lines.append(f"{label}: {status}; no issues")
    return "\n".join(lines)


def motion_prompt(summary: str, wish: str) -> str:
    """Build the motion prompt for animating a desk still."""
    parts = [
        "Animate this still as a six-second briefing.",
        "Do not add papers, numbers, or verdicts.",
        "Keep the motion on these summary lines:",
        summary.strip() or "(empty desk)",
    ]
    wish_text = wish.strip()
    if wish_text:
        parts.insert(1, f"Follow this wish: {wish_text}.")
    return " ".join(parts)


def render_still(title: str, summary: str) -> bytes:
    """Draw a PNG still of the conference title and summary (stdlib only)."""
    title_line = _sanitize(title.strip() or "Conference desk")
    body_lines = [_sanitize(line) for line in summary.splitlines() if line.strip()]
    if not body_lines:
        body_lines = [_sanitize(summary.strip() or "(empty)")]
    lines = [title_line, ""] + body_lines
    lines = lines[: _MAX_LINES]

    cell_w = (_GLYPH_W + _CHAR_GAP) * _SCALE
    cell_h = (_GLYPH_H + _LINE_GAP) * _SCALE
    max_chars = max(1, (_MAX_WIDTH - 2 * _PAD) // cell_w)
    wrapped: list[str] = []
    for i, line in enumerate(lines):
        if not line:
            wrapped.append("")
            continue
        chunks = _wrap(line, max_chars)
        if i == 0 and len(chunks) > 1:
            wrapped.append(chunks[0][: max_chars - 1] + "…")
        else:
            wrapped.extend(chunks)
    wrapped = wrapped[:_MAX_LINES]

    width = min(
        _MAX_WIDTH,
        max(len(line) for line in wrapped) * cell_w + 2 * _PAD if wrapped else _MAX_WIDTH,
    )
    width = max(width, 160)
    height = len(wrapped) * cell_h + 2 * _PAD
    height = max(height, 80)

    pixels = bytearray([_BG[0], _BG[1], _BG[2]] * (width * height))

    y = _PAD
    for line in wrapped:
        x = _PAD
        for ch in line:
            _blit(pixels, width, height, x, y, ch)
            x += cell_w
            if x + cell_w > width - _PAD:
                break
        y += cell_h
        if y + cell_h > height:
            break

    return _encode_png(width, height, pixels)


def generate_clip(still: bytes, prompt: str) -> str | None:
    """Request a video clip from xAI; return the URL or None."""
    key = (os.environ.get("XAI_API_KEY") or "").strip()
    if not key:
        return None
    try:
        return _xai_video(key, still, prompt)
    except Exception:
        return None


def _xai_video(key: str, still: bytes, prompt: str) -> str | None:
    """POST a video generation, poll until done, return video.url."""
    import httpx

    data_uri = "data:image/png;base64," + base64.b64encode(still).decode("ascii")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "grok-imagine-video-1.5",
        "prompt": prompt,
        "duration": 6,
        "image": {"url": data_uri},
    }
    with httpx.Client(timeout=30.0) as client:
        post = client.post(
            "https://api.x.ai/v1/videos/generations",
            headers=headers,
            json=body,
        )
        post.raise_for_status()
        posted = post.json()
        request_id = posted.get("request_id")
        if not request_id:
            return None

        for _ in range(45):
            get = client.get(
                f"https://api.x.ai/v1/videos/{request_id}",
                headers=headers,
            )
            get.raise_for_status()
            payload = get.json()
            status = payload.get("status")
            if status == "done":
                video = payload.get("video") or {}
                url = video.get("url")
                return url if isinstance(url, str) and url else None
            if status in {"failed", "expired"}:
                return None
            if status is None and not isinstance(payload, dict):
                return None
            time.sleep(2)
    return None


def _sanitize(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if 32 <= ord(ch) <= 126:
            out.append(ch)
        elif ch in "\t":
            out.append(" ")
        else:
            out.append("?")
    return "".join(out)


def _wrap(line: str, max_chars: int) -> list[str]:
    if len(line) <= max_chars:
        return [line]
    chunks: list[str] = []
    start = 0
    while start < len(line):
        chunks.append(line[start : start + max_chars])
        start += max_chars
    return chunks


def _blit(
    pixels: bytearray, width: int, height: int, x0: int, y0: int, ch: str
) -> None:
    rows = _GLYPHS.get(ch) or _GLYPHS["?"]
    for row_i, bits in enumerate(rows):
        for col_i, bit in enumerate(bits):
            if bit != "1":
                continue
            for dy in range(_SCALE):
                for dx in range(_SCALE):
                    x = x0 + col_i * _SCALE + dx
                    y = y0 + row_i * _SCALE + dy
                    if 0 <= x < width and 0 <= y < height:
                        i = (y * width + x) * 3
                        pixels[i] = _FG[0]
                        pixels[i + 1] = _FG[1]
                        pixels[i + 2] = _FG[2]


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    length = struct.pack(">I", len(data))
    crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return length + tag + data + crc


def _encode_png(width: int, height: int, rgb: bytearray) -> bytes:
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # filter: None
        start = y * stride
        raw.extend(rgb[start : start + stride])
    compressed = zlib.compress(bytes(raw), 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )
