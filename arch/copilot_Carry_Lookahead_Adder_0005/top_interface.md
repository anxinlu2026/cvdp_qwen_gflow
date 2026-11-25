# top_interface.md — Python interface of the cycle-accurate model of `pipelined_adder_32bit`

## Ports (as far as task.md names them)

| Port    | Direction | Width | Name comes from |
|---------|-----------|-------|-----------------|
| `clk`   | input     | 1     | "triggered by the positive edge of the clock (`clk`)" |
| `reset` | input     | 1     | "an active-high synchronous reset (`reset`) signal" |
| `start` | input     | 1     | "The `start` signal initiates the addition process" |
| `A`     | input     | 32    | "32-bit input operands `A` and `B`" |
| `B`     | input     | 32    | same sentence |
| `done`  | output    | 1     | "the `done` signal is asserted after the final stage is completed" |
| `S`     | output    | 32    | sum; the text only says "Output sum" and uses "S" as a table heading ("Expected S") |
| `Co`    | output    | 1     | carry-out; the text only says "carry" and uses "Co" as a table heading ("Expected Co") |

The names of the two result ports are not stated as port names in task.md ("Interface: details are explained
in the given code for all modules"). The worker takes the real names of the 32-bit sum output and the 1-bit
carry output from the RTL port list and maps them to `S` and `Co` (open point O5).

## Class

```python
class Top:
    def __init__(self): ...
    def step(self, reset, start, A, B) -> (done, S, Co)
```

- One call of `step` is one rising edge of `clk`. `clk` itself is not an argument.
- Arguments: the values the input ports have at that rising edge (the values that edge samples).
  - `reset`: 0 or 1 (1 = reset active at this edge).
  - `start`: 0 or 1.
  - `A`, `B`: Python integers 0 .. 2**32-1. Bit 31 of the integer is the most significant bit of the port
    (`A[31]`), bit 0 is `A[0]`. "Least significant byte" = bits 7..0, "most significant byte" = bits 31..24.
- Return value: the values of the output ports right after that edge (stable until the next edge).
  - `done`: 0 or 1.
  - `S`: integer 0 .. 2**32-1, bit 31 most significant.
  - `Co`: 0 or 1.
  - Any of the three may be `None`: the task text does not fix that value in that cycle; the checker
    does not judge it (see "Open points" in schedule.md).
- The first call must be a call with `reset = 1`. Before the first reset edge nothing is specified.
