#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageSequence, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
GIF_PATH = ROOT / 'assets' / 'new_pokemon_loading.gif'
HEADER_PATH = ROOT / 'pokemon_loading_frames.h'
PREVIEW_PATH = ROOT / 'assets' / 'new_pokemon_loading_preview.png'

OUT_W = 32
OUT_H = 32
FRAME_COUNT = 8


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xF8) << 3) | (b >> 3)


def composite_frames(path):
    # For this sticker, using the composed canvas makes the crop too large.
    # Use each raw frame so the visible Pokemon is cropped tightly.
    im = Image.open(path)
    return [frame.convert('RGBA') for frame in ImageSequence.Iterator(im)]


def frame_bbox(fr):
    # Use alpha + brightness, because some Giphy stickers have a very large transparent/motion area.
    alpha = fr.getchannel('A').point(lambda v: 255 if v > 20 else 0)
    bright = fr.convert('RGB').convert('L').point(lambda v: 255 if v > 28 else 0)
    mask = ImageChops.multiply(alpha, bright)
    bbox = mask.getbbox()
    return bbox or (0, 0, fr.width, fr.height)


def square_bbox(bbox, w, h, pad_ratio=0.08):
    left, top, right, bottom = bbox
    bw = right - left
    bh = bottom - top
    pad = int(max(bw, bh) * pad_ratio)
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(w, right + pad)
    bottom = min(h, bottom + pad)
    side = max(right - left, bottom - top)
    cx = (left + right) // 2
    cy = (top + bottom) // 2
    left = max(0, min(w - side, cx - side // 2))
    top = max(0, min(h - side, cy - side // 2))
    return (left, top, left + side, top + side)


def pick_frames(frames, count):
    if len(frames) <= count:
        return frames
    return [frames[round(i * (len(frames) - 1) / (count - 1))] for i in range(count)]


def process_frame(fr):
    bbox = square_bbox(frame_bbox(fr), fr.width, fr.height)
    cropped = fr.crop(bbox)
    # LANCZOS preserves detail better when shrinking a large 1080px sticker to 32px.
    resized = cropped.resize((OUT_W, OUT_H), Image.Resampling.LANCZOS).filter(ImageFilter.SHARPEN)
    out = Image.new('RGB', (OUT_W, OUT_H), (0, 0, 0))
    out.paste(resized.convert('RGB'), mask=resized.getchannel('A'))
    return out, bbox


def main():
    frames = composite_frames(GIF_PATH)
    selected = pick_frames(frames, FRAME_COUNT)
    processed = []
    boxes = []
    for fr in selected:
        p, b = process_frame(fr)
        processed.append(p)
        boxes.append(b)

    preview = Image.new('RGB', (OUT_W * FRAME_COUNT, OUT_H), (20, 20, 20))
    for i, fr in enumerate(processed):
        preview.paste(fr, (i * OUT_W, 0))
    preview.save(PREVIEW_PATH)

    lines = [
        '#pragma once',
        '#include <Arduino.h>',
        '#include <pgmspace.h>',
        '',
        '// Pokemon loading icon generated from the Giphy sticker chosen by Davi.',
        '// 8 frames, 32x32, RGB565. Each frame is cropped individually for a sharper TFT icon.',
        f'const uint8_t POKEMON_LOADING_FRAME_COUNT = {FRAME_COUNT};',
        f'const uint8_t POKEMON_LOADING_W = {OUT_W};',
        f'const uint8_t POKEMON_LOADING_H = {OUT_H};',
        '',
        'const uint16_t pokemonLoadingFrames[POKEMON_LOADING_FRAME_COUNT][POKEMON_LOADING_H][POKEMON_LOADING_W] PROGMEM = {'
    ]
    for fr in processed:
        lines.append('  {')
        px = fr.load()
        for y in range(OUT_H):
            vals = [f'0x{rgb565(*px[x, y]):04X}' for x in range(OUT_W)]
            lines.append('    {' + ','.join(vals) + '},')
        lines.append('  },')
    lines.extend([
        '};',
        '',
        'template <typename TDisplay>',
        'void drawPokemonLoadingFrame(TDisplay &display, uint8_t frame, int16_t x, int16_t y) {',
        '  display.drawRGBBitmap(x, y, (const uint16_t*)pokemonLoadingFrames[frame % POKEMON_LOADING_FRAME_COUNT], POKEMON_LOADING_W, POKEMON_LOADING_H);',
        '}',
        ''
    ])
    HEADER_PATH.write_text('\n'.join(lines), encoding='utf-8')
    print(f'frames_in_gif={len(frames)}')
    print(f'used_frames={FRAME_COUNT}')
    print(f'boxes={boxes}')
    print(f'header={HEADER_PATH}')
    print(f'preview={PREVIEW_PATH}')

if __name__ == '__main__':
    main()
