#!/usr/bin/env python3

import re
from .ck2parser import rootpath, is_codename, get_cultures, Pair, SimpleParser, FullParser


def process_title(title_pair):
    title, tree = title_pair.key.val, title_pair.value
    for pair in tree:
        if is_codename(pair.key.val):
            process_title(pair)
    try:
        index, b_val = next((i + 1, v.val) for i, (n, v) in enumerate(tree)
                            if n.val == 'greek')
    except StopIteration:
        return
    for culture in ['sicilian_greek']:
        if not tree.get(culture):
            tree.contents[index:index] = [Pair(culture, b_val)]
            index += 1


def main():
    modpath = rootpath / 'Byzantine Melting Pot Expansion/Historical Immersion Project'
    print(list(modpath.glob('../*')))
    simple_parser = SimpleParser()
    full_parser = FullParser()
    simple_parser.moddirs = [modpath]
    cultures = get_cultures(simple_parser, groups=False)
    full_parser.fq_keys = cultures
    for path, tree in full_parser.parse_files('common/landed_titles/*.txt',
                                              modpath):
        for title_pair in tree:
            process_title(title_pair)
        full_parser.write(tree, path)

if __name__ == '__main__':
    main()
