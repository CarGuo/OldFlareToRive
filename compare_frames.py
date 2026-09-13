#!/usr/bin/env python3
"""Measure exported runtime PNGs and write a labeled comparison sheet (Pillow)."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageStat


def compare(directory):
    rows = []
    sources = sorted(directory.glob('*-flare.png'))
    if not sources:
        raise ValueError('No exported runtime frames found')
    for source in sources:
        a = Image.open(source).convert('RGBA')
        b = Image.open(source.with_name(source.name.replace('-flare', '-rive'))).convert('RGBA')
        if a.size != b.size:
            raise ValueError('Mismatched frame sizes')
        diff = ImageChops.difference(a, b)
        foreground = ImageChops.lighter(a.getchannel('A'), b.getchannel('A')).point(lambda x: 255 if x else 0)
        count = foreground.histogram()[255]
        maximum = diff.getchannel('R')
        for channel in ['G', 'B', 'A']:
            maximum = ImageChops.lighter(maximum, diff.getchannel(channel))
        over = ImageChops.multiply(maximum.point(lambda x: 255 if x > 2 else 0), foreground)
        over_count = over.histogram()[255]
        mean = sum(ImageStat.Stat(diff, foreground).mean) / 4 if count else 0
        fraction = over_count/count if count else 0
        rows.append({'file': source.name, 'foregroundPixels': count,
                     'pixelsOver2Of255': over_count, 'fractionOver2': fraction,
                     'meanAbsoluteRGBA': mean, 'maxChannelDifference': maximum.getextrema()[1],
                     'passed': fraction <= 0.0002 and mean <= 0.002})
    if not any(r['foregroundPixels'] for r in rows):
        raise ValueError('All comparison frames are blank')
    report = {'definition': 'RGBA 8-bit differences over the union of nontransparent pixels; no alignment or color correction',
              'tolerances': {'maxFractionOver2': 0.0002, 'maxMeanAbsoluteRGBA': 0.002},
              'frames': rows, 'passed': all(r['passed'] for r in rows)}
    (directory/'pixel-comparison.json').write_text(json.dumps(report, indent=2)+'\n')

    timeline = [p for p in sources if '-playback-' not in p.name]
    selected = [timeline[round((len(timeline)-1)*f)] for f in (0, 1/3, 2/3, 1)]
    size = Image.open(selected[0]).size
    height = round(512 * size[1] / size[0])
    sheet = Image.new('RGB', (1048, 4*(height+38)+46), '#202934')
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 16), 'Original Flare (legacy clipping)', fill='white')
    draw.text((544, 16), 'Migrated Rive', fill='white')
    for row, source in enumerate(selected):
        for column, suffix in enumerate(['flare', 'rive']):
            image = Image.open(source.with_name(source.name.replace('-flare', '-'+suffix))).convert('RGBA')
            background = Image.new('RGBA', image.size, '#202934')
            background.alpha_composite(image)
            sheet.paste(background.convert('RGB').resize((512,height)), (12+524*column,46+row*(height+38)))
        draw.text((20, 50+height+row*(height+38)), source.stem.replace('-flare', ''), fill='white')
    sheet.save(directory/'comparison-sheet.png')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    report = compare(parser.parse_args().directory)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)
