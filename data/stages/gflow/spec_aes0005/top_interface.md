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
