#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parents[1]
GIF_PATH = ROOT / 'assets' / 'mew_loading.gif'
HEADER_PATH = ROOT / 'mew_loading_frames.h'
PREVIEW_PATH = ROOT / 'assets' / 'mew_loading_preview.png'

OUT_W = 32
OUT_H = 32
FRAME_COUNT = 8


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xF8) << 3) | (b >> 3)


def composite_frames(path):
    im = Image.open(path)
    canvas = Image.new('RGBA', im.size, (0, 0, 0, 0))
    frames = []
    for frame in ImageSequence.Iterator(im):
        fr = frame.convert('RGBA')
        canvas.alpha_composite(fr)
        frames.append(canvas.copy())
    return frames


def content_bbox(frames):
    bbox = None
    for fr in frames:
        alpha = fr.getchannel('A')
        b = alpha.getbbox()
        if not b:
            continue
        if bbox is None:
            bbox = b
        else:
            bbox = (
                min(bbox[0], b[0]), min(bbox[1], b[1]),
                max(bbox[2], b[2]), max(bbox[3], b[3])
            )
    return bbox or (0, 0, frames[0].width, frames[0].height)


def square_bbox(bbox, w, h, pad=16):
    left, top, right, bottom = bbox
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(w, right + pad)
    bottom = min(h, bottom + pad)
    bw = right - left
    bh = bottom - top
    side = max(bw, bh)
    cx = (left + right) // 2
    cy = (top + bottom) // 2
    left = max(0, min(w - side, cx - side // 2))
    top = max(0, min(h - side, cy - side // 2))
    return (left, top, left + side, top + side)


def pick_frames(frames, count):
    if len(frames) <= count:
        return frames
    return [frames[round(i * (len(frames) - 1) / (count - 1))] for i in range(count)]


def process_frame(fr, bbox):
    cropped = fr.crop(bbox)
    # Pixel-art GIF: NEAREST keeps the sprite sharper on the small TFT.
    resized = cropped.resize((OUT_W, OUT_H), Image.Resampling.NEAREST)
    out = Image.new('RGB', (OUT_W, OUT_H), (0, 0, 0))
    # Treat transparency as black so it blends with the clock UI.
    out.paste(resized.convert('RGB'), mask=resized.getchannel('A'))
    return out


def main():
    frames = composite_frames(GIF_PATH)
    bbox = square_bbox(content_bbox(frames), frames[0].width, frames[0].height)
    selected = pick_frames(frames, FRAME_COUNT)
    processed = [process_frame(fr, bbox) for fr in selected]

    # Preview strip for human inspection.
    preview = Image.new('RGB', (OUT_W * FRAME_COUNT, OUT_H), (20, 20, 20))
    for i, fr in enumerate(processed):
        preview.paste(fr, (i * OUT_W, 0))
    preview.save(PREVIEW_PATH)

    lines = []
    lines.append('#pragma once')
    lines.append('#include <Arduino.h>')
    lines.append('#include <pgmspace.h>')
    lines.append('')
    lines.append('// Mew loading icon generated from the GIF chosen by Davi.')
    lines.append('// 8 frames, 32x32, RGB565. Transparent pixels become black.')
    lines.append(f'const uint8_t MEW_LOADING_FRAME_COUNT = {FRAME_COUNT};')
    lines.append(f'const uint8_t MEW_LOADING_W = {OUT_W};')
    lines.append(f'const uint8_t MEW_LOADING_H = {OUT_H};')
    lines.append('')
    lines.append(f'const uint16_t mewLoadingFrames[MEW_LOADING_FRAME_COUNT][MEW_LOADING_H][MEW_LOADING_W] PROGMEM = {{')
    for fi, fr in enumerate(processed):
        lines.append('  {')
        px = fr.load()
        for y in range(OUT_H):
            vals = []
            for x in range(OUT_W):
                vals.append(f'0x{rgb565(*px[x, y]):04X}')
            lines.append('    {' + ','.join(vals) + '},')
        lines.append('  },')
    lines.append('};')
    lines.append('')
    lines.append('template <typename TDisplay>')
    lines.append('void drawMewLoadingFrame(TDisplay &display, uint8_t frame, int16_t x, int16_t y) {')
    lines.append('  display.drawRGBBitmap(x, y, (const uint16_t*)mewLoadingFrames[frame % MEW_LOADING_FRAME_COUNT], MEW_LOADING_W, MEW_LOADING_H);')
    lines.append('}')
    lines.append('')
    HEADER_PATH.write_text('\n'.join(lines), encoding='utf-8')
    print(f'frames_in_gif={len(frames)}')
    print(f'used_frames={FRAME_COUNT}')
    print(f'bbox={bbox}')
    print(f'header={HEADER_PATH}')
    print(f'preview={PREVIEW_PATH}')

if __name__ == '__main__':
    main()
