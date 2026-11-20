"""listdiff: compare two lists of lines as sequences (aligned, not position by position).

Each file holds one item per line (for example one operation with its parameter). Empty lines and
lines that start with # are ignored; spaces at the ends and runs of spaces are not significant.
The two lists are aligned on their longest common parts, so one extra line does not shift every
line after it. The report names only: lines that are extra in the first list, lines that are
missing in the first list, and lines that differ at the same place.

usage: python3 /code/lib/listdiff.py FIRST SECOND [--names design spec] [--full]
    --names A B   the words used for the two lists in the report (default: first second)
    --full        also print the two lists side by side, aligned
In Python: from listdiff import compare; compare(list_a, list_b) -> list of (kind, a_lines, b_lines)
    kind is "same", "extra" (only in the first), "missing" (only in the second) or "differ";
    a_lines and b_lines are lists of (line number from 1, text).
"""
import argparse
import difflib
import sys


def read(path):
    out = []
    for n, line in enumerate(open(path), 1):
        t = " ".join(line.split())
        if t and not t.startswith("#"):
            out.append((n, t))
    return out


def compare(a, b):
    """a, b: lists of texts or of (number, text). Returns the aligned blocks."""
    a = [x if isinstance(x, tuple) else (i, " ".join(str(x).split())) for i, x in enumerate(a, 1)]
    b = [x if isinstance(x, tuple) else (i, " ".join(str(x).split())) for i, x in enumerate(b, 1)]
    sm = difflib.SequenceMatcher(None, [t for _, t in a], [t for _, t in b], autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append(("same", a[i1:i2], b[j1:j2]))
        elif tag == "delete":
            out.append(("extra", a[i1:i2], []))
        elif tag == "insert":
            out.append(("missing", [], b[j1:j2]))
        else:
            n = min(i2 - i1, j2 - j1)
            out.append(("differ", a[i1:i1 + n], b[j1:j1 + n]))
            if i2 - i1 > n:
                out.append(("extra", a[i1 + n:i2], []))
            if j2 - j1 > n:
                out.append(("missing", [], b[j1 + n:j2]))
    return out


def report(blocks, na="first", nb="second", full=False):
    lines = []
    count = {"same": 0, "extra": 0, "missing": 0, "differ": 0}
    prev = None
    all_a = [(n, t) for _, xa, _ in blocks for n, t in xa]
    all_b = [(n, t) for _, _, xb in blocks for n, t in xb]

    def elsewhere(texts, other, word, own):
        at = sorted({n for n, t in other if t in texts and n not in own})
        return [f"    (lines with these texts are in {word} at another place: {word} line{'s' if len(at) > 1 else ''} {', '.join(map(str, at[:12]))}{' ...' if len(at) > 12 else ''}; the alignment did not match them here)"] if at else []
    for kind, xa, xb in blocks:
        count[kind] += max(len(xa), len(xb))
        if kind == "same":
            prev = (xa[-1], xb[-1])
            continue
        where = f"after {na} line {prev[0][0]} / {nb} line {prev[1][0]} ({prev[0][1]})" if prev else "at the start"
        if kind == "extra":
            lines.append(f"EXTRA in {na} ({len(xa)} line{'s' if len(xa) > 1 else ''}), {where}:")
            lines += [f"    {na} {n}: {t}" for n, t in xa]
            lines += elsewhere({t for _, t in xa}, all_b, nb, set())
        elif kind == "missing":
            lines.append(f"MISSING in {na} ({len(xb)} line{'s' if len(xb) > 1 else ''}), {where}:")
            lines += [f"    {nb} {n}: {t}" for n, t in xb]
            lines += elsewhere({t for _, t in xb}, all_a, na, set())
        else:
            lines.append(f"DIFFERENT ({len(xa)} line{'s' if len(xa) > 1 else ''}), {where}:")
            lines += [f"    {na} {n}: {t}    |    {nb} {m}: {u}" for (n, t), (m, u) in zip(xa, xb)]
    head = (f"{na}: {sum(len(xa) for _, xa, _ in blocks)} lines, {nb}: {sum(len(xb) for _, _, xb in blocks)} lines. "
            f"Aligned: {count['same']} the same, {count['extra']} extra in {na}, {count['missing']} missing in {na}, "
            f"{count['differ']} different.")
    lines.insert(0, head)
    if not (count["extra"] or count["missing"] or count["differ"]):
        lines.append("The two lists are the same.")
    if full:
        w = max([len(t) for _, xa, _ in blocks for _, t in xa] + [len(na)]) + 6
        lines.append("")
        lines.append(f"{na:<{w}} | {nb}")
        for kind, xa, xb in blocks:
            for i in range(max(len(xa), len(xb))):
                l = f"{xa[i][0]:>3} {xa[i][1]}" if i < len(xa) else ""
                r = f"{xb[i][0]:>3} {xb[i][1]}" if i < len(xb) else ""
                mark = {"same": " ", "extra": "+", "missing": "-", "differ": "!"}[kind]
                lines.append(f"{l:<{w}} {mark} {r}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="compare two lists of lines as sequences")
    ap.add_argument("first")
    ap.add_argument("second")
    ap.add_argument("--names", nargs=2, default=["first", "second"])
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args(argv)
    blocks = compare(read(a.first), read(a.second))
    print(report(blocks, a.names[0], a.names[1], a.full))
    return 0 if all(k == "same" for k, _, _ in blocks) else 1


if __name__ == "__main__":
    sys.exit(main())
