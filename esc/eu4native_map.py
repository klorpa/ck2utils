#!/usr/bin/env python3

from collections import defaultdict
from pathlib import Path
import re
import sys
import matplotlib
import matplotlib.cm
import matplotlib.colors
import numpy as np
from PIL import Image, ImageFont, ImageDraw
from ck2parser import rootpath, csv_rows, SimpleParser
from localpaths import eu4dir
from print_time import print_time

VALUE_FUNC, NAME = lambda natives: natives[0] * 100, 'pop'
# VALUE_FUNC, NAME = lambda natives: natives[1], 'agg'

@print_time
def main():
    parser = SimpleParser()
    parser.basedir = eu4dir
    if len(sys.argv) > 1:
        parser.moddirs.append(Path(sys.argv[1]))
    rgb_number_map = {}
    number_rgb_map = {}
    default_tree = parser.parse_file('map/default.map')
    provinces_path = parser.file('map/' + default_tree['provinces'].val)
    climate_path = parser.file('map/' + default_tree['climate'].val)
    max_provinces = default_tree['max_provinces'].val
    counties = set()
    rgb_map = {}
    for row in csv_rows(parser.file('map/' + default_tree['definitions'].val)):
        try:
            number = int(row[0])
        except ValueError:
            continue
        if number < max_provinces:
            rgb = tuple(np.uint8(row[1:4]))
            rgb_number_map[rgb] = np.uint16(number)
            number_rgb_map[number] = rgb
            counties.add(number)
            rgb_map[tuple(rgb)] = np.uint8((127, 127, 127)) # normal province

    migratory_govs = set()
    for _, tree in parser.parse_files('common/governments/*'):
        for n, v in tree:
            if v.has_pair('allow_migration', 'yes'):
                migratory_govs.add(n.val)

    migratory_provs = {}
    for path, tree in parser.parse_files('history/countries/*'):
        tag = path.stem[:3]
        gov = None
        history = defaultdict(list)
        for n, v in tree:
            if n.val == 'government':
                gov = v.val
            elif isinstance(n.val, tuple) and n.val <= (1444, 11, 11):
                history[n.val].extend(v)
        for _, v in sorted(history.items()):
            for n2, v2 in v:
                if n2.val == 'government':
                    gov = v2.val
        if gov in migratory_govs:
            migratory_provs[tag] = []

    province_value = {}
    vmin, vmax = 0, 0
    for path in parser.files('history/provinces/*'):
        match = re.match(r'\d+', path.stem)
        if not match:
            continue
        number = int(match.group())
        if number >= max_provinces:
            continue
        if number in province_value:
            print('extra province history {}'.format(path), file=sys.stderr)
            continue
        tree = parser.parse_file(path)
        natives = [0, 0]
        owner = None
        history = defaultdict(list)
        for n, v in tree:
            if n.val == 'owner':
                owner = v.val
            elif n.val == 'native_size':
                natives[0] = v.val
            elif n.val == 'native_hostileness':
                natives[1] = v.val
            elif isinstance(n.val, tuple) and n.val <= (1444, 11, 11):
                history[n.val].extend(v)
        for _, v in sorted(history.items()):
            for n2, v2 in v:
                if n2.val == 'owner':
                    owner = v2.val
                elif n2.val == 'native_size':
                    natives[0] = v2.val
                elif n2.val == 'native_hostileness':
                    natives[1] = v2.val
        if owner in migratory_provs:
            migratory_provs[owner].append(number)
        if owner is None or owner in migratory_provs:
            province_value[number] = VALUE_FUNC(natives)
        else:
            province_value[number] = -1
        vmax = max(vmax, province_value[number])

    for tag, provs in migratory_provs.items():
        if len(provs) > 1:
            for prov in provs:
                province_value[prov] = -1

    cmap = matplotlib.cm.get_cmap('plasma')
    norm = matplotlib.colors.Normalize(vmin, vmax * 4 / 3)
    colormap = matplotlib.cm.ScalarMappable(cmap=cmap, norm=norm)
    for number, value in province_value.items():
        if value < 0:
            color = np.uint8((127, 127, 127))
        else:
            color = np.uint8(colormap.to_rgba(value, bytes=True)[:3])
        rgb_map[number_rgb_map[number]] = color

    for n in parser.parse_file(climate_path)['impassable']:
        rgb_map[number_rgb_map[int(n.val)]] = np.uint8((36, 36, 36)) # desert
        counties.discard(int(n.val))
    for n in default_tree['sea_starts']:
        rgb_map[number_rgb_map[int(n.val)]] = np.uint8((51, 67, 85)) # sea
        counties.discard(int(n.val))
    for n in default_tree['lakes']:
        try:
            rgb_map[number_rgb_map[int(n.val)]] = np.uint8((51, 67, 85)) # sea
            counties.discard(int(n.val))
        except KeyError:
            pass
    for n in default_tree['only_used_for_random']:
        counties.discard(int(n.val))
    image = Image.open(str(provinces_path))
    a = np.array(image)
    b = np.apply_along_axis(lambda x: rgb_number_map[tuple(x)], 2, a)
    a = np.apply_along_axis(lambda x: rgb_map[tuple(x)], 2, a)
    txt = Image.new('RGBA', image.size, (0, 0, 0, 0))
    lines = Image.new('RGBA', image.size, (0, 0, 0, 0))
    draw_txt = ImageDraw.Draw(txt)
    draw_lines = ImageDraw.Draw(lines)
    font = ImageFont.truetype(str(rootpath / 'ck2utils/esc/NANOTYPE.ttf'), 16)
    maxlen = len(str(vmax))
    e = {(n * 4 - 1, 5): np.ones_like(b, bool) for n in range(1, maxlen + 1)}
    for number in sorted(rgb_number_map.values()):
        if number not in counties:
            continue
        print('\r' + str(number), end='', file=sys.stderr)
        value = province_value[number]
        if value < 0:
            continue
        size = len(str(value)) * 4 - 1, 5
        c = np.nonzero(b == number)
        center = np.mean(c[1]), np.mean(c[0])
        pos = [int(round(max(0, min(center[0] - size[0] / 2,
                                    image.width - size[0])))),
               int(round(max(0, min(center[1] - size[1] / 2,
                                    image.height - size[1]))))]
        pos[2:] = pos[0] + size[0], pos[1] + size[1]
        if not e[size][pos[1], pos[0]]:
            x1, x2 = max(0, pos[0] - 1), min(pos[0] + 2, image.width)
            y1, y2 = max(0, pos[1] - 1), min(pos[1] + 2, image.height)
            if not np.any(e[size][y1:y2, x1:x2]):
                x1, y1, (x2, y2) = 0, 0, image.size
            f = np.nonzero(e[size][y1:y2, x1:x2])
            g = (f[0] - pos[1]) ** 2 + (f[1] - pos[0]) ** 2
            pos[:2] = np.transpose(f)[np.argmin(g)][::-1] + [x1, y1]
            pos[2:] = pos[0] + size[0], pos[1] + size[1]
        draw_txt.text((pos[0], pos[1] - 6), str(value),
                      fill=(255, 255, 255, 255), font=font)
        for size2 in e:
            rows = slice(max(pos[1] - size2[1] - 1, 0), pos[3] + 2)
            cols = slice(max(pos[0] - size2[0] - 1, 0), pos[2] + 2)
            e[size2][rows, cols] = False
        x = int(round(pos[0] + size[0] / 2))
        y = int(round(pos[1] + size[1] / 2))
        if b[y, x] != number:
            d = (c[0] - y) ** 2 + (c[1] - x) ** 2
            dest = tuple(np.transpose(c)[np.argmin(d)][::-1])
            start = (max(pos[0] - 1, min(dest[0], pos[2])),
                     max(pos[1] - 1, min(dest[1], pos[3])))
            if start != dest:
                print('\rline drawn for {}'.format(number), file=sys.stderr)
                draw_lines.line([start, dest], fill=(192, 192, 192))
    print('', file=sys.stderr)
    out = Image.fromarray(a)
    mod = parser.moddirs[0].name.lower() + '_' if parser.moddirs else ''
    borders_path = rootpath / (mod + 'eu4borderlayer.png')
    borders = Image.open(str(borders_path))
    out.paste(borders, mask=borders)
    out.paste(lines, mask=lines)
    out.paste(txt, mask=txt)
    out_path = rootpath / (mod + 'eu4native{}_map.png'.format(NAME))
    out.save(str(out_path))

if __name__ == '__main__':
    main()
