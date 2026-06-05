#!/usr/bin/env python3
"""Generate a simple stock-themed Windows icon using only the Python standard library."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZE = 256
OUT = Path(__file__).resolve().parent / "app.ico"


def _rgba_pixel(x: int, y: int) -> tuple[int, int, int, int]:
    # Dark gradient background.
    t = y / (SIZE - 1)
    r = int(6 + 10 * t)
    g = int(18 + 22 * t)
    b = int(33 + 25 * t)
    a = 255

    # Glassy panel.
    if 34 <= x <= 222 and 38 <= y <= 218:
        r = int(11 + 8 * t)
        g = int(25 + 10 * t)
        b = int(45 + 12 * t)

    # Green uptrend line.
    points = [
        (48, 186), (78, 168), (108, 176), (138, 132), (170, 150), (202, 92)
    ]
    thickness = 5
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        dx = x2 - x1
        dy = y2 - y1
        seg_len2 = dx * dx + dy * dy
        if seg_len2 == 0:
            continue
        px = x - x1
        py = y - y1
        u = max(0.0, min(1.0, (px * dx + py * dy) / seg_len2))
        cx = x1 + u * dx
        cy = y1 + u * dy
        if (x - cx) ** 2 + (y - cy) ** 2 <= thickness ** 2:
            return (51, 211, 153, 255)

    # Arrow head.
    if 190 <= x <= 214 and 72 <= y <= 100:
        if y <= (-1.2 * x + 328) and y >= (1.2 * x - 157):
            return (51, 211, 153, 255)

    # Small white bars.
    bars = [(54, 196, 6, 14), (66, 189, 6, 21), (78, 181, 6, 29)]
    for bx, by, bw, bh in bars:
        if bx <= x < bx + bw and by <= y < by + bh:
            return (231, 238, 249, 255)

    return (r, g, b, a)


def _build_png() -> bytes:
    rows = []
    for y in range(SIZE):
        row = bytearray([0])  # filter type 0
        for x in range(SIZE):
            r, g, b, a = _rgba_pixel(x, y)
            row.extend((r, g, b, a))
        rows.append(bytes(row))
    compressed = zlib.compress(b"".join(rows), 9)

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)
        ) + chunk_type + data + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


def _build_ico(png: bytes) -> bytes:
    # ICO header + one directory entry pointing at embedded PNG data.
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack(
        "<BBBBHHII",
        0 if SIZE == 256 else SIZE,
        0 if SIZE == 256 else SIZE,
        0,
        0,
        1,
        32,
        len(png),
        6 + 16,
    )
    return header + entry + png


def main() -> None:
    png = _build_png()
    OUT.write_bytes(_build_ico(png))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
