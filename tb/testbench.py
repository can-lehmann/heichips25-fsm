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
    for bit in program[::-1]:
        dut.ui_in[0].value = bit
        await ClockCycles(dut.clk, 1)
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
CONST_WIDTH = 16
CONST_COUNT = 2

COND_WIDTH = 1
ACTION_WIDTH = 2 + math.ceil(math.log2(CONST_COUNT))

Cond = Enum("Cond", ["IS_ZERO", "IN_0"])
ActionKind = Enum("Action", ["NO_OP", "LOAD_CONST", "DECR", "INCR"])

@dataclass
class Action:
    kind: ActionKind
    operand: int = 0

@dataclass
class StateDef:
    cond: Cond
    then_action: Action
    else_action: Action
    jump_target: int

def assemble(consts, states):
    program = []

    def emit(value, width):
        print(f"Emitting value {value} with width {width}")
        assert 0 <= value < (1 << width)
        nonlocal program
        for i in range(width):
            program.append((value >> i) & 1)

    for const_id in range(CONST_COUNT):
        if const_id in consts:
            value = consts[const_id]
        else:
            value = 0
        emit(value, CONST_WIDTH)

    for inst in states:
        emit(inst.jump_target, STATE_WIDTH)
        emit(inst.cond.value - 1, COND_WIDTH)
        emit(inst.then_action.kind.value - 1, 2)
        emit(inst.then_action.operand, math.ceil(math.log2(CONST_COUNT)))
        emit(inst.else_action.kind.value - 1, 2)
        emit(inst.else_action.operand, math.ceil(math.log2(CONST_COUNT)))
        
    return program

@cocotb.test()
async def counter_test(dut):
    # Create a clock with a period of 10ns = 100MHz
    clock = Clock(dut.clk, 10, 'ns')
    await cocotb.start(clock.start())

    await setup(dut)
    await load_program(dut, assemble({
        0: 10,
        1: 20
    }, [
        StateDef(
            cond=Cond.IN_0,
            then_action=Action(ActionKind.NO_OP),
            else_action=Action(ActionKind.NO_OP),
            jump_target=(i - 1 + STATE_COUNT) % STATE_COUNT
        )
        for i in range(STATE_COUNT)
    ]))

    dut.ui_in[0].value = 0
    await ClockCycles(dut.clk, 10)
    dut.ui_in[0].value = 1
    await ClockCycles(dut.clk, 10)


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
