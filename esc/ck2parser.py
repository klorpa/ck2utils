#!/usr/bin/env python3

import collections
import csv
import functools
import hashlib
import operator
import os
import pathlib
import pickle
import re
import sys
import time
import traceback
from funcparserlib.lexer import make_tokenizer, Token
from funcparserlib.parser import (some, a, maybe, many, finished, skip,
                                  oneplus, forward_decl, NoParseError)
from localpaths import rootpath, vanilladir, cachedir
from functools import total_ordering

try:
    import git
    git_present = True
except ImportError:
    git_present = False

VERSION = 3

csv.register_dialect('ckii', delimiter=';', doublequote=False,
                     quotechar='\0', quoting=csv.QUOTE_NONE, strict=True)

def csv_rows(path, linenum=False, comments=False):
    with open(str(path), newline='', encoding='cp1252', errors='replace') as f:
        gen = ((r, i + 1) if linenum else r
               for i, r in enumerate(csv.reader(f, dialect='ckii'))
               if (r and r[0] and
                   (r[0].startswith('#') and comments or
                    not r[0].startswith('#') and len(r) > 1)))
        yield from gen

def replace_paths_from_mod(path):
    result = set()
    try:
        modfile = next(path.glob('*.mod'))
    except StopIteration:
        return result
    with open(modfile) as f:
        for line in f:
            if match := re.match(r'replace_path\s*=\s*"([^"]+)"', line):
                result.add(pathlib.Path(match[1]))
    return result


# give mod dirs in descending lexicographical order of mod name (Z-A),
# modified for dependencies as necessary.
def files(glob, moddirs=(), basedir=vanilladir, reverse=False):
    result_paths = {}
    for d in (basedir,) + tuple(moddirs):
        # this should be cached...
        if replace_paths := replace_paths_from_mod(d):
            for k in list(result_paths.keys()):
                if not replace_paths.isdisjoint(k.parents):
                    del result_paths[k]
        for p in d.glob(glob):
            result_paths[p.relative_to(d)] = p
    for _, p in sorted(result_paths.items(), key=lambda t: t[0].parts,
                       reverse=reverse):
        yield p

def get_cultures(parser, groups=True):
    cultures = []
    culture_groups = []
    for _, tree in parser.parse_files('common/cultures/*.txt'):
        for n, v in tree:
            culture_groups.append(n.val)
            cultures.extend(n2.val for n2, v2 in v
                            if n2.val not in ['graphical_cultures',
                                              'unit_graphical_cultures',
                                              'alternate_start'])
    return (cultures, culture_groups) if groups else cultures

def get_religions(parser, groups=True):
    religions = []
    religion_groups = []
    for _, tree in parser.parse_files('common/religions/*.txt'):
        for n, v in tree:
            if n.val == 'secret_religion_visibility_trigger':
                continue
            religion_groups.append(n.val)
            religions.extend(n2.val for n2, v2 in v
                             if (isinstance(v2, Obj) and
                                 n2.val not in ['color', 'male_names',
                                                'female_names',
                                                'interface_skin']))
    return (religions, religion_groups) if groups else religions

def get_province_id_name_map(parser):
    defs = parser.parse_file('map/default.map')['definitions'].val
    id_name_map = {}
    for row in csv_rows(parser.file('map/' + defs)):
        try:
            id_name_map[int(row[0])] = row[4]
        except (IndexError, ValueError):
            continue
    return id_name_map

def get_provinces(parser):
    id_name = get_province_id_name_map(parser)
    for path in parser.files('history/provinces/* - *.txt'):
        number, name = path.stem.split(' - ')
        number = int(number)
        if id_name.get(number) == name:
            tree = parser.parse_file(path)
            try:
                title = tree['title'].val
            except KeyError:
                continue
            yield number, title, tree

def get_localisation(moddirs=(), basedir=vanilladir, ordered=False):
    locs = collections.OrderedDict() if ordered else {}
    for path in files('localisation/*.csv', moddirs, basedir=basedir):
        for row in csv_rows(path):
            if row[0] not in locs:
                locs[row[0]] = row[1]
    return locs

