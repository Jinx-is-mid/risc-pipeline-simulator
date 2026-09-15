RISC-V Pipeline Simulator

A Python simulation of a 5-stage RISC-V CPU pipeline (Fetch, Decode, Execute, Memory, Write-back). It steps through a program cycle by cycle and correctly handles the hazards a real pipelined CPU has to deal with: forwarding data between instructions, stalling on load-use hazards, and flushing the pipeline on a taken branch.

Features:
- Full 5-stage pipeline with cycle-by-cycle simulation
- Data hazard forwarding + load-use stall detection
- Branch resolution with pipeline flush
- Supports `ADD`, `SUB`, `AND`, `OR`, `XOR`, `SLT`, `ADDI`, `LW`, `SW`, `BEQ`, `BNE`, `NOP`

Run it:
```bash
python3 riscv_simulator.py
```
No dependencies — just Python 3. This runs the built-in sample program and prints a pipeline diagram plus the final register/memory state.

Write your own program:
One instruction per line, `x0`-`x31` for registers, labels end in `:`:
```
ADDI x1, x0, 10
ADDI x2, x0, 20
ADD  x3, x1, x2
LW   x4, 0(x3)
BEQ  x4, x0, DONE
ADDI x5, x0, 1
DONE:
SW   x5, 0(x3)
```

Why I built this:
To understand CPU pipelining by implementing the hazard-handling logic myself, rather than just reading about it.
