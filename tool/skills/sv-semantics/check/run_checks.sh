#!/bin/sh
# Runs the rule checks of SKILL.md in the image (Icarus for simulation, Verilator lint for latches). From the skill directory:
#   docker run --rm -u root -v $PWD/check:/w -w /w --entrypoint sh lora-rtl:v5.4-noaes-20261108 run_checks.sh
iverilog -g2012 -o t rules_check.sv && vvp t
iverilog -g2012 -o t2 rules_check2.sv && vvp t2
verilator --lint-only -Wall latch_check.sv 2>&1 | grep -E "Warning-(LATCH|CASEINCOMPLETE)"
