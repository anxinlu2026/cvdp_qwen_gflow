# Top model interface (the same for every model that is compared)

Write a Python file `aes_top_model.py` (standard library only) with:

```python
class Top:
    """One chip, in the state you decide it has after a power-up reset."""
    def step(self, rst_n: int, i_start: int, i_update_key: int, i_key: int, i_data: int) -> tuple[int, int]:
        """Simulate ONE rising edge of clk.
        The arguments are the values the input ports have at that rising edge
        (i_key and i_data are 128-bit integers, bit 127 is the most significant bit, as at the ports;
        rst_n = 0 means the asynchronous reset rst_async_n is asserted at that edge).
        Returns (o_done, o_data): the values of the output ports right AFTER that rising edge
        (o_done is 0 or 1, o_data is a 128-bit integer)."""
```

- Each call is one clock edge, so the number of calls is the number of cycles.
- The ports are the ports of `aes128_decrypt` in task.md: clk, rst_async_n, i_update_key, i_key, i_start, i_data, o_done, o_data.
- Which cycle each result appears in, what a port does in each situation, and what the state is after reset are for you to decide from the task and the standard. Write them in comments next to the code, and list every place where the task leaves the behaviour open and the choice you made.
- Use no network. Do not sleep.

## Data at the ports (FIPS 197, Sections 3.3 to 3.5 and 5.2)

- i_data, o_data and i_key each hold 16 bytes in[0..15] (out[0..15], key[0..15]). Byte k is bits 127-8k down to 120-8k: byte 0 is bits 127:120, byte 15 is bits 7:0, as the hexadecimal strings of the standard are read from left to right.
- The state of the standard is s[r][c], r the row and c the column (0..3): s[r][c] = in[r + 4c] (Eq. 3.6) and out[r + 4c] = s[r][c] (Eq. 3.7). Bytes 0..3 are column 0, rows 0..3; bytes 4..7 are column 1; and so on.
- A word is 4 bytes [a0, a1, a2, a3], a0 first (Section 3.5); a column of the state is the word [s[0][c], s[1][c], s[2][c], s[3][c]]. The key gives the words w[i] = [key[4i], key[4i+1], key[4i+2], key[4i+3]] (Algorithm 2). The round key of round n is w[4n..4n+3], and word w[4n+c] is combined with column c of the state (Eq. 5.9).
