"""Cycle-accurate port model of pipelined_adder_32bit, written from task.md only.

Top.step(reset, start, A, B) -> (done, S, Co): values of the outputs right after
the rising clock edge at which the given input values were sampled.
A returned None means: the task text does not fix this value (do not judge it).
"""
import random

M32 = 0xFFFFFFFF
LATENCY = 4  # the step that samples start=1 is step 1; done is returned by step 4


def cla8(a, b, cin):
    """8-bit carry-lookahead adder, bit by bit, formulas of task.md (P = A ^ B)."""
    c = cin
    s = 0
    for i in range(8):
        ai, bi = (a >> i) & 1, (b >> i) & 1
        g = ai & bi
        p = ai ^ bi
        s |= (p ^ c) << i
        c = g | (p & c)
    return s, c


def add32_staged(a, b, p_or=False):
    """Four 8-bit stages, low byte first, carry-in 0, carry chained (Pipeline Behavior table)."""
    c = 0
    s = 0
    for k in range(4):
        ab, bb = (a >> (8 * k)) & 0xFF, (b >> (8 * k)) & 0xFF
        if p_or:
            sb = 0
            for i in range(8):
                ai, bi = (ab >> i) & 1, (bb >> i) & 1
                g, p = ai & bi, ai | bi
                sb |= (p ^ c) << i
                c = g | (p & c)
        else:
            sb, c = cla8(ab, bb, c)
        s |= sb << (8 * k)
    return s, c


class Top:
    """hold: choice for open point O1 (outputs in cycles where done is 0).
         'unjudged' : S, Co returned as None whenever done is not 1 and the value is not fixed
         'gated'    : S, Co keep the last result until the next done
         'free'     : S, Co are the sum of the A, B sampled 3 edges earlier, start or not
    """

    def __init__(self, hold="unjudged"):
        assert hold in ("unjudged", "gated", "free")
        self.hold = hold
        # each entry: [valid, S, Co]; valid in (0, 1, None); index 0 = newest
        self.pipe = [[0, None, None] for _ in range(LATENCY - 1)]
        self.last = (None, None)      # last result shown with done = 1
        self.sig = []                 # (A, B) sampled at the edges since that result's acceptance

    def step(self, reset, start, A, B):
        A &= M32
        B &= M32
        s, co = add32_staged(A, B)
        if reset:
            # reset behaviour is not fixed by the text (open point O3)
            for e in self.pipe:
                if e[0] != 0:
                    e[0] = None
                e[1] = e[2] = None
            new = [None if start else 0, None, None]
            self.last = (None, None)
        else:
            new = [1 if start else 0, s, co]
        self.pipe.insert(0, new)
        out = self.pipe.pop()         # entered LATENCY-1 edges before this one
        valid = out[0]
        if valid == 1:
            self.last = (out[1], out[2])
            return 1, out[1], out[2]
        if valid is None:
            self.last = (None, None)
            return None, None, None
        # done = 0
        if self.hold == "gated":
            return 0, self.last[0], self.last[1]
        if self.hold == "free":
            return 0, out[1], out[2]
        # 'unjudged': fixed only if both choices agree
        if self.last[0] is not None and (out[1], out[2]) == self.last:
            return 0, out[1], out[2]
        return 0, None, None


# ---------------------------------------------------------------- self-check
EXAMPLES = [  # A, B, expected S, expected Co : table "Simulation Results" of task.md
    (0x12153524, 0xC0895E81, 0xD29E93A5, 0),
    (0x8484D609, 0xB1F05663, 0x36752C6C, 1),
    (0x06B97B0D, 0x46DF998D, 0x4D99149A, 0),
    (0xB2C28465, 0x89375212, 0x3BF9D677, 1),
]


def selfcheck():
    res = []
    # 1 function: staged CLA (P = XOR) against the table and against integer addition
    ok = all(add32_staged(a, b) == (s, c) for a, b, s, c in EXAMPLES)
    res.append(("function, 4 table rows, P = A ^ B", ok))
    ok_or = [add32_staged(a, b, p_or=True) == (s, c) for a, b, s, c in EXAMPLES]
    res.append(("function, 4 table rows, P = A | B gives the expected values (expected: none)", not any(ok_or)))
    rnd = random.Random(1)
    ok = True
    for _ in range(20000):
        a, b = rnd.getrandbits(32), rnd.getrandbits(32)
        t = a + b
        ok &= add32_staged(a, b) == (t & M32, t >> 32)
    res.append(("function equals A + B (33 bits), 20000 random pairs", ok))

    # 2 timing, continuous stream: the four rows on four successive edges
    for hold in ("unjudged", "gated", "free"):
        m = Top(hold)
        m.step(1, 0, 0, 0)
        outs = []
        for a, b, _, _ in EXAMPLES:
            outs.append(m.step(0, 1, a, b))
        for _ in range(5):
            outs.append(m.step(0, 0, 0, 0))
        dones = [o[0] for o in outs]
        ok = dones == [0, 0, 0, 1, 1, 1, 1, 0, 0]
        ok &= all(outs[3 + i][1:] == (s, c) for i, (_, _, s, c) in enumerate(EXAMPLES))
        res.append(("continuous stream, hold=%s: done on steps 4..7, values = table" % hold, ok))

    # 3 timing, single operations with A, B held: done one cycle, result retained
    for hold in ("unjudged", "gated", "free"):
        ok = True
        for a, b, s, c in EXAMPLES:
            m = Top(hold)
            m.step(1, 0, 0, 0)
            outs = [m.step(0, 1, a, b)] + [m.step(0, 0, a, b) for _ in range(8)]
            ok &= [o[0] for o in outs] == [0, 0, 0, 1, 0, 0, 0, 0, 0]
            ok &= all(o[1:] == (s, c) for o in outs[3:])
        res.append(("single operation, inputs held, hold=%s: done only on step 4, S/Co retained" % hold, ok))

    # 4 the open choices differ only where the model says None
    rnd = random.Random(2)
    mu, mg, mf = Top("unjudged"), Top("gated"), Top("free")
    ok = True
    for n in range(5000):
        r = 1 if (n == 0 or rnd.random() < 0.01) else 0
        st = rnd.getrandbits(1)
        a, b = rnd.getrandbits(32), rnd.getrandbits(32)
        if rnd.random() < 0.3:
            a, b = pa, pb
        pa, pb = a, b
        u, g, f = mu.step(r, st, a, b), mg.step(r, st, a, b), mf.step(r, st, a, b)
        for i in range(3):
            if u[i] is not None:
                ok &= (u[i] == g[i] == f[i])
            elif i == 0:
                ok &= g[0] is None and f[0] is None
    res.append(("'unjudged' model agrees with 'gated' and 'free' wherever it returns a value", ok))
    return res


if __name__ == "__main__":
    allok = True
    for name, ok in selfcheck():
        allok &= ok
        print("PASS" if ok else "FAIL", "-", name)
    print("ALL PASS" if allok else "SOME FAIL")
