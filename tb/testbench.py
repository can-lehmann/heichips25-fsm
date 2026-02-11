# SPDX-FileCopyrightText: © 2025 XXX Authors
# SPDX-License-Identifier: Apache-2.0

import os
import sys
from pathlib import Path
import cocotb
from cocotb.clock import Clock
from cocotb.runner import get_runner
from cocotb.triggers import Timer, ClockCycles, ReadOnly, NextTimeStep

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
    "ALWAYS",
    "IS_ALU_ZERO",
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
    "DECR"
])

OutputMode = Enum("OutputMode", [
    "Default",
    "BufferHigh",
    "BufferLow",
    "BufferLSB"
])

@dataclass
class OutputOpcode:
    mode: OutputMode = OutputMode.Default
    const_0: bool = False
    const_1: bool = False
    const_2: bool = False

    def encode(self):
        match self.mode:
            case OutputMode.Default:
                res = 0
                res |= int(self.const_0) << 1
                res |= int(self.const_1) << 2
                res |= int(self.const_2) << 3
                return res
            case OutputMode.BufferHigh:
                return 7
            case OutputMode.BufferLow:
                return 3
            case OutputMode.BufferLSB:
                return 1 | (int(self.const_1) << 2) | (int(self.const_2) << 3)
        assert False

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

    @staticmethod
    def placeholder():
        return StateDef(
            cond=Cond.IN_0,
            output_opcode=OutputOpcode(),
            repeat_state=False,
            slow_mode=False,
            then_action=Action(),
            else_action=Action(),
            jump_target=0
        )

def assemble(consts, states):
    while len(states) < STATE_COUNT:
        states.append(StateDef.placeholder())

    program = []

    def emit(value, width):
        assert 0 <= value < (1 << width)
        nonlocal program
        for i in range(width):
            program.append((value >> i) & 1)

    def emit_action(action):
        emit(action.counter.value, 3)
        emit(action.alu.value - 1, 3)

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

    return program

def get_state(dut):
    return dut.uo_out[5].value | (dut.uo_out[6].value << 1) | (dut.uo_out[7].value << 2)

@cocotb.test()
async def counter_test(dut):
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
        await ReadOnly()
        assert get_state(dut) == expected_state
        await ClockCycles(dut.clk, 1)
        expected_state = (expected_state + 1) % STATE_COUNT
    dut.ui_in[0].value = 1
    for i in range(10):
        await ReadOnly()
        assert get_state(dut) == expected_state
        await ClockCycles(dut.clk, 1)
        expected_state = (expected_state - 1) % STATE_COUNT

@cocotb.test()
async def serialize8_test(dut):
    clock = Clock(dut.clk, 10, 'ns')
    await cocotb.start(clock.start())

    await setup(dut)
    await load_program(dut, assemble({
        0: 7
    }, [
        StateDef(
            cond = Cond.IN_0,
            output_opcode = OutputOpcode(
                const_1 = True
            ),
            repeat_state = True,
            slow_mode = False,
            then_action = Action(
                alu = AluAction.LOAD_DATA_IN,
                counter = CounterAction.RESET_0
            ),
            else_action = Action(),
            jump_target = 1
        ),
        StateDef(
            cond = Cond.IS_ZERO_0,
            output_opcode = OutputOpcode(
                mode = OutputMode.BufferLSB,
                const_1 = False,
                const_2 = True
            ),
            repeat_state = True,
            slow_mode = False,
            then_action = Action(),
            else_action = Action(
                alu = AluAction.SHIFT_RIGHT_ZERO,
                counter = CounterAction.DECR_0
            ),
            jump_target = 0
        )
    ]))

    for test_value in [123, 10, 0, 255]:
        await ClockCycles(dut.clk, 10)
        assert get_state(dut) == 0

        dut.ui_in[0].value = 1
        dut.uio_in.value = test_value
        await ClockCycles(dut.clk, 1)
        await ReadOnly()

        assert get_state(dut) == 1

        await NextTimeStep()
        dut.ui_in[0].value = 0

        serialized_value = 0
        for it in range(8):
            await ReadOnly()
            serialized_value |= (dut.uo_out[0].value << it)
            await ClockCycles(dut.clk, 1)
        
        assert serialized_value == test_value, f"Expected {test_value} but got {serialized_value}"

@cocotb.test()
async def serialize16_test(dut):
    clock = Clock(dut.clk, 10, 'ns')
    await cocotb.start(clock.start())

    await setup(dut)
    await load_program(dut, assemble({
        0: 15
    }, [
        StateDef(
            cond = Cond.IN_0,
            output_opcode = OutputOpcode(
                const_1 = True
            ),
            repeat_state = True,
            slow_mode = False,
            then_action = Action(
                alu = AluAction.LOAD_DATA_IN,
                counter = CounterAction.RESET_0
            ),
            else_action = Action(),
            jump_target = 1
        ),
        StateDef(
            cond = Cond.IN_0,
            output_opcode = OutputOpcode(
                const_1 = True
            ),
            repeat_state = True,
            slow_mode = False,
            then_action = Action(
                alu = AluAction.LOAD_DATA_IN,
                counter = CounterAction.RESET_0
            ),
            else_action = Action(),
            jump_target = 2
        ),
        StateDef(
            cond = Cond.IS_ZERO_0,
            output_opcode = OutputOpcode(
                mode = OutputMode.BufferLSB,
                const_1 = False,
                const_2 = True
            ),
            repeat_state = True,
            slow_mode = False,
            then_action = Action(),
            else_action = Action(
                alu = AluAction.SHIFT_RIGHT_ZERO,
                counter = CounterAction.DECR_0
            ),
            jump_target = 0
        )
    ]))

    for test_value in [12345, 10, 0, 255, 65535]:
        await ClockCycles(dut.clk, 10)
        assert get_state(dut) == 0

        dut.ui_in[0].value = 1

        dut.uio_in.value = (test_value >> 8) & 0xff
        await ClockCycles(dut.clk, 1)

        dut.ui_in[0].value = 0
        await ClockCycles(dut.clk, test_value % 3)

        dut.ui_in[0].value = 1
        dut.uio_in.value = test_value & 0xff
        await ClockCycles(dut.clk, 1)

        await ReadOnly()
        assert get_state(dut) == 2

        await NextTimeStep()
        dut.ui_in[0].value = 0

        serialized_value = 0
        for it in range(16):
            await ReadOnly()
            serialized_value |= (dut.uo_out[0].value << it)
            await ClockCycles(dut.clk, 1)
        
        assert serialized_value == test_value, f"Expected {test_value} but got {serialized_value}"