def first_post_comment(item):
    if item.post_comment:
        return item.post_comment.val.split('#', 1)[0].strip()
    return None

def prepend_post_comment(item, s, force=False):
    if force or first_post_comment(item) != s:
        if item.post_comment:
            s += ' ' + str(item.post_comment)
        item.post_comment = Comment(s)

def is_codename(string):
    try:
        return re.match(r'[ekdcb]_', string) is not None
    except TypeError:
        return False

def chars(line, parser):
    line = str(line)
    try:
        line = line.splitlines()[-1]
    except IndexError: # empty string
        pass
    col = 0
    for char in line:
        if char == '\t':
            col = (col // parser.indent_width + 1) * parser.indent_width
        else:
            col += 1
    return col

def comments_to_str(parser, comments, indent):
    s = ''
    if indent == 0 and comments and comments[0].val.startswith('-*-'):
        s = str(comments[0]) + '\n\n'
        comments = comments[1:]
    if not comments:
        return s
    indent_str = '\t' if parser.tab_indents else ' ' * parser.indent_width
    sep = '\n' + indent * indent_str
    comments_str = '\n'.join(c.val for c in comments)
    if comments_str == '':
        return s
    try:
        tree = parser.parse(comments_str)
        if not tree.contents:
            raise ValueError()
    except (NoParseError, ValueError):
        butlast = comments_to_str(parser, comments[:-1], indent)
        if butlast:
            butlast += indent * indent_str
        return s + butlast + str(comments[-1]) + '\n'
    for p in tree:
        p_is, _ = p.inline_str(parser, indent)
        p_is_lines = p_is.rstrip().splitlines()
        s += '#' + p_is_lines[0] + sep
        s += ''.join('#' + line[len(sep) - 1:] + sep
                     for line in p_is_lines[1:])
    if tree.post_comments:
        s += comments_to_str(parser, tree.post_comments, indent)
    s = s.rstrip('\t ')
    return s


class Comment:
    def __init__(self, string):
        if string and string[0] == '#':
            string = string[1:]
        self.val = string.strip()

    def __str__(self):
        return ('# ' if self.val and self.val[0] != '#' else '#') + self.val


class Stringifiable:
    pass


class TopLevel(Stringifiable):

    def __init__(self, contents=None, post_comments=None):
        super().__init__()
        if contents is None:
            self.contents = []
        else:
            self.contents = contents
        if post_comments is None:
            self.post_comments = []
        else:
            self.post_comments = [Comment(s) for s in post_comments]
        self._dictionary = None

    def __len__(self):
        return len(self.contents)

    def __contains__(self, item):
        return item in self.contents

    def __iter__(self):
        return iter(self.contents)

    def __getitem__(self, key):
        return self.dictionary[key]

    def __reversed__(self):
        return reversed(self.contents)

    @property
    def pre_comments(self):
        return self.contents[0].pre_comments if self.contents else None

    @pre_comments.setter
    def pre_comments(self, value):
        if not self.contents:
            raise RuntimeError('setting pre_comments on empty toplevel')
        self.contents[0].pre_comments = value

    @property
    def header_comment(self):
        c_list = self.pre_comments or self.post_comments
        if c_list[0].val.startswith('-*-'):
            return c_list[0].val
        return None

    @header_comment.setter
    def header_comment(self, value):
        del self.header_comment
        if self.pre_comments is not None:
            c_list = self.pre_comments
        else:
            c_list = self.post_comments
        c_list.insert(0, value)

    @header_comment.deleter
    def header_comment(self):
        if self.pre_comments is not None:
            c_list = self.pre_comments
        else:
            c_list = self.post_comments
        if (c_list and c_list[0].val.startswith('-*-')):
            del c_list[0]

    def get(self, *args, **kwargs):
        return self.dictionary.get(*args, **kwargs)

    # assumes keys occur at most once
    def has_pair(self, key_val, val_val):
        return key_val in self.dictionary and self[key_val].val == val_val

    @property
    def has_pairs(self):
        return not self.contents or isinstance(self.contents[0], Pair)

    @property
    def dictionary(self):
        if self._dictionary is None:
            self._dictionary = {k.val: v for k, v in reversed(self.contents)}
        return self._dictionary

    def str(self, parser, indent=0):
        s = ''
        for i, item in enumerate(self):
            s += item.str(parser, indent)
            if indent <= parser.newlines_to_depth:
                if (i < len(self) - 1 and (isinstance(item.value, Obj) or
                    isinstance(self.contents[i + 1].value, Obj))):
                    s += '\n'
        if self.post_comments:
            s += comments_to_str(parser, self.post_comments, indent)
        return s


class Commented(Stringifiable):

    def __init__(self, *args):
        super().__init__()
        if len(args) == 3:
            self.pre_comments = [Comment(s) for s in args[0]]
            self.val = self.str_to_val(args[1])
            self.post_comment = Comment(args[2]) if args[2] else None
        elif len(args) == 2:
            self.pre_comments = args[1].pre_comments
            if isinstance(args[0], str):
                self.val = self.str_to_val(args[0])
            else:
                self.val = args[0]
            self.post_comment = args[1].post_comment
        else:
            self.pre_comments = []
            self.val = self.str_to_val(args[0])
            self.post_comment = None

    @property
    def has_comments(self):
        return self.pre_comments or self.post_comment

    def str_to_val(self, string):
        return string

    def val_str(self):
        return str(self.val)

    def val_inline_str(self, parser, col=0):
        s = self.val_str()
        return s, col + chars(s, parser)

    def str(self, parser, indent=0):
        s = ''
        indent_str = '\t' if parser.tab_indents else ' ' * parser.indent_width
        if self.pre_comments:
            s += indent * indent_str
            s += comments_to_str(parser, self.pre_comments, indent)
        s += indent * indent_str + self.val_str()
        if self.post_comment:
            s += ' ' + str(self.post_comment)
        s += '\n'
        return s

    def inline_str(self, parser, indent=0, col=0):
        nl = 0
        indent_str = '\t' if parser.tab_indents else ' ' * parser.indent_width
        sep = '\n' + indent * indent_str
        s = ''
        if self.pre_comments:
            if col > indent * parser.indent_width:
                s += sep
                nl += 1
            if isinstance(self, Op) and self.val == '}':
                pre_indent = indent + 1
                s += indent_str
            else:
                pre_indent = indent
            # I can't tell the difference if I'm just after, say, "NOT = { "
            # with indent_width == 8, but whatever. # ?????
            c_s = (comments_to_str(parser, self.pre_comments, pre_indent) +
                   sep[1:])
            s += c_s
            nl += c_s.count('\n')
            col = indent * parser.indent_width
        val_is, col_val = self.val_inline_str(parser, col)
        s += val_is
        col = col_val
        if self.post_comment:
            s += ' ' + str(self.post_comment) + sep
            nl += 1
            col = indent * parser.indent_width
        return s, (nl, col)


@total_ordering
class String(Commented):

    def __init__(self, *args):
        super().__init__(*args)
        self.force_quote = False

    def val_str(self):
        s = self.val
        if self.force_quote or not re.fullmatch(r'\S+', s):
            s = '"{}"'.format(s)
        return s

    def __str__(self):
        return self.val

    def __hash__(self):
        return hash(self.val)

    def __eq__(self, other):
        if isinstance(other, String):
            return self.val == other.val
        else:
            return self.val == other

    def __lt__(self, other):
        if isinstance(other, String):
            return self.val < other.val
        else:
            return self.val < other


@total_ordering
class Number(Commented):

    def str_to_val(self, string):
        try:
            return int(string)
        except ValueError:
            return float(string)

    def __hash__(self):
        return hash(self.val)

    def __str__(self):
        return str(self.val)

    def __eq__(self, other):
        if isinstance(other, Number):
            return self.val == other.val
        else:
            return self.val == other

    def __lt__(self, other):
        if isinstance(other, Number):
            return self.val < other.val
        else:
            return self.val < other

class Date(Commented):

    def str_to_val(self, string):
        return tuple((int(x) if x else 0) for x in string.split('.'))

    def val_str(self):
        return '{}.{}.{}'.format(*self.val)


class Op(Commented):
    pass


class Pair(Stringifiable):

    def __init__(self, *args):
        super().__init__()
        if len(args) == 3:
            self.key = args[0]
            self.op = args[1]
            self.value = args[2]
        elif len(args) == 2:
            if isinstance(args[0], Stringifiable):
                self.key = args[0]
            else:
                self.key = String(args[0])
            self.op = Op('=')
            if isinstance(args[1], Stringifiable):
                self.value = args[1]
            elif isinstance(args[1], list):
                self.value = Obj(args[1])
            else:
                self.value = String(args[1])
        else:
            if isinstance(args[0], Stringifiable):
                self.key = args[0]
            else:
                self.key = String(args[0])
            self.op = Op('=')
            self.value = Obj([])

    def __iter__(self):
        yield self.key
        yield self.value

    @property
    def pre_comments(self):
        return self.key.pre_comments

    @pre_comments.setter
    def pre_comments(self, value):
        self.key.pre_comments = value

    @property
    def post_comment(self):
        return self.val.post_comment

    @post_comment.setter
    def post_comment(self, value):
        self.val.post_comment = value

    @property
    def has_comments(self):
        return any(x.has_comments for x in (self.key, self.op, self.value))

    def str(self, parser, indent=0):
        indent_str = '\t' if parser.tab_indents else ' ' * parser.indent_width
        s = indent * indent_str
        self_is, _ = self.inline_str(parser, indent,
                                     indent * parser.indent_width)
        if self_is[-1].isspace():
            if indent:
                s += self_is[:-len(s)]
            else:
                s += self_is
        else:
            s += self_is + '\n'
        return s

    def inline_str(self, parser, indent=0, col=0):
        if isinstance(self.key, String) and self.key.val in parser.fq_keys:
            self.value.force_quote = True
        s = ''
        nl = 0
        key_is, (nl_key, col_key) = self.key.inline_str(parser, indent, col)
        s += key_is
        nl += nl_key
        col = col_key
        if not s[-1].isspace():
            s += ' '
            col += 1
        op_is, (nl_op, col_op) = self.op.inline_str(parser, indent, col)
        if (col > indent * parser.indent_width and
            col_op > parser.chars_per_line):
            if not s[-2].isspace():
                s = s[:-1]
            op_s = self.op.str(parser, indent)
            s += '\n' + op_s
            nl += 1 + op_s.count('\n')
            col = indent * parser.indent_width
        else:
            if op_is[0] == '\n':
                s = s[:-1]
                col -= 1
            s += op_is
            nl += nl_op
            col = col_op
        if not s[-1].isspace():
            s += ' '
            col += 1
        val_is, (nl_val, col_val) = self.value.inline_str(parser, indent, col)
        if val_is[0] == '\n':
            s = s[:-1]
            col -= 1
        s += val_is
        nl += nl_val
        col = col_val
        return s, (nl, col)


class Obj(Stringifiable):

    def __init__(self, kel, contents=None, ker=None):
        super().__init__()
        if contents is None:
            self.kel = Op('{')
            self.contents = kel
            self.ker = Op('}')
        else:
            self.kel = kel
            self.contents = contents
            self.ker = ker if ker is not None else Op('}')
        self._dictionary = None

    def __len__(self):
        return len(self.contents)

    def __contains__(self, item):
        return item in self.contents or item in self.dictionary

    def __iter__(self):
        return iter(self.contents)

    def __getitem__(self, key):
        return self.dictionary[key]

    def __reversed__(self):
        return reversed(self.contents)

    @property
    def pre_comments(self):
        return self.kel.pre_comments

    @pre_comments.setter
    def pre_comments(self, value):
        self.kel.pre_comments = value

    @property
    def post_comment(self):
        return self.ker.post_comment

    @post_comment.setter
    def post_comment(self, value):
        self.ker.post_comment = value

    @property
    def has_comments(self):
        return (self.kel.has_comments or self.ker.has_comments or
                any(x.has_comments for x in self))

    def get(self, *args, **kwargs):
        return self.dictionary.get(*args, **kwargs)

    # assumes keys occur at most once
    def has_pair(self, key_val, val_val):
        return key_val in self.dictionary and self[key_val].val == val_val

    @property
    def has_pairs(self):
        return not self.contents or isinstance(self.contents[0], Pair)

    @property
    def dictionary(self):
        if self._dictionary is None:
            self._dictionary = {k.val: v for k, v in reversed(self.contents)}
        return self._dictionary

    def str(self, parser, indent=0):
        indent_str = '\t' if parser.tab_indents else ' ' * parser.indent_width
        s = indent * indent_str
        self_is, _ = self.inline_str(parser, indent,
                                     indent * parser.indent_width)
        if self_is[-1].isspace():
            if indent:
                s += self_is[:-len(s)]
            else:
                s += self_is
        else:
            s += self_is + '\n'
        return s

    def might_fit_on_line(self, parser, indent):
        if self.kel.has_comments or self.ker.pre_comments:
            return False
        if self.contents and isinstance(self.contents[0], Pair):
            return (len(self) == 1 and not self.contents[0].has_comments and
                    indent > parser.no_fold_to_depth and
                    not self.contents[0].key.val in parser.no_fold_keys)
        return all(isinstance(x, Commented) and not x.has_comments
                   for x in self)

    def inline_str(self, parser, indent=0, col=0):
        s = ''
        nl = 0
        kel_is, (nl_kel, col_kel) = self.kel.inline_str(parser, indent, col)
        s += kel_is
        nl += nl_kel
        col = col_kel
        if self.might_fit_on_line(parser, indent):
            # attempt one line object
            s_oneline, col_oneline = s, col
            for item in self:
                item_is, (nl_item, col_item) = item.inline_str(parser, indent,
                                                               1 + col_oneline)
                s_oneline += ' ' + item_is
                col_oneline = col_item
                if nl_item > 0 or col_oneline + 2 > parser.chars_per_line:
                    break
            else:
                if self.contents:
                    s_oneline += ' '
                    col_oneline += 1
                ker_is, (nl_ker, col_ker) = self.ker.inline_str(parser, indent,
                                                                col_oneline)
                if nl_ker == 0 or (chars(ker_is.splitlines()[0], parser) <=
                                   parser.chars_per_line):
                    s_oneline += ker_is
                    return s_oneline, (nl_ker, col_ker)
        indent_str = '\t' if parser.tab_indents else ' ' * parser.indent_width
        if self.has_pairs:
            if s[-1].isspace():
                if indent:
                    s = s[:-indent * len(indent_str)]
            else:
                s += '\n'
                nl += 1
            for i, item in enumerate(self):
                item_s = item.str(parser, indent + 1)
                s += item_s
                nl += item_s.count('\n')
                if indent + 1 <= parser.newlines_to_depth:
                    if (i < len(self) - 1 and (isinstance(item.value, Obj) or
                        isinstance(self.contents[i + 1].value, Obj))):
                        s += '\n'
                        nl += 1
            s += indent * indent_str
            col = indent * parser.indent_width
        else:
            sep = '\n' + (indent + 1) * indent_str
            sep_col = chars(sep, parser)
            if s[-1].isspace():
                s += indent_str
            else:
                s += sep
                nl += 1
            col = sep_col
            for item in self:
                if not s[-1].isspace():
                    s += ' '
                    col += 1
                item_is, (nl_item, col_item) = item.inline_str(parser,
                                                               indent + 1, col)
                if (col > (indent + 1) * parser.indent_width and
                    col_item > parser.chars_per_line):
                    if not s[-2].isspace():
                        s = s[:-1]
                    s += sep
                    nl += 1
                    col = sep_col
                    item_is, (nl_item, col_item) = item.inline_str(parser,
                        indent + 1, col)
                s += item_is
                nl += nl_item
                col = col_item
            if not s[-1].isspace():
                s += '\n' + indent * indent_str
                nl += 1
                col = indent * parser.indent_width
        ker_is, (nl_ker, col_ker) = self.ker.inline_str(parser, indent, col)
        s += ker_is
        nl += nl_ker
        col = col_ker
        return s, (nl, col)


class SimpleTokenizer:
    specs = [
        ('Comment', (r'#.*',)),
        ('Space', (r'\s+',)),
        ('Brace', (r'[{}]',)),
        ('Op', (r'[<=>]=?',)),
        ('String', (r'(?s)".*?"',)),
        ('Key', (r'[^\s"#<=>{}]+',))
    ]
    useless = ['Comment', 'Space']
    t = staticmethod(make_tokenizer(specs))

    @classmethod
    def tokenize(cls, string):
        for x in cls.t(string):
            if x.type not in cls.useless:
                if x.type == 'Key':
                    if re.fullmatch(r'-?\d*\.\d*\.\d*', x.value):
                        x.type = 'Date'
                    elif re.fullmatch(r'-?\d+(\.\d+)?', x.value):
                        x.type = 'Number'
                    else:
                        x.type = 'Name'
                yield x


class FullTokenizer(SimpleTokenizer):
    #specs = [
    #    ('Comment', (r'#(.*\S)?',)),
    #    ('Space', (r'[ \t]+',)),
    #    ('NL', (r'\r?\n',)),
    #    ('Op', (r'[={}]',)),
    #    ('String', (r'".*?"',)),
    #    ('Key', (r'[^\s"#={}]+',))
    #]
    specs = [
        ('comment', (r'#(.*\S)?',)),
        ('whitespace', (r'[ \t]+',)),
        ('newline', (r'\r?\n',)),
        ('brace', (r'[{}]',)),
        ('op', (r'[<=>]=?',)),
        ('date', (r'-?\d*\.\d*\.\d*',)),
        ('number', (r'-?\d+(\.\d+)?(?!\w)',)),
        ('quoted_string', (r'(?s)".*?"',)),
        ('unquoted_string', (r'[^\s"#<=>{}]+',))
    ]
    useless = ['whitespace']
    t = staticmethod(make_tokenizer(specs))


class SimpleParser:
    tokenizer = SimpleTokenizer
    repos = {}

    def __init__(self, *moddirs, strict=True):
        self.moddirs = list(moddirs)
        self.basedir = vanilladir
        self.strict = strict
        self.cache_hits = 0
        self.cache_misses = 0
        self.parse_tree_cache = {}
        self.memcache_default = False
        self.diskcache_default = True
        self.tab_indents = True
        self.indent_width = 8 # minimum 2
        self.chars_per_line = 125
        self.fq_keys = []
        self.no_fold_keys = []
        self.no_fold_to_depth = -1
        self.newlines_to_depth = -1
        self.crlf = True
        self.encoding = 'cp1252'
        self.ignore_cache = False
        self.vanilla_is_repo = True
        self.cachedir = cachedir / self.__class__.__name__
        self.cachedir.mkdir(parents=True, exist_ok=True)
        self.setup_parser()

    def __del__(self):
        if not self.ignore_cache:
            print('{}: {} hits, {} misses'.format(
                  self.__class__.__name__, self.cache_hits, self.cache_misses),
                  file=sys.stderr)

    def setup_parser(self):
        unarg = lambda f: lambda x: f(*x)
        tokval = lambda x: x.value
        toktype = lambda t: some(lambda x: x.type == t) >> tokval
        kel = a(Token('Brace', '{')) >> tokval >> Op
        ker = a(Token('Brace', '}')) >> tokval >> Op
        op = toktype('Op') >> Op
        number = toktype('Number') >> Number
        date = toktype('Date') >> Date
        name = toktype('Name') >> String
        string = toktype('String') >> (lambda s: s[1:-1]) >> String
        key = date | number | name | string
        pair = forward_decl()
        if self.strict:
            obj = kel + many(pair | string | key) + ker >> unarg(Obj)
        else:
            obj = (kel + many(pair | string | key) +
                   (ker | skip(finished)) >> unarg(Obj))
        pair.define(key + op + (obj | string | key) >> unarg(Pair))
        self.toplevel = many(pair) + skip(finished) >> TopLevel

    def flush(self, path=None):
        if path is None:
            self.parse_tree_cache = {}
        elif path in self.parse_tree_cache:
            del self.parse_tree_cache[path]

    def invalidate_repo_cache(self, bad_path=None):
        if bad_path is None:
            self.repos.clear()
        else:
            bad_repo_path = None
            for repo_path in self.repos:
                if repo_path == bad_path or repo_path in bad_path.parents:
                    bad_repo_path = repo_path
            if bad_repo_path != None:
                del self.repos[bad_repo_path]

    def get_cachepath(self, path, encoding):
        m = hashlib.md5()
        m.update(encoding.encode())
        m.update(bytes(path))
        cachedir = self.cachedir
        name = m.hexdigest()
        if not self.vanilla_is_repo and vanilladir in path.parents:
            return self.cachedir / 'vanilla' / name, False
        for repo_path, (latest_commit, dirty_paths) in self.repos.items():
            if repo_path in path.parents:
                break
        else:
            repo_init_start = time.time()
            if git_present:
                try:
                    repo = git.Repo(str(path.parent), odbt=git.GitCmdObjectDB,
                                    search_parent_directories=True)
                    no_git = False
                except git.InvalidGitRepositoryError:
                    no_git = True
            else:
                no_git = True
            if no_git:
                if self.vanilla_is_repo and vanilladir in path.parents:
                    self.vanilla_is_repo = False
                    return self.cachedir / 'vanilla' / name, False
                return self.cachedir / name, False
            repo_path = pathlib.Path(repo.working_tree_dir)
            tracked_files = set(repo.git.ls_files(z=True).split('\x00')[:-1])
            latest_commit = {}
            log_output = repo.git.log('.', m=True, pretty='format:%h', z=True,
                                      name_only=True)
            log_iter = iter(log_output.split('\x00'))
            for entry in log_iter:
                try:
                    commit, file_str = entry.split('\n', maxsplit=1)
                except ValueError:
                    continue
                while file_str:
                    try:
                        tracked_files.remove(file_str)
                        latest_commit[file_str] = commit
                    except KeyError:
                        pass
                    file_str = next(log_iter)
                if not tracked_files:
                    break
            dirty_paths = []
            status_output = repo.git.status(z=True)
            status_iter = iter(status_output.split('\x00')[:-1])
            for entry in status_iter:
                dirty_paths.append(pathlib.Path(entry[3:]))
                if entry[0] == 'R':
                    next(status_iter)
            self.repos[repo_path] = latest_commit, dirty_paths
            print('Repo {} processed in {:g} s'.format(
                  repo_path.name, time.time() - repo_init_start),
                  file=sys.stderr)
        repo_cachedir = self.cachedir / repo_path.name
        path = path.relative_to(repo_path)
        if not any(p == path or p in path.parents for p in dirty_paths):
            return repo_cachedir / latest_commit[str(path)] / name, True
        return repo_cachedir / name, False

    def files(self, glob, reverse=False):
        yield from files(glob, self.moddirs, basedir=self.basedir,
                         reverse=reverse)

    def file(self, *args, **kwargs):
        return next(self.files(*args, **kwargs))

    def merge_parse(self, glob, basedir=None, moddirs=None, **kwargs):
        """parse files, merge all top level items into one dictionary and return the items of that dictionary"""
        dictionary = {}
        for filename, tree in self.parse_files(glob, basedir, moddirs, **kwargs):
            dictionary.update(tree.dictionary)

        return dictionary.items()

    def parse_files(self, glob, basedir=None, moddirs=None, **kwargs):
        if moddirs is None:
            moddirs = self.moddirs
        if basedir is None:
            basedir = self.basedir
        for path in files(glob, moddirs, basedir=basedir):
            if path.is_file():
                yield path.resolve(), self.parse_file(path, **kwargs)

    def parse_file(self, path, encoding=None, errors='replace',
                   memcache=None, diskcache=None):
        try:
            path = path.resolve()
        except AttributeError:
            return self.parse_file(self.file(path),
                                   encoding, errors, memcache, diskcache)
        if memcache is None:
            memcache = self.memcache_default
        if diskcache is None:
            diskcache = self.diskcache_default
        if encoding is None:
            encoding = self.encoding
        ignore_cache = (self.ignore_cache or errors != 'replace')
        if not ignore_cache:
            if path in self.parse_tree_cache:
                return self.parse_tree_cache[path]
            cachepath, is_indexed = self.get_cachepath(path, encoding)
            try:
                if cachepath.exists() and (is_indexed or
                                           (os.path.getmtime(str(cachepath)) >=
                                            os.path.getmtime(str(path)))):
                    with cachepath.open('rb') as f:
                        tree = pickle.load(f)
                        if tree.version == VERSION:
                            if memcache:
                                self.parse_tree_cache[path] = tree
                            self.cache_hits += 1
                            return tree
            except AttributeError:
                pass
            except (pickle.PickleError, EOFError, ImportError, IndexError):
                print('Error retrieving cache for {}'.format(path),
                      file=sys.stderr)
                traceback.print_exc()
                pass
            self.cache_misses += 1
        with path.open(encoding=encoding, errors=errors) as f:
            try:
                tree = self.parse(f.read())
                if not ignore_cache:
                    if diskcache:
                        cachepath.parent.mkdir(parents=True, exist_ok=True)
                        # possible todo: put this i/o in another thread
                        with cachepath.open('wb') as f:
                            tree.version = VERSION
                            pickle.dump(tree, f)
                    if memcache:
                        self.parse_tree_cache[path] = tree
                return tree
            except:
                print(path, file=sys.stderr)
                raise

    def parse(self, string):
        tokens = list(self.tokenizer.tokenize(string))
        tree = self.toplevel.parse(tokens)
        return tree

    def write(self, tree, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open('w', encoding=self.encoding,
                           newline=('\r\n' if self.crlf else '\n')) as f:
                f.write(tree.str(self))
        except:
            print(path)
            raise

class FullParser(SimpleParser):
    tokenizer = FullTokenizer

    def setup_parser(self):
        unarg = lambda f: lambda x: f(*x)
        unquote = lambda s: s[1:-1]
        tokval = lambda x: x.value
        toktype = lambda t: some(lambda x: x.type == t) >> tokval
        nl = skip(many(toktype('newline')))
        end = nl + skip(finished)
        comment = toktype('comment')
        commented = lambda x: (many(nl + comment) + nl + x + maybe(comment))
        unquoted_string = (commented(toktype('unquoted_string')) >>
                           unarg(String))
        quoted_string = (commented(toktype('quoted_string') >> unquote) >>
                         unarg(String))
        kel = commented(a(Token('brace', '{')) >> tokval) >> unarg(Op)
        ker = commented(a(Token('brace', '}')) >> tokval) >> unarg(Op)
        op = commented(toktype('op')) >> unarg(Op)
        number = commented(toktype('number')) >> unarg(Number)
        date = commented(toktype('date')) >> unarg(Date)
        key = unquoted_string | date | number | quoted_string
        value = forward_decl()
        pair = key + op + value >> unarg(Pair)
        if self.strict:
            obj = kel + many(pair | value) + ker >> unarg(Obj)
        else:
            obj = kel + many(pair | value) + (ker | end) >> unarg(Obj)
        value.define(obj | key | quoted_string)
        self.toplevel = (many(pair) + many(nl + comment) + end >>
                         unarg(TopLevel))
