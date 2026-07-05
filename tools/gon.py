"""Minimal parser for GON (Glaiel Object Notation) as used by Mewgenics.

Format notes handled here:
  - key/value pairs separated by whitespace; commas are whitespace
  - objects  Key { ... }      arrays  key [ a b c ]
  - quoted "strings" (loc keys / literals), bare words, numbers, true/false
  - comments: // to EOL, /* block */, and # to EOL
  - directive: #include "relative/path.gon"  (inlined)
  - numeric keys allowed (e.g. spawn ids)
"""
import os
import re

_INCLUDE = re.compile(r'#include\s+"([^"]+)"')


def load_text(path, _seen=None):
    """Read a .gon file, recursively inlining #include directives."""
    _seen = _seen or set()
    ap = os.path.abspath(path)
    if ap in _seen:
        return ""            # guard against include cycles
    _seen.add(ap)
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    base = os.path.dirname(path)

    def repl(m):
        inc = os.path.join(base, m.group(1))
        return load_text(inc, _seen) if os.path.exists(inc) else ""

    return _INCLUDE.sub(repl, text)


# ---- tokenizer ---------------------------------------------------------
# token = (kind, value); kind in { '{', '}', '[', ']', 'str', 'word' }
_STRUCT = set("{}[]")
_WS = set(" \t\r\n,")


def tokenize(text):
    toks = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in _WS:
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            i = text.find("\n", i)
            if i < 0:
                break
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == "#":
            i = text.find("\n", i)
            if i < 0:
                break
        elif c in _STRUCT:
            toks.append((c, c))
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n:
                ch = text[j]
                if ch == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                    continue
                if ch == '"':
                    break
                buf.append(ch)
                j += 1
            toks.append(("str", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in _WS and text[j] not in _STRUCT \
                    and text[j] != '"' and text[j] != "#" \
                    and not (text[j] == "/" and j + 1 < n and text[j + 1] in "/*"):
                j += 1
            toks.append(("word", text[i:j]))
            i = j
    return toks


def _coerce(word):
    if word == "true":
        return True
    if word == "false":
        return False
    try:
        return int(word)
    except ValueError:
        pass
    try:
        return float(word)
    except ValueError:
        return word


class _P:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def value(self):
        kind, val = self.next()
        if kind == "{":
            return self.obj()
        if kind == "[":
            return self.arr()
        if kind == "str":
            return val                 # quoted -> always string
        return _coerce(val)            # bare word/number/bool

    def arr(self):
        out = []
        while self.peek()[0] not in ("]", None):
            out.append(self.value())
        if self.peek()[0] == "]":
            self.next()
        return out

    def obj(self, top=False):
        out = {}
        dup = set()                    # keys seen more than once
        while True:
            kind, key = self.peek()
            if kind is None:
                break
            if kind == "}":
                self.next()
                break
            self.next()                # consume key token
            key = str(key)
            val = self.value()
            if key in out:             # duplicate key -> collect into list
                if key not in dup:
                    out[key] = [out[key]]
                    dup.add(key)
                out[key].append(val)
            else:
                out[key] = val
        return out


def parse(text):
    return _P(tokenize(text)).obj(top=True)


def load(path):
    return parse(load_text(path))
