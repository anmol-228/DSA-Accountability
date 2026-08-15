"""Generates minimal solid-color PNG icons for the Chrome extension using
only the stdlib (no Pillow dependency)."""
import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "chrome-extension" / "icons"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Fire-orange, matches the "study streak" theme in the spec's overlay mockups.
COLOR = (255, 107, 26, 255)


def make_png(size: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))

    raw = bytearray()
    r, g, b, a = COLOR
    for y in range(size):
        raw.append(0)  # filter type 0
        for x in range(size):
            # simple rounded-corner-ish disc so it doesn't look like a flat square
            cx, cy = size / 2, size / 2
            dist = ((x - cx + 0.5) ** 2 + (y - cy + 0.5) ** 2) ** 0.5
            if dist <= size / 2:
                raw.extend((r, g, b, a))
            else:
                raw.extend((0, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


for size in (16, 48, 128):
    path = OUT_DIR / f"icon{size}.png"
    path.write_bytes(make_png(size))
    print(f"wrote {path}")
