# Cycle schedule (edge 0 = the edge where i_start is sampled; o_done/o_data are values right AFTER each edge)

## i_update_key = 1 (done after edge 21)
- Edge 0: latch i_data and i_key (rk0 = cipher key); o_done -> 0.
- Edges 1..10: key expansion, one round key per edge (edge n computes rk n).
- Edge 11: initial AddRoundKey with rk10.
- Edges 12..20: rounds 1..9 (InvShiftRows, InvSubBytes, AddRoundKey rk(10-r), InvMixColumns), r = edge-11.
- Edge 21: final round (InvShiftRows, InvSubBytes, AddRoundKey rk0); o_done -> 1, o_data = plaintext.

## i_update_key = 0 (done after edge 11), stored round keys used
- Edge 0: latch i_data; o_done -> 0.
- Edge 1: initial AddRoundKey with rk10.
- Edges 2..10: rounds 1..9 (rk9..rk1).
- Edge 11: final round (rk0); o_done -> 1, o_data = plaintext.

Reset (rst_n = 0): o_done 1, o_data 0, stored keys zero, idle. Inputs are ignored while busy. See Open points in aes_top_model.py.
