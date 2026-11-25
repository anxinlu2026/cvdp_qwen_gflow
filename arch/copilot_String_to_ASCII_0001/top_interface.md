# top_interface.md — Python interface of the cycle-accurate model of `String_to_ASCII_Converter`

Source: task.md only.

## Ports named in task.md

| Port | Direction | Width | Sentence of task.md |
|---|---|---|---|
| `start` | input | 1 bit | "When `start` is asserted:" |
| `char_in` | input | 8 elements x 8 bits | "an 8-character input string"; "The char_in input array uses custom encoding, where each 8-bit value corresponds to a character's encoded value." |
| `ascii_out` | output | 8 elements; element width not stated (open point W1) | "The ascii_out array should contain the ASCII values corresponding to all input characters" |
| `valid` | output | 1 bit | "The `valid` signal should be asserted in the same cycle" |
| `ready` | output | 1 bit | "`ready` should deassert until processing is complete" |

A clock and a reset are implied ("Clock Cycle", "within 1 clock cycle") but task.md gives neither their names nor the polarity / kind of the reset (open point R1). The worker takes these names from the RTL port list.

## Class

```python
class Top:
    def __init__(self): ...
    def step(self, reset, start, char_in) -> dict:
        """One rising clock edge.
        reset   : 0/1, 1 = reset active at this edge (logical value; polarity of the pin is not given by task.md)
        start   : 0/1, value of `start` sampled at this edge
        char_in : list of 8 integers 0..255, value of `char_in` sampled at this edge
        returns : {"ascii_out": [8 integers], "valid": 0/1, "ready": 0/1}
                  = the output ports right after this edge
        """
```

## How multi-bit values are passed

- Every element of `char_in` and `ascii_out` is a non-negative Python integer; bit 7 of an 8-bit element is the most significant bit (weight 128), bit 0 the least significant.
- `char_in[0]` is the first (leftmost) character of the string as task.md writes it (`"A1b!C3d@"` -> index 0 is `A`); `ascii_out[i]` belongs to `char_in[i]` (task.md: `char_in = ["A", "1", "b", "!", "C", "3", "d", "@"]` gives `[65, 49, 98, 33, 67, 51, 100, 64]`, same order).
- How list index i maps to the bits of the RTL ports (unpacked array or one flat vector, and which end holds index 0) is not given by task.md (open point W2). The only thing fixed is that input and output use the same order.
- An element of `ascii_out` that task.md does not fix is returned as `None` by a model that follows the text strictly; a checker does not judge it.
