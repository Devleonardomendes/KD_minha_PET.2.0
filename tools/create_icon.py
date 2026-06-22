from __future__ import annotations

from pathlib import Path
import math
import struct


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "lupa.ico"
SIZES = (256, 64, 48, 32, 16)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def coverage(distance: float, half_width: float, aa: float) -> float:
    return clamp((half_width + aa - distance) / (2 * aa))


def over(dst: tuple[int, int, int, int], src: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    sr, sg, sb, sa_i = src
    dr, dg, db, da_i = dst
    sa = sa_i / 255.0
    da = da_i / 255.0
    out_a = sa + da * (1 - sa)
    if out_a <= 0:
        return 0, 0, 0, 0
    r = int((sr * sa + dr * da * (1 - sa)) / out_a)
    g = int((sg * sa + dg * da * (1 - sa)) / out_a)
    b = int((sb * sa + db * da * (1 - sa)) / out_a)
    return r, g, b, int(out_a * 255)


def line_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx = bx - ax
    vy = by - ay
    wx = px - ax
    wy = py - ay
    length_sq = vx * vx + vy * vy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = clamp((wx * vx + wy * vy) / length_sq)
    cx = ax + t * vx
    cy = ay + t * vy
    return math.hypot(px - cx, py - cy)


def draw_icon(size: int) -> bytes:
    pixels: list[tuple[int, int, int, int]] = []
    aa = 1.4 / size

    cx, cy = 0.43, 0.42
    radius = 0.255
    stroke = 0.075
    inner = radius - stroke * 0.55

    for y in range(size):
        py = (y + 0.5) / size
        for x in range(size):
            px = (x + 0.5) / size
            pixel = (0, 0, 0, 0)

            dist_center = math.hypot(px - cx, py - cy)
            fill_a = clamp((inner + aa - dist_center) / (2 * aa))
            if fill_a:
                pixel = over(pixel, (190, 232, 251, int(130 * fill_a)))

            handle_dist = line_distance(px, py, 0.60, 0.60, 0.84, 0.84)
            handle_a = coverage(handle_dist, stroke * 0.50, aa)
            if handle_a:
                pixel = over(pixel, (20, 64, 94, int(255 * handle_a)))

            ring_dist = abs(dist_center - radius)
            ring_a = coverage(ring_dist, stroke * 0.50, aa)
            if ring_a:
                pixel = over(pixel, (23, 83, 124, int(255 * ring_a)))

            highlight_dist = line_distance(px, py, 0.31, 0.32, 0.43, 0.25)
            highlight_a = coverage(highlight_dist, stroke * 0.18, aa)
            if highlight_a and dist_center < inner:
                pixel = over(pixel, (255, 255, 255, int(165 * highlight_a)))

            pixels.append(pixel)

    return to_dib(size, pixels)


def to_dib(size: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    header = struct.pack(
        "<IIIHHIIIIII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        size * size * 4,
        0,
        0,
        0,
        0,
    )

    bitmap = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            r, g, b, a = pixels[y * size + x]
            bitmap.extend((b, g, r, a))

    mask_row = ((size + 31) // 32) * 4
    mask = bytes(mask_row * size)
    return header + bytes(bitmap) + mask


def write_ico() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images = [(size, draw_icon(size)) for size in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    entries = bytearray()
    offset = 6 + len(images) * 16
    payload = bytearray()

    for size, data in images:
        width_byte = 0 if size >= 256 else size
        entries.extend(
            struct.pack(
                "<BBBBHHII",
                width_byte,
                width_byte,
                0,
                0,
                1,
                32,
                len(data),
                offset,
            )
        )
        payload.extend(data)
        offset += len(data)

    OUT.write_bytes(header + entries + payload)


if __name__ == "__main__":
    write_ico()
    print(OUT)
