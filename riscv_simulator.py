"""
RISC-V 5-Stage Pipeline CPU Simulator
======================================
Simulates: IF -> ID -> EX -> MEM -> WB
Handles:   RAW hazards via forwarding (EX/MEM -> EX, MEM/WB -> EX)
           Load-use hazards via a 1-cycle stall
           Control hazards (branches) via a 2-cycle flush (resolved in EX)

Supported instructions:
    ADD  rd, rs1, rs2
    SUB  rd, rs1, rs2
    AND  rd, rs1, rs2
    OR   rd, rs1, rs2
    XOR  rd, rs1, rs2
    SLT  rd, rs1, rs2
    ADDI rd, rs1, imm
    LW   rd, imm(rs1)
    SW   rs2, imm(rs1)
    BEQ  rs1, rs2, label
    BNE  rs1, rs2, label
    NOP
"""

import re
from collections import defaultdict

# ---------------------------------------------------------------------------
# Section 1: Register File
# ---------------------------------------------------------------------------

class RegisterFile:
    def __init__(self):
        self.regs = [0] * 32

    def read(self, idx):
        return 0 if idx == 0 else self.regs[idx]

    def write(self, idx, value):
        if idx != 0:
            self.regs[idx] = value

    def dump(self):
        return {f"x{i}": v for i, v in enumerate(self.regs) if v != 0}


# ---------------------------------------------------------------------------
# Section 2: Memory
# ---------------------------------------------------------------------------

class Memory:
    def __init__(self, preset=None):
        self.mem = defaultdict(int)
        if preset:
            self.mem.update(preset)

    def read(self, addr):
        return self.mem[addr]

    def write(self, addr, value):
        self.mem[addr] = value

    def dump(self):
        return {addr: v for addr, v in sorted(self.mem.items()) if v != 0}


# ---------------------------------------------------------------------------
# Section 3: Parser
# ---------------------------------------------------------------------------

_F = re.IGNORECASE
R_TYPE = re.compile(r"^(ADD|SUB|AND|OR|XOR|SLT)\s+x(\d+)\s*,\s*x(\d+)\s*,\s*x(\d+)$", _F)
I_TYPE = re.compile(r"^(ADDI)\s+x(\d+)\s*,\s*x(\d+)\s*,\s*(-?\d+)$", _F)
LOAD = re.compile(r"^(LW)\s+x(\d+)\s*,\s*(-?\d+)\(x(\d+)\)$", _F)
STORE = re.compile(r"^(SW)\s+x(\d+)\s*,\s*(-?\d+)\(x(\d+)\)$", _F)
BRANCH = re.compile(r"^(BEQ|BNE)\s+x(\d+)\s*,\s*x(\d+)\s*,\s*(\w+)$", _F)
NOP_RE = re.compile(r"^(NOP)$", _F)
LABEL_RE = re.compile(r"^(\w+):$")


def parse_program(source_lines):
    """Two-pass parser: first resolve label addresses, then decode operands."""
    raw = []
    for line in source_lines:
        line = line.split("#", 1)[0].strip()
        if line:
            raw.append(line)

    # Pass 1: strip labels, assign addresses
    labels = {}
    stripped = []
    addr = 0
    for line in raw:
        m = LABEL_RE.match(line)
        if m:
            labels[m.group(1)] = addr
        else:
            stripped.append(line)
            addr += 4

    # Pass 2: decode each instruction into a static dict
    program = []
    for pc, line in enumerate(stripped):
        pc *= 4
        program.append(decode_line(line, pc, labels))
    return program


def decode_line(line, pc, labels):
    inst = {"pc": pc, "text": line, "rd": 0, "rs1": 0, "rs2": 0, "imm": 0,
             "reg_write": False, "mem_read": False, "mem_write": False,
             "is_branch": False, "branch_type": None, "branch_target": None,
             "alu_op": "nop", "op": None}

    if m := R_TYPE.match(line):
        op, rd, rs1, rs2 = m.groups()
        inst.update(op=op, rd=int(rd), rs1=int(rs1), rs2=int(rs2),
                    reg_write=True, alu_op=op.lower())
    elif m := I_TYPE.match(line):
        op, rd, rs1, imm = m.groups()
        inst.update(op=op, rd=int(rd), rs1=int(rs1), imm=int(imm),
                    reg_write=True, alu_op="add")
    elif m := LOAD.match(line):
        op, rd, imm, rs1 = m.groups()
        inst.update(op=op, rd=int(rd), rs1=int(rs1), imm=int(imm),
                    reg_write=True, mem_read=True, alu_op="add")
    elif m := STORE.match(line):
        op, rs2, imm, rs1 = m.groups()
        inst.update(op=op, rs2=int(rs2), rs1=int(rs1), imm=int(imm),
                    mem_write=True, alu_op="add")
    elif m := BRANCH.match(line):
        op, rs1, rs2, label = m.groups()
        inst.update(op=op, rs1=int(rs1), rs2=int(rs2), is_branch=True,
                    branch_type="eq" if op == "BEQ" else "ne",
                    branch_target=labels[label], alu_op="sub")
    elif NOP_RE.match(line):
        inst.update(op="NOP")
    else:
        raise ValueError(f"Cannot parse instruction: {line!r}")
    return inst


