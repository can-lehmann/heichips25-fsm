# SPDX-FileCopyrightText: © 2025 XXX Authors
# SPDX-License-Identifier: Apache-2.0

import os
import sys
from pathlib import Path
import cocotb
from cocotb.clock import Clock
from cocotb.runner import get_runner
from cocotb.triggers import Timer, ClockCycles

async def load_program(dut, program):
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)
    dut.ui_in[7].value = 1
    it = len(program) - 8
    while it >= 0:
        for it2 in range(8):
            dut.uio_in[it2].value = program[it + it2]
        await ClockCycles(dut.clk, 1)
        it -= 8
    dut.ui_in[7].value = 0

async def setup(dut, duration_ns=100):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0

    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 1)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)

import math
from dataclasses import dataclass
from enum import Enum

STATE_COUNT = 8
STATE_WIDTH = math.ceil(math.log2(STATE_COUNT))
COUNTER_WIDTH = 16
COUNTER_COUNT = 2

COND_WIDTH = 3
ACTION_WIDTH = 6

Cond = Enum("Cond", [
    "IS_ZERO_0",
    "IS_ZERO_1",
    "IS_ALU_ZERO",
    "IS_ALU_LSB",
    "IN_0",
    "IN_1",
    "IN_2",
    "IN_3"
])

CounterAction = Enum("CounterAction", [
    ("NOP", 0),
    ("RESET_0", 1),
    ("RESET_1", 5),
    ("DECR_0", 2),
    ("DECR_1", 6),
    ("LOAD_DATA_IN_0", 3),
    ("RESET_BOTH", 4),
    ("DECR_0_RESET_1", 7)
])

AluAction = Enum("AluAction", [
    "NOP",
    "LOAD_DATA_IN",
    "PARITY",
    "CLEAR_BUFFER",
    "SHIFT_RIGHT_ZERO",
    "SHIFT_RIGHT_DATA_IN",
    "SHIFT_LEFT_DATA_IN",
    "SHIFT_RIGHT_LOW8_DATA_IN"
])

@dataclass
class OutputOpcode:
    buffer: bool = False
    buffer_lsb: bool = False
    const_0: bool = False
    const_1: bool = False
    const_2: bool = False

    def encode(self):
        if self.buffer:
            return 3
        elif self.buffer_lsb:
            return 1 | (int(self.const_1) << 2) | (int(self.const_2) << 3)
        else:
            res = 0
            res |= int(self.const_0) << 1
            res |= int(self.const_1) << 2
            res |= int(self.const_2) << 3
            return res

@dataclass
class Action:
    alu: AluAction = AluAction.NOP
    counter: CounterAction = CounterAction.NOP

@dataclass
class StateDef:
    cond: Cond
    output_opcode: OutputOpcode
    then_action: Action
    else_action: Action
    jump_target: int
    repeat_state: bool = False
    slow_mode: bool = False

def assemble(consts, states):
    program = []

    def emit(value, width):
        print(f"Emitting value {value} with width {width}")
        assert 0 <= value < (1 << width)
        nonlocal program
        for i in range(width):
            program.append((value >> i) & 1)

    def emit_action(action):
        emit(action.alu.value - 1, 3)
        emit(action.counter.value, 3)

    for const_id in range(COUNTER_COUNT):
        if const_id in consts:
            value = consts[const_id]
        else:
            value = 0
        emit(value, COUNTER_WIDTH)

    for inst in states:
        emit(inst.jump_target, STATE_WIDTH)
        emit(int(inst.repeat_state), 1)
        emit(int(inst.slow_mode), 1)
        emit(inst.output_opcode.encode(), 4)
        emit(inst.cond.value - 1, COND_WIDTH)
        emit_action(inst.then_action)
        emit_action(inst.else_action)
    
    for it in range((8 - len(program) % 8) % 8):
        program.append(0)

    print(program)

    return program

@cocotb.test()
async def counter_test(dut):
    # Create a clock with a period of 10ns = 100MHz
    clock = Clock(dut.clk, 10, 'ns')
    await cocotb.start(clock.start())

    await setup(dut)
    await load_program(dut, assemble({}, [
        StateDef(
            cond=Cond.IN_0,
            output_opcode=OutputOpcode(),
            repeat_state=False,
            slow_mode=False,
            then_action=Action(),
            else_action=Action(),
            jump_target=(i - 1 + STATE_COUNT) % STATE_COUNT
        )
        for i in range(STATE_COUNT)
    ]))

    dut.ui_in[0].value = 0
    expected_state = 0
    for i in range(10):
        await ClockCycles(dut.clk, 1)
        state = dut.uo_out[5].value | (dut.uo_out[6].value << 1) | (dut.uo_out[7].value << 2)
        assert state == expected_state
        expected_state = (expected_state + 1) % STATE_COUNT
    dut.ui_in[0].value = 1
    for i in range(10):
        await ClockCycles(dut.clk, 1)
        state = dut.uo_out[5].value | (dut.uo_out[6].value << 1) | (dut.uo_out[7].value << 2)
        assert state == expected_state
        expected_state = (expected_state - 1) % STATE_COUNT


"""
# Ensure the otuput is 0x00
assert dut.uo_out.value == 0, "Output is not 0!"

# Wait for 10 clock cycles
await ClockCycles(dut.clk, 10)

# Ensure the otuput is still 0x00
assert dut.uo_out.value == 0, "Output is not 0!"

# Enable the counter
dut.ui_in.value = 1

# Wait for 10 clock cycles
await ClockCycles(dut.clk, 10)

# Ensure the otuput is 10-1
assert dut.uo_out.value == 10-1, "Output is not 9!"

# cocotb documentation: https://docs.cocotb.org/en/stable/refcard.html
# cocotb reference card: https://docs.cocotb.org/en/stable/refcard.html
"""

if __name__ == "__main__":

    sim         = os.getenv("SIM", "icarus")
    pdk_root    = os.getenv("PDK_ROOT", "~/.ciel")
    pdk         = os.getenv("PDK", "ihp-sg13g2")
    scl         = os.getenv("SCL", "sg13g2_stdcell")
    gl          = os.getenv("GL", False)

    testbench_path = Path(__file__).resolve().parent
    sources = []#[testbench_path / 'testbench.sv']
    defines = {}

    MACRO_NL = testbench_path / '../macro/nl/heichips25_template.nl.v'

    if gl:
        if not MACRO_NL.exists():
            print(f"The macro netlist {MACRO_NL} does not exist. Did you implement the macro?")
            sys.exit(0)
    
        sources.append(Path(pdk_root).expanduser() / pdk / "libs.ref" / scl / "verilog" / f"{scl}.v" )
        sources.append(MACRO_NL)
        defines = {'FUNCTIONAL': True, 'UNIT_DELAY': '#0'}
    else:
        sources.extend(list(testbench_path.glob('../src/*')))
        defines = {'RTL': True}

    hdl_toplevel = "heichips25_template"

    runner = get_runner(sim)
    runner.build(
        sources=sources,
        hdl_toplevel=hdl_toplevel,
        defines=defines,
        timescale=['1ns', '1ps'],
        waves=True,
        build_args=['--trace', '--trace-fst', '--trace-structs'] if sim == 'verilator' else ['-gno-specify'],
    )

    runner.test(
        hdl_toplevel=hdl_toplevel,
        test_module='testbench,',
        timescale=['1ns', '1ps'],
        waves=True,
        plusargs=['--trace-file', f'{hdl_toplevel}.fst']  if sim == 'verilator' else [],
    )
