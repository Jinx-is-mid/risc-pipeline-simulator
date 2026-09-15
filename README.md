RISC-V Pipeline Simulator

A Python simulation of a classic 5-stage RISC-V CPU pipeline (Fetch -> Decode -> Execute -> Memory -> Writeback). It models the register file, memory, and pipeline latches cycle-by-cycle, and implements the hazard-handling logic real CPUs use.

Features:
Full 5-stage pipeline: IF, ID, EX, MEM, WB
Data hazard forwarding (EX/MEM and MEM/WB to EX)
Load-use hazard detection with automatic stalling
Control hazard handling: branches resolved in EX with a pipeline flush
Supports ADD, SUB, AND, OR, XOR, SLT, ADDI, LW, SW, BEQ, BNE, NOP
How to run

python3 riscv_simulator.py

This runs a built-in sample program and prints a cycle-by-cycle pipeline diagram along with the final register and memory state.

Example output
Pipeline Diagram

Instruction C1 C2 C3 C4 C5 C6 ADDI x1, x0, 10 IF ID EX MEM WB ADDI x2, x0, 20 IF ID EX MEM WB ADD x3, x1, x2 IF ID EX MEM

What this demonstrates

Built to understand pipelining hazards hands-on: why forwarding alone can't resolve a load-use dependency, and why a taken branch costs a multi-cycle penalty when resolved mid-pipeline.