@cocotb.test()
async def deserialize_test(dut):
    clock = Clock(dut.clk, 10, 'ns')
    await cocotb.start(clock.start())

    await setup(dut)
    await load_program(dut, assemble({
        0: 7
    }, [
        # Initialize State, always jump to state 1
        StateDef(
            cond = Cond.ALWAYS,
            output_opcode = OutputOpcode(),
            repeat_state = False,
            slow_mode = False,
            then_action = Action(
                alu = AluAction.CLEAR_BUFFER,
                counter = CounterAction.RESET_0
            ),
            else_action = Action(),
            jump_target = 1
        ),
        # Read 8 bits
        StateDef(
            cond = Cond.IS_ZERO_0,
            output_opcode = OutputOpcode(const_1 = True),
            repeat_state = True,
            slow_mode = False,
            then_action = Action(
                alu = AluAction.SHIFT_RIGHT_DATA_IN
            ),
            else_action = Action(
                alu = AluAction.SHIFT_RIGHT_DATA_IN,
                counter = CounterAction.DECR_0
            ),
            jump_target = 2
        ),
        # Announce Valid and wait for Ready
        StateDef(
            cond = Cond.IN_1,
            output_opcode = OutputOpcode(const_2 = True),
            repeat_state = True,
            slow_mode = False,
            then_action = Action(),
            else_action = Action(),
            jump_target = 3
        ),
        # Output the deserialized value for one cycle, then jump back to state 0
        StateDef(
            cond = Cond.ALWAYS,
            output_opcode = OutputOpcode(mode = OutputMode.BufferHigh),
            repeat_state = False,
            slow_mode = False,
            then_action = Action(
                alu = AluAction.CLEAR_BUFFER,
                counter = CounterAction.RESET_0
            ),
            else_action = Action(),
            jump_target = 1
        )
    ]))

    for test_value in [123, 10, 0, 255]:
        for it in range(10):
            await ReadOnly()
            if dut.uo_out[1].value == 1:
                assert get_state(dut) == 1
                break
            await ClockCycles(dut.clk, 1)
        else:
            assert False
        
        await NextTimeStep()
        for it in range(8):
            dut.uio_in[0].value = (test_value >> it) & 1
            await ClockCycles(dut.clk, 1)
        
        await ReadOnly()
        assert get_state(dut) == 2

        # Wait some arbitrary number of cycles before setting Ready
        await ClockCycles(dut.clk, test_value % 3 + 2)

        dut.ui_in[1].value = 1
        await ClockCycles(dut.clk, 1)
        await ReadOnly()

        assert dut.uo_out.value == test_value, f"Expected {test_value} but got {dut.uo_out.value}"

        await NextTimeStep()
        dut.ui_in[1].value = 0

        await ClockCycles(dut.clk, 1)

@cocotb.test()
async def pwm_test(dut):
    clock = Clock(dut.clk, 10, 'ns')
    await cocotb.start(clock.start())

    await setup(dut)
    await load_program(dut, assemble({
        0: 4,
        1: 3
    }, [
        # Initialize State, always jump to state 1
        StateDef(
            cond = Cond.ALWAYS,
            output_opcode = OutputOpcode(),
            repeat_state = False,
            slow_mode = False,
            then_action = Action(
                alu = AluAction.LOAD_DATA_IN,
                counter = CounterAction.RESET_BOTH
            ),
            else_action = Action(),
            jump_target = 1
        ),
        # High phase
        StateDef(
            cond = Cond.IS_ALU_ZERO,
            output_opcode = OutputOpcode(const_2 = True),
            repeat_state = True,
            slow_mode = True,
            then_action = Action(
                counter = CounterAction.RESET_1,
            ),
            else_action = Action(
                counter = CounterAction.DECR_0_RESET_1,
                alu = AluAction.DECR
            ),
            jump_target = 2
        ),
        # Low phase
        StateDef(
            cond = Cond.IS_ZERO_0,
            output_opcode = OutputOpcode(),
            repeat_state = True,
            slow_mode = True,
            then_action = Action(
                counter = CounterAction.RESET_BOTH,
                alu = AluAction.LOAD_DATA_IN
            ),
            else_action = Action(
                counter = CounterAction.DECR_0_RESET_1,
                alu = AluAction.DECR
            ),
            jump_target = 1
        )
    ]))

    dut.uio_in.value = 2
    await ClockCycles(dut.clk, 1)
    await ReadOnly()

    assert get_state(dut) == 1
    await ClockCycles(dut.clk, 20)



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
