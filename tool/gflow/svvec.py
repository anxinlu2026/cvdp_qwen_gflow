"""svvec: SystemVerilog vectors with unknown bits (X) for Python models of RTL.

A vector is a V: a width, the bits, and which bits are known. Every bit carries its own X.
Use only the functions of this file for selects, concatenations and operations: they follow
the simulator bit by bit and raise an error when a width or a range does not fit.

Making values
    V(width, value)            all bits known (value must fit the width)
    X(width)                   all bits unknown
    from_bin("10x1")           from a text of 0, 1, x (underscores allowed); width = number of digits
    NW                         marker "not written yet" for a combinational variable; every function raises on it

Reading values
    v.w                        width
    v.is_known()               True when no bit is X
    v.int()                    the integer; raises XValue when a bit is X
    v.int_or_none()            the integer, or None when a bit is X
    v.bin()  v.hex()           text as the simulator prints it (%b, %h): x = unknown, X = hex digit partly unknown
    a.same(b)                  True when width, bits and X bits are identical (for tests; not an RTL operation)

Selects (line = source line number, any text or number; the selected range is recorded under it)
    sel(v, ":", m, l, line)    v[m:l]
    sel(v, "+:", b, w, line)   v[b +: w]   bits b+w-1 down to b
    sel(v, "-:", b, w, line)   v[b -: w]   bits b down to b-w+1
    bit(v, i, line)            v[i]
        The base b or index i may be an int or a V. A range that leaves the vector raises RangeError.
        When the reading of the line was checked and the source really does this, pass outside="x":
        the bits outside the vector read X. A base or index with an X bit gives X for every bit.
    put(v, op, b, w, value, line)   assignment to a part of a vector: v[b -: w] = value (op ":", "+:", "-:" as in sel; bit: w = 1 with "+:").
                               Returns the new vector (v itself is not changed); the other bits keep their value. value must have the width
                               of the part (use fit() where the source's widths differ). A range that leaves the vector raises RangeError;
                               with outside="x" the bits outside are dropped; a base with an X bit writes nothing.
    ranges(line)               the list of (high, low) recorded for the line
    aget(arr, i, line)         element i of a list of V; an X or outside index reads X
    aset(arr, i, value, line)  write element i; an X or outside index writes nothing

Building
    cat([a, b, c], width, line)   {a, b, c}: a is the most significant part; raises WidthError when the widths do not add up to width
    rep(n, v)                     {n{v}}
    ext(v, width)                 zero extension to a wider width
    sext(v, width)                sign extension
    fit(v, width, line)           assignment to a target of this width: extends with zeros or cuts the upper bits, as the source's assignment does

Operations. An operand may be a Python int: it is a known constant of the other operand's width.
Two V operands of different widths: the narrower is extended with zeros (the source does the same).
    band(a, b)  bor(a, b)  bxor(a, b)  bnot(a)     bitwise; X per bit (0 & X = 0, 1 | X = 1)
    add(a, b, width=None)  sub  mul  div  mod  neg(a, width=None)
                                                   the result has `width` bits (default: the wider operand) and wraps;
                                                   any X bit in an operand makes every result bit X; division by 0 gives X
    shl(a, n)  shr(a, n)  sra(a, n)                shift by n (int or V); width of a; an X bit in n makes every bit X
    eq(a, b)  ne(a, b)                             1 bit: X when the known bits do not decide
    lt(a, b)  le  gt  ge   (signed=False)          1 bit: X when any bit is X
    lnot(a)  land(a, b)  lor(a, b)                 logical !, &&, ||: 1 bit, may be X
    rand(a)  ror(a)  rxor(a)                       reduction &, |, ^
    mux(c, a, b)                                   c ? a : b; when c is X: a bit is known only where a and b have the same known bit

Control
    true(c)                    for `if (c)`: True only when c is known to be not zero; X takes the else branch
    match(s, item)             for `case (s)`: True when s has no X bit and equals item (int or V); with an X bit no item matches (default)
    match_wild(s, "1??0", kind)   for casez (kind="z") and casex (kind="x"); ? or z in the pattern is a wildcard
"""