# ---------------------------------------------------------------------------
# Section 4: ALU and Forwarding
# ---------------------------------------------------------------------------

def alu(op, a, b, imm):
    if op == "add":
        return a + imm if imm else a + b
    if op == "sub":
        return a - b
    if op == "and":
        return a & b
    if op == "or":
        return a | b
    if op == "xor":
        return a ^ b
    if op == "slt":
        return 1 if a < b else 0
    return 0


def forward(reg_num, ex_mem, mem_wb):
    """Return a forwarded value for reg_num, or None if no hazard exists."""
    if reg_num == 0:
        return None
    if ex_mem and ex_mem["reg_write"] and ex_mem["rd"] == reg_num and not ex_mem["mem_read"]:
        return ex_mem["alu_result"]
    if mem_wb and mem_wb["reg_write"] and mem_wb["rd"] == reg_num:
        return mem_wb["wb_value"]
    return None


# ---------------------------------------------------------------------------
# Section 5: Pipeline Simulator
# ---------------------------------------------------------------------------

class PipelineSimulator:
    def __init__(self, program, memory_preset=None, max_cycles=500):
        self.program = program
        self.regs = RegisterFile()
        self.mem = Memory(memory_preset)
        self.max_cycles = max_cycles
        self.pc = 0
        self.IF_ID = None
        self.ID_EX = None
        self.EX_MEM = None
        self.MEM_WB = None
        self._next_id = 0
        self.stage_log = defaultdict(dict)   # instr id -> {cycle: stage_name}
        self.instr_text = {}                 # instr id -> source text
        self.stall_count = 0
        self.flush_count = 0

    def _tag(self, inst):
        """Attach a unique tracking id the first time an instruction is fetched."""
        inst = dict(inst)
        inst["id"] = self._next_id
        self.instr_text[self._next_id] = inst["text"]
        self._next_id += 1
        return inst

    def run(self):
        cycle = 0
        while cycle < self.max_cycles:
            cycle += 1

            # ---- WB stage: write back using MEM_WB (from previous cycle) ----
            if self.MEM_WB:
                mw = self.MEM_WB
                if mw["reg_write"]:
                    self.regs.write(mw["rd"], mw["wb_value"])
                self.stage_log[mw["id"]][cycle] = "WB"

            # ---- MEM stage: access memory using EX_MEM ----
            new_MEM_WB = None
            if self.EX_MEM:
                em = self.EX_MEM
                wb_value = self.mem.read(em["alu_result"]) if em["mem_read"] else em["alu_result"]
                if em["mem_write"]:
                    self.mem.write(em["alu_result"], em["store_val"])
                new_MEM_WB = {"id": em["id"], "rd": em["rd"], "reg_write": em["reg_write"],
                              "wb_value": wb_value}
                self.stage_log[em["id"]][cycle] = "MEM"

            # ---- EX stage: ALU / forwarding / branch resolution ----
            new_EX_MEM = None
            branch_taken = False
            branch_target = None
            if self.ID_EX:
                ie = self.ID_EX
                fv1 = forward(ie["rs1"], self.EX_MEM, self.MEM_WB)
                fv2 = forward(ie["rs2"], self.EX_MEM, self.MEM_WB)
                val1 = fv1 if fv1 is not None else ie["val1"]
                val2 = fv2 if fv2 is not None else ie["val2"]

                alu_result = alu(ie["alu_op"], val1, val2, ie["imm"])

                if ie["is_branch"]:
                    equal = (val1 == val2)
                    branch_taken = equal if ie["branch_type"] == "eq" else not equal
                    branch_target = ie["branch_target"]

                new_EX_MEM = {"id": ie["id"], "rd": ie["rd"], "reg_write": ie["reg_write"],
                              "mem_read": ie["mem_read"], "mem_write": ie["mem_write"],
                              "alu_result": alu_result, "store_val": val2}
                self.stage_log[ie["id"]][cycle] = "EX"

            # ---- ID stage: decode + register read + hazard detection ----
            new_ID_EX = None
            stall = False
            if self.IF_ID:
                fi = self.IF_ID
                if (self.ID_EX and self.ID_EX["mem_read"]
                        and self.ID_EX["rd"] != 0
                        and self.ID_EX["rd"] in (fi["rs1"], fi["rs2"])):
                    stall = True
                    self.stall_count += 1
                    self.stage_log[fi["id"]][cycle] = "ID*"
                else:
                    new_ID_EX = dict(fi)
                    new_ID_EX["val1"] = self.regs.read(fi["rs1"])
                    new_ID_EX["val2"] = self.regs.read(fi["rs2"])
                    self.stage_log[fi["id"]][cycle] = "ID"

            # ---- IF stage: fetch next instruction ----
            new_IF_ID = None
            if stall:
                new_IF_ID = self.IF_ID  # hold the same instruction, re-decode next cycle
            elif self.pc < len(self.program) * 4:
                raw = self.program[self.pc // 4]
                new_IF_ID = self._tag(raw)
                self.stage_log[new_IF_ID["id"]][cycle] = "IF"
                self.pc += 4

            # ---- Resolve control hazard: flush wrong-path instructions ----
            if branch_taken:
                self.flush_count += 2
                new_IF_ID = None
                new_ID_EX = None
                self.pc = branch_target

            # ---- Commit all latches simultaneously ----
            self.MEM_WB = new_MEM_WB
            self.EX_MEM = new_EX_MEM
            self.ID_EX = new_ID_EX
            self.IF_ID = new_IF_ID

            done_fetching = self.pc >= len(self.program) * 4
            pipeline_empty = not any([self.IF_ID, self.ID_EX, self.EX_MEM, self.MEM_WB])
            if done_fetching and pipeline_empty:
                break

        return cycle

    # -----------------------------------------------------------------
    # Section 6: Reporting
    # -----------------------------------------------------------------

    def print_diagram(self):
        max_cycle = max((c for stages in self.stage_log.values() for c in stages), default=0)
        print("\nPipeline Diagram")
        print("-" * 70)
        header = "Instruction".ljust(28) + "".join(f"C{c:<6}" for c in range(1, max_cycle + 1))
        print(header)
        for iid in sorted(self.stage_log):
            row = self.instr_text[iid].ljust(28)
            for c in range(1, max_cycle + 1):
                row += self.stage_log[iid].get(c, "").ljust(7)
            print(row)

    def print_summary(self, cycles):
        print("\nExecution Summary")
        print("-" * 70)
        print(f"Total cycles:   {cycles}")
        print(f"Stalls:         {self.stall_count}")
        print(f"Flushes:        {self.flush_count}")
        print("\nFinal Register State (non-zero):")
        for name, val in self.regs.dump().items():
            print(f"  {name} = {val}")
        print("\nFinal Memory State (non-zero words):")
        for addr, val in self.mem.dump().items():
            print(f"  mem[{addr}] = {val}")


# ---------------------------------------------------------------------------
# Section 7: Sample Program and Entry Point
# ---------------------------------------------------------------------------

SAMPLE_PROGRAM = """
ADDI x1, x0, 10        # x1 = 10
ADDI x2, x0, 20        # x2 = 20
ADD  x3, x1, x2        # x3 = 30          (RAW hazard: needs forwarding)
LW   x4, 0(x3)         # x4 = mem[30]     (address depends on x3: forwarding)
ADD  x5, x4, x1        # x5 = x4 + 10     (load-use hazard: needs a stall)
SUB  x6, x5, x2
BEQ  x6, x0, SKIP      # branch resolved in EX: 2-cycle flush if taken
ADDI x7, x0, 99
SKIP:
ADDI x8, x0, 1
SW   x8, 4(x3)         # mem[34] = 1
"""


def main():
    lines = SAMPLE_PROGRAM.strip().splitlines()
    program = parse_program(lines)
    sim = PipelineSimulator(program, memory_preset={30: 5})
    cycles = sim.run()
    sim.print_diagram()
    sim.print_summary(cycles)


if __name__ == "__main__":
    main()
