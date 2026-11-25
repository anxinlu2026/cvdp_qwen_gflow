"""Cycle-accurate model of String_to_ASCII_Converter, written from task.md only.
Self-check model (not given to the worker). Run: python3 top_model.py
"""

N = 8  # characters per operation


def code_to_ascii(code, special_rule="linear"):
    """Custom code (0..255) -> ASCII value, or None where task.md does not fix it.

    special_rule selects one of the two readings of the contradictory
    special-character line (open point F2):
      "linear": code 62 -> 33 ('!'), 63 -> 34, ... contiguous, so '@'(64) is code 93
      "at95"  : only the three codes the text names: 62 -> 33, 63 -> 34, 95 -> 64
    """
    if 0 <= code <= 9:
        return 48 + code            # '0'..'9'
    if 10 <= code <= 35:
        return 65 + code - 10       # 'A'..'Z'
    if 36 <= code <= 61:
        return 97 + code - 36       # 'a'..'z'
    if code in (62, 63):
        return 33 + code - 62       # '!' and '"' are named with their codes
    if 64 <= code <= 95:
        if special_rule == "linear":
            return 33 + code - 62
        if special_rule == "at95":
            return 64 if code == 95 else None
    return None                     # 96..255: not defined by the text


def char_to_code(ch, special_rule="linear"):
    """Input preparation (testbench side): character -> custom code."""
    o = ord(ch)
    if 48 <= o <= 57:
        return o - 48
    if 65 <= o <= 90:
        return o - 65 + 10
    if 97 <= o <= 122:
        return o - 97 + 36
    if special_rule == "at95" and ch == "@":
        return 95
    if 33 <= o <= 64:
        return o - 33 + 62
    raise ValueError(ch)


class Top:
    """step(reset, start, char_in) -> dict(ascii_out=[8 ints], valid=0/1, ready=0/1)

    char_in / ascii_out: lists of 8 integers, index 0 = first (leftmost)
    character of the string as task.md writes it.
    None in ascii_out = value not fixed by task.md.
    """

    def __init__(self, special_rule="linear"):
        self.special_rule = special_rule
        self._idle()

    def _idle(self):
        self.ascii_out = [0] * N
        self.valid = 0
        self.ready = 1
        self.busy = False

    def step(self, reset, start, char_in):
        if reset:
            self._idle()                       # open point R1: reset state is the model's choice
        elif self.busy:
            self._idle()                       # edge 1: zeros, valid 0, ready 1 (start ignored: open point B1)
        elif start:
            self.ascii_out = [code_to_ascii(c & 0xFF, self.special_rule) for c in char_in]
            self.valid = 1                     # edge 0: all 8 values, valid 1, ready 0
            self.ready = 0
            self.busy = True
        return {"ascii_out": list(self.ascii_out), "valid": self.valid, "ready": self.ready}


def selfcheck():
    s = "A1b!C3d@"
    exp = [65, 49, 98, 33, 67, 51, 100, 64]
    zeros = [0] * N
    ok = True
    for rule in ("linear", "at95"):
        codes = [char_to_code(c, rule) for c in s]
        t = Top(rule)
        t.step(1, 0, zeros)
        # "Test Sequence" table, column "Expected ascii_out": cycle 1 start=1, cycles 2..5 start=0
        rows = [(1, exp, 1, 0)] + [(0, zeros, 0, 1)] * 4
        for i, (start, e_out, e_valid, e_ready) in enumerate(rows, 1):
            o = t.step(0, start, codes)
            good = (o["ascii_out"] == e_out and o["valid"] == e_valid and o["ready"] == e_ready)
            ok &= good
            print(f"rule={rule:6s} codes={codes} cycle {i}: {o} {'OK' if good else 'MISMATCH'}")
    # the codes the text names one by one
    named = {0: 48, 9: 57, 10: 65, 11: 66, 35: 90, 36: 97, 37: 98, 61: 122, 62: 33, 63: 34}
    for c, a in named.items():
        for rule in ("linear", "at95"):
            ok &= code_to_ascii(c, rule) == a
    ok &= code_to_ascii(95, "at95") == 64
    print("named codes checked:", sorted(named), "+ 95 (at95)")
    print("linear rule: code 95 ->", code_to_ascii(95, "linear"), "; '@' is code", char_to_code("@", "linear"))
    print("SELF-CHECK", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if selfcheck() else 1)