__all__ = ["V", "X", "NW", "from_bin", "sel", "bit", "put", "ranges", "RANGES", "aget", "aset", "cat", "rep", "ext", "sext", "fit",
           "band", "bor", "bxor", "bnot", "add", "sub", "mul", "div", "mod", "neg", "shl", "shr", "sra",
           "eq", "ne", "lt", "le", "gt", "ge", "lnot", "land", "lor", "rand", "ror", "rxor", "mux",
           "true", "match", "match_wild", "XValue", "RangeError", "WidthError", "NotWritten"]


class XValue(Exception):
    """An integer was asked of a vector that has an X bit."""


class RangeError(Exception):
    """A select leaves the vector."""


class WidthError(Exception):
    """Widths do not fit."""


class NotWritten(Exception):
    """A combinational variable was read before it was written in this pass."""


class _NotWritten:
    def __repr__(self):
        return "NW"


NW = _NotWritten()
RANGES = {}


def _mask(w):
    return (1 << w) - 1


class V:
    """A vector of w bits: v holds the known bits (0 where unknown), k has a 1 for every known bit."""
    __slots__ = ("w", "v", "k")

    def __init__(self, w, v=0, k=None):
        if not isinstance(w, int) or isinstance(w, bool) or w < 1:
            raise WidthError(f"width must be a positive int, got {w!r}")
        if isinstance(v, V) or v is NW or v is None or not isinstance(v, int):
            raise TypeError(f"V(width, value): value must be an int, got {v!r}")
        m = _mask(w)
        if k is None:
            k = m
        if v < 0 or v > m:
            raise WidthError(f"value {v:#x} does not fit {w} bits")
        if k < 0 or k > m:
            raise WidthError(f"known mask {k:#x} does not fit {w} bits")
        object.__setattr__(self, "w", w)
        object.__setattr__(self, "k", k)
        object.__setattr__(self, "v", v & k)

    def __setattr__(self, *a):
        raise AttributeError("a V is not changed; make a new one")

    def is_known(self):
        return self.k == _mask(self.w)

    def int(self):
        if not self.is_known():
            raise XValue(f"the vector has X bits: {self.bin()}")
        return self.v

    def int_or_none(self):
        return self.v if self.is_known() else None

    def bin(self):
        return "".join(("1" if (self.v >> i) & 1 else "0") if (self.k >> i) & 1 else "x" for i in range(self.w - 1, -1, -1))

    def hex(self):
        out = []
        for d in range((self.w + 3) // 4 - 1, -1, -1):
            n = min(4, self.w - 4 * d)
            kk = (self.k >> (4 * d)) & _mask(n)
            out.append(format((self.v >> (4 * d)) & 15, "x") if kk == _mask(n) else "x" if kk == 0 else "X")
        return "".join(out)

    def same(self, o):
        return isinstance(o, V) and (self.w, self.v, self.k) == (o.w, o.v, o.k)

    def __repr__(self):
        return f"V({self.w}, {self.w}'b{self.bin()})" if not self.is_known() else f"V({self.w}, {self.v:#x})"

    def __bool__(self):
        raise TypeError("a V has no truth value: use true(c) for an if, match() for a case, same() to compare in a test")

    def __eq__(self, o):
        raise TypeError("use eq(a, b) for the RTL's ==, or a.same(b) in a test")

    __hash__ = None


def X(w):
    return V(w, 0, 0)


def from_bin(text):
    t = text.replace("_", "")
    if not t or any(c not in "01xX" for c in t):
        raise ValueError(f"from_bin: only 0, 1, x: {text!r}")
    return V(len(t), int("".join("1" if c == "1" else "0" for c in t), 2), int("".join("0" if c in "xX" else "1" for c in t), 2))


def _v(a, w=None, what="operand"):
    """An operand as a V. An int becomes a known constant of width w."""
    if a is NW:
        raise NotWritten(f"{what} is read before it is written in this pass")
    if isinstance(a, V):
        return a
    if isinstance(a, bool) or not isinstance(a, int):
        raise TypeError(f"{what} must be a V or an int, got {a!r}")
    if w is None:
        raise WidthError(f"{what} is an int ({a}) and no width is known for it: make it V(width, {a})")
    if a < 0 or a > _mask(w):
        raise WidthError(f"constant {a} does not fit the {w} bits of the other operand")
    return V(w, a)


def _pair(a, b, width=None):
    if not isinstance(a, V) and not isinstance(b, V):
        if a is NW or b is NW:
            raise NotWritten("an operand is read before it is written in this pass")
        if width is None:
            raise WidthError("both operands are ints: make one a V(width, value)")
        a = _v(a, width)
    a = _v(a, b.w if isinstance(b, V) else None)
    b = _v(b, a.w)
    w = max(a.w, b.w) if width is None else width
    if w < max(a.w, b.w):
        raise WidthError(f"the result width {w} is smaller than an operand ({a.w}, {b.w}); operate first, then fit() to the target")
    return ext(a, w), ext(b, w), w


def _index(i, what):
    """An index or base as an int, or None when it has an X bit."""
    if i is NW:
        raise NotWritten(f"{what} is read before it is written in this pass")
    if isinstance(i, V):
        return i.int_or_none()
    if isinstance(i, bool) or not isinstance(i, int):
        raise TypeError(f"{what} must be an int or a V, got {i!r}")
    return i


def _take(v, hi, lo, outside, line):
    w = hi - lo + 1
    if w < 1:
        raise RangeError(f"line {line}: the select [{hi}:{lo}] is empty or reversed")
    RANGES.setdefault(line, []).append((hi, lo))
    if hi >= v.w or lo < 0:
        if outside != "x":
            raise RangeError(f"line {line}: the select [{hi}:{lo}] leaves the {v.w}-bit vector")
    if lo >= 0:
        val, kn = (v.v >> lo) & _mask(w), (v.k >> lo) & _mask(w)
    else:
        val, kn = (v.v << -lo) & _mask(w), (v.k << -lo) & _mask(w)
    return V(w, val, kn)


def sel(v, op, base, n, line, outside="raise"):
    v = _v(v, what="the vector")
    if op == ":":
        hi, lo = _index(base, "the high index"), _index(n, "the low index")
        if hi is None or lo is None:
            raise XValue(f"line {line}: the bounds of [m:l] must be constants")
        return _take(v, hi, lo, outside, line)
    if op not in ("+:", "-:"):
        raise ValueError(f"line {line}: select operator must be ':', '+:' or '-:', got {op!r}")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise WidthError(f"line {line}: the width of a {op} select must be a positive int constant")
    b = _index(base, "the base")
    if b is None:
        RANGES.setdefault(line, []).append(("x", "x"))
        return X(n)
    return _take(v, b + n - 1, b, outside, line) if op == "+:" else _take(v, b, b - n + 1, outside, line)


def bit(v, i, line, outside="raise"):
    return sel(v, "+:", i, 1, line, outside)


def put(v, op, base, n, value, line, outside="raise"):
    v = _v(v, what="the vector")
    if op == ":":
        hi, lo = _index(base, "the high index"), _index(n, "the low index")
        if hi is None or lo is None:
            raise XValue(f"line {line}: the bounds of [m:l] must be constants")
    elif op in ("+:", "-:"):
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise WidthError(f"line {line}: the width of a {op} select must be a positive int constant")
        b = _index(base, "the base")
        if b is None:
            _v(value, n, "the value")
            RANGES.setdefault(line, []).append(("x", "x"))
            return v
        hi, lo = (b + n - 1, b) if op == "+:" else (b, b - n + 1)
    else:
        raise ValueError(f"line {line}: select operator must be ':', '+:' or '-:', got {op!r}")
    w = hi - lo + 1
    if w < 1:
        raise RangeError(f"line {line}: the select [{hi}:{lo}] is empty or reversed")
    value = _v(value, w, "the value")
    if value.w != w:
        raise WidthError(f"line {line}: the value has {value.w} bits, the part [{hi}:{lo}] has {w}")
    RANGES.setdefault(line, []).append((hi, lo))
    if (hi >= v.w or lo < 0) and outside != "x":
        raise RangeError(f"line {line}: the select [{hi}:{lo}] leaves the {v.w}-bit vector")
    m = _mask(v.w)
    part = (_mask(w) << lo if lo >= 0 else _mask(w) >> -lo) & m
    nv = (value.v << lo if lo >= 0 else value.v >> -lo) & m
    nk = (value.k << lo if lo >= 0 else value.k >> -lo) & m
    return V(v.w, (v.v & ~part) | (nv & part), (v.k & ~part) | (nk & part))


def ranges(line):
    return list(RANGES.get(line, []))


def aget(arr, i, line):
    if arr is NW or any(e is NW for e in arr):
        raise NotWritten(f"line {line}: the array is read before it is written in this pass")
    n = _index(i, "the index")
    RANGES.setdefault(line, []).append(("element", n if n is not None else "x"))
    if n is None or n < 0 or n >= len(arr):
        return X(arr[0].w)
    return arr[n]


def aset(arr, i, value, line):
    n = _index(i, "the index")
    value = _v(value, arr[0].w if isinstance(arr[0], V) else None, "the value")
    RANGES.setdefault(line, []).append(("element", n if n is not None else "x"))
    if n is None or n < 0 or n >= len(arr):
        return
    arr[n] = value


def cat(parts, width, line):
    ps = [_v(p, what="a part of the concatenation") for p in parts]
    total = sum(p.w for p in ps)
    if total != width:
        raise WidthError(f"line {line}: the parts are {' + '.join(str(p.w) for p in ps)} = {total} bits, the target is {width} bits")
    val = kn = 0
    for p in ps:
        val, kn = (val << p.w) | p.v, (kn << p.w) | p.k
    return V(width, val, kn)


def rep(n, v):
    v = _v(v, what="the repeated part")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise WidthError("the repeat count must be a positive int constant")
    val = kn = 0
    for _ in range(n):
        val, kn = (val << v.w) | v.v, (kn << v.w) | v.k
    return V(n * v.w, val, kn)


def ext(v, width):
    v = _v(v, what="the vector")
    if width < v.w:
        raise WidthError(f"ext: {width} bits is narrower than the vector ({v.w}); use fit() where the source assigns to a narrower target")
    return v if width == v.w else V(width, v.v, v.k | (_mask(width) & ~_mask(v.w)))


def sext(v, width):
    v = _v(v, what="the vector")
    if width < v.w:
        raise WidthError(f"sext: {width} bits is narrower than the vector ({v.w})")
    if width == v.w:
        return v
    up = _mask(width) & ~_mask(v.w)
    sk, sv = (v.k >> (v.w - 1)) & 1, (v.v >> (v.w - 1)) & 1
    return V(width, v.v | (up if sv else 0), v.k | (up if sk else 0))


def fit(v, width, line=None):
    v = _v(v, what="the value")
    return ext(v, width) if width >= v.w else V(width, v.v & _mask(width), v.k & _mask(width))


def band(a, b):
    a, b, w = _pair(a, b)
    k = (a.k & b.k) | (a.k & ~a.v) | (b.k & ~b.v)
    return V(w, a.v & b.v, k & _mask(w))


def bor(a, b):
    a, b, w = _pair(a, b)
    k = (a.k & b.k) | (a.k & a.v) | (b.k & b.v)
    return V(w, (a.v | b.v) & k, k)


def bxor(a, b):
    a, b, w = _pair(a, b)
    k = a.k & b.k
    return V(w, (a.v ^ b.v) & k, k)


def bnot(a):
    a = _v(a)
    return V(a.w, ~a.v & a.k & _mask(a.w), a.k)


def _arith(a, b, width, f):
    a, b, w = _pair(a, b, width)
    if not (a.is_known() and b.is_known()):
        return X(w)
    r = f(a.v, b.v)
    return X(w) if r is None else V(w, r & _mask(w))


def add(a, b, width=None):
    return _arith(a, b, width, lambda x, y: x + y)


def sub(a, b, width=None):
    return _arith(a, b, width, lambda x, y: x - y)


def mul(a, b, width=None):
    return _arith(a, b, width, lambda x, y: x * y)


def div(a, b, width=None):
    return _arith(a, b, width, lambda x, y: None if y == 0 else x // y)


def mod(a, b, width=None):
    return _arith(a, b, width, lambda x, y: None if y == 0 else x % y)


def neg(a, width=None):
    a = _v(a)
    return sub(V(width or a.w, 0), a, width)


def _amount(n):
    if n is NW:
        raise NotWritten("the shift amount is read before it is written in this pass")
    if isinstance(n, V):
        return n.int_or_none()
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise TypeError(f"the shift amount must be an int >= 0 or a V, got {n!r}")
    return n


def shl(a, n):
    a, n = _v(a), _amount(n)
    if n is None:
        return X(a.w)
    m = _mask(a.w)
    return V(a.w, (a.v << n) & m, ((a.k << n) | _mask(n)) & m) if n else a


def shr(a, n):
    a, n = _v(a), _amount(n)
    if n is None:
        return X(a.w)
    m = _mask(a.w)
    return V(a.w, a.v >> n, ((a.k >> n) | (m & ~(m >> n))) & m) if n else a


def sra(a, n):
    a, n = _v(a), _amount(n)
    if n is None:
        return X(a.w)
    n = min(n, a.w)
    return fit(shr(sext(a, a.w + n), n), a.w)


def eq(a, b):
    a, b, w = _pair(a, b)
    both = a.k & b.k
    if (a.v ^ b.v) & both:
        return V(1, 0)
    return V(1, 1) if both == _mask(w) else X(1)


def ne(a, b):
    return lnot(eq(a, b))


def _rel(a, b, signed, f):
    a, b, w = _pair(a, b)
    if not (a.is_known() and b.is_known()):
        return X(1)
    x, y = a.v, b.v
    if signed:
        x, y = (x - (1 << w) if x >> (w - 1) else x), (y - (1 << w) if y >> (w - 1) else y)
    return V(1, int(f(x, y)))


def lt(a, b, signed=False):
    return _rel(a, b, signed, lambda x, y: x < y)


def le(a, b, signed=False):
    return _rel(a, b, signed, lambda x, y: x <= y)


def gt(a, b, signed=False):
    return _rel(a, b, signed, lambda x, y: x > y)


def ge(a, b, signed=False):
    return _rel(a, b, signed, lambda x, y: x >= y)


def _tv(a):
    """Truth of a vector: 1 (a known 1 bit), 0 (all bits known 0) or None."""
    a = _v(a, 1)
    if a.v:
        return 1
    return 0 if a.is_known() else None


def _t(x):
    return X(1) if x is None else V(1, x)


def lnot(a):
    t = _tv(a)
    return _t(None if t is None else 1 - t)


def land(a, b):
    x, y = _tv(a), _tv(b)
    return _t(0 if x == 0 or y == 0 else 1 if x == 1 and y == 1 else None)


def lor(a, b):
    x, y = _tv(a), _tv(b)
    return _t(1 if x == 1 or y == 1 else 0 if x == 0 and y == 0 else None)


def rand(a):
    a = _v(a)
    if a.k & ~a.v & _mask(a.w):
        return V(1, 0)
    return V(1, 1) if a.is_known() else X(1)


def ror(a):
    return _t(_tv(_v(a)))


def rxor(a):
    a = _v(a)
    return V(1, bin(a.v).count("1") & 1) if a.is_known() else X(1)


def mux(c, a, b):
    a, b, w = _pair(a, b)
    t = _tv(c)
    if t is not None:
        return a if t else b
    k = a.k & b.k & ~(a.v ^ b.v) & _mask(w)
    return V(w, a.v & k, k)


def true(c):
    return _tv(c) == 1


def match(s, item):
    s = _v(s, what="the selector")
    item = _v(item, s.w, "the case item")
    s, item, w = _pair(s, item)
    return s.is_known() and item.is_known() and s.v == item.v


def match_wild(s, pattern, kind):
    s = _v(s, what="the selector")
    if kind not in ("z", "x"):
        raise ValueError("kind is 'z' (casez) or 'x' (casex)")
    p = pattern.replace("_", "")
    if len(p) != s.w:
        raise WidthError(f"the pattern {pattern!r} has {len(p)} digits, the selector {s.w} bits")
    for i, c in enumerate(p):
        pos = s.w - 1 - i
        known, val = (s.k >> pos) & 1, (s.v >> pos) & 1
        if c in "?zZ":
            continue
        if c in "xX":
            if kind == "x" or not known:
                continue
            return False
        if c not in "01":
            raise ValueError(f"pattern digit {c!r}")
        if not known:
            if kind == "x":
                continue
            return False
        if val != int(c):
            return False
    return True
