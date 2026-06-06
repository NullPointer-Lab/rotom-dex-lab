from PIL import Image
from pathlib import Path

src = Path('/home/davi/rotom-dex-lab/firmware/ZappClockOnly/reference-running-pikachu.gif')
out = Path('/home/davi/rotom-dex-lab/firmware/ZappClockOnly/pika_frames.h')
img = Image.open(src)

boxes = []
for i in range(img.n_frames):
    img.seek(i)
    fr = img.convert('RGBA')
    w, h = fr.size
    xs = []
    ys = []
    pix = fr.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = pix[x, y]
            if a == 0:
                continue
            mx = max(r, g, b)
            mn = min(r, g, b)
            sat = 0 if mx == 0 else (mx - mn) / mx
            if (sat > 0.18 and mx > 80) or (mx < 75):
                xs.append(x)
                ys.append(y)
    boxes.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1))

left = min(b[0] for b in boxes)
top = min(b[1] for b in boxes)
right = max(b[2] for b in boxes)
bottom = max(b[3] for b in boxes)
pad = 8
left = max(0, left - pad)
top = max(0, top - pad)
right = min(img.size[0], right + pad)
bottom = min(img.size[1], bottom + pad)

W, H = 32, 24
frames = []
for i in range(img.n_frames):
    img.seek(i)
    fr = img.convert('RGBA').crop((left, top, right, bottom))
    fr.thumbnail((W, H), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    canvas.alpha_composite(fr, ((W - fr.width) // 2, (H - fr.height) // 2))
    vals = []
    for y in range(H):
        row = []
        for x in range(W):
            r, g, b, a = canvas.getpixel((x, y))
            mx = max(r, g, b)
            mn = min(r, g, b)
            sat = 0 if mx == 0 else (mx - mn) / mx
            if a < 20 or (mx > 190 and sat < 0.16):
                row.append(0x0000)
            elif mx < 90 and sat < 0.35:
                row.append(0x8410)  # gray outline visible on black TFT
            else:
                if r > 180 and g > 120 and b < 100:
                    r, g, b = 255, 210, 30
                elif r > 150 and g < 120 and b < 120:
                    r, g, b = 230, 30, 40
                elif r > 70 and g > 35 and b < 100:
                    r, g, b = 150, 80, 20
                row.append(((r // 8) << 11) | ((g // 4) << 5) | (b // 8))
        vals.append(row)
    frames.append(vals)


def hex16(v):
    return f'0x{v:04X}'

lines = []
lines.append('#pragma once')
lines.append('#include <Arduino.h>')
lines.append('#include <pgmspace.h>')
lines.append('')
lines.append('// 4-frame 32x24 icon generated from the running Pikachu cross-stitch reference.')
lines.append('// Background pixels are black; outline pixels are light gray so they are visible on the black clock UI.')
lines.append('const uint8_t PIKA_FRAME_COUNT = 4;')
lines.append('const uint8_t PIKA_W = 32;')
lines.append('const uint8_t PIKA_H = 24;')
lines.append('')
lines.append('const uint16_t pikaFrames[PIKA_FRAME_COUNT][PIKA_H][PIKA_W] PROGMEM = {')
for frame in frames:
    lines.append('  {')
    for row in frame:
        lines.append('    {' + ','.join(hex16(v) for v in row) + '},')
    lines.append('  },')
lines.append('};')
lines.append('')
lines.append('template <typename DisplayT>')
lines.append('void drawPikaFrame(DisplayT &display, uint8_t frame, int16_t x, int16_t y) {')
lines.append('  frame %= PIKA_FRAME_COUNT;')
lines.append('  for (uint8_t py = 0; py < PIKA_H; py++) {')
lines.append('    for (uint8_t px = 0; px < PIKA_W; px++) {')
lines.append('      uint16_t color = pgm_read_word(&pikaFrames[frame][py][px]);')
lines.append('      display.drawPixel(x + px, y + py, color);')
lines.append('    }')
lines.append('  }')
lines.append('}')
lines.append('')

out.write_text('\n'.join(lines))
print(f'bbox={(left, top, right, bottom)} source_frames={img.n_frames} wrote={out} bytes={out.stat().st_size}')
