# Copyright (c) 2026 Can Joshua Lehmann
# SPDX-License-Identifier: Apache-2.0
# Based on the original testbench.py from the heichips25 template repository

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
    INPUT_WIDTH = 1
    it = len(program) - INPUT_WIDTH
    while it >= 0:
        for it2 in range(INPUT_WIDTH):
            dut.uio_in[it2].value = program[it + it2]
        await ClockCycles(dut.clk, 1)
        it -= INPUT_WIDTH
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
    "BufferLSB",
    "Keep"
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
            case OutputMode.Keep:
                return 15
        assert False
    
    def __str__(self):
        match self.mode:
            case OutputMode.Default:
                return f"{int(self.const_0)}, {int(self.const_1)}, {int(self.const_2)}"
            case OutputMode.BufferLSB:
                return f"lsb, {int(self.const_1)}, {int(self.const_2)}"
            case _:
                return self.mode.name

@dataclass
class Action:
    alu: AluAction = AluAction.NOP
    counter: CounterAction = CounterAction.NOP

    def format(self, constants):
        cmds = []

        match self.alu:
            case AluAction.NOP: pass
            case AluAction.LOAD_DATA_IN: cmds.append("buf = {buf[15:0], data_in}")
            case AluAction.PARITY: cmds.append("buf = parity(buf)")
            case AluAction.CLEAR_BUFFER: cmds.append("buf = 0")
            case AluAction.SHIFT_RIGHT_ZERO: cmds.append("buf >>= 1")
            case AluAction.SHIFT_RIGHT_DATA_IN: cmds.append("buf >>= {data_in[0], buf[23:1]}")
            case AluAction.SHIFT_LEFT_DATA_IN: cmds.append("buf = {buf[22:0], data_in[0]}")
            case AluAction.DECR: cmds.append("buf -= 1")
        
        match self.counter:
            case CounterAction.NOP: pass
            case CounterAction.RESET_0: cmds.append(f"counter_0 = {constants[0]}")
            case CounterAction.RESET_1: cmds.append(f"counter_1 = {constants[1]}")
            case CounterAction.DECR_0: cmds.append("counter_0 -= 1")
            case CounterAction.DECR_1: cmds.append("counter_1 -= 1")
            case CounterAction.LOAD_DATA_IN_0: cmds.append("counter_0 = data_in")
            case CounterAction.RESET_BOTH:
                cmds.append(f"counter_0 = {constants[0]}")
                cmds.append(f"counter_1 = {constants[1]}")
            case CounterAction.DECR_0_RESET_1:
                cmds.append("counter_0 -= 1")
                cmds.append(f"counter_1 = {constants[1]}")

        return cmds

@dataclass
class StateExtension:
    cond: Cond
    then_action: Action
    jump_target: int

@dataclass
class StateDef:
    cond: Cond
    output_opcode: OutputOpcode
    then_action: Action
    else_action: Action
    jump_target: int
    repeat_state: bool = False
    slow_mode: bool = False
    extension: StateExtension = None
    doc: str = ""

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

def save_dot(path, states, constants):
    with open(path, "w") as f:
        f.write("digraph {\n")
        f.write("rankdir=LR;\n")
        f.write("node [fontname=\"Noto Sans\"];\n")
        f.write("edge [fontname=\"Noto Sans\"];\n")

        for it, state in enumerate(states):
            if state is not None:
                label = f"State {it}\\n"
                if state.doc:
                    label += state.doc + "\\n"
                label += f"Output = {state.output_opcode}"
                if state.slow_mode:
                    label += "\\n(Wait for counter_1)"
                f.write(f"s{it} [shape=box, label=\"{label}\"];\n")
        
        def format_cond(cond):
            match cond:
                case Cond.IS_ZERO_0: return "counter_0 == 0"
                case Cond.IS_ZERO_1: return "counter_1 == 0"
                case Cond.ALWAYS: return "1"
                case Cond.IS_ALU_ZERO: return "buf == 0"
                case Cond.IN_0: return "in[0]"
                case Cond.IN_1: return "in[1]"
                case Cond.IN_2: return "in[2]"
                case Cond.IN_3: return "in[3]"

        def transition(from_state, cond, to_state, action):
            label = "\\n".join((["if " + cond] if cond != "1" else []) + action.format(constants))
            f.write(f"s{from_state} -> s{to_state} [label=\"{label}\"];\n")
        
        for it, state in enumerate(states):
            if state is not None:
                transition(it, format_cond(state.cond), state.jump_target, state.then_action)
                else_target = it if state.repeat_state else (it + 1) % STATE_COUNT
                if state.cond == Cond.ALWAYS:
                    continue
                if state.extension is not None:
                    transition(
                        it,
                        f"!{format_cond(state.cond)} & {format_cond(state.extension.cond)}",
                        state.extension.jump_target,
                        state.extension.then_action
                    )
                    if state.extension.cond == Cond.ALWAYS:
                        continue
                    transition(
                        it,
                        f"!{format_cond(state.cond)} & !{format_cond(state.extension.cond)}",
                        else_target,
                        state.else_action
                    )
                else:
                    transition(it, f"!{format_cond(state.cond)}", else_target, state.else_action)
        
        f.write("}\n")

def assemble(consts, states, path=None):
    if type(states) is dict:
        state_dict = states
        states = [None] * STATE_COUNT
        for key, value in state_dict.items():
            states[key] = value
    else:
        while len(states) < STATE_COUNT:
            states.append(None)

    if path is not None:
        save_dot(path, states, consts)
    
    extended_state = None
    for it, state in enumerate(states):
        if state is not None and state.extension is not None:
            assert extended_state is None, "Only one state can have an extension"
            extended_state = it
            assert states[STATE_COUNT - 1] is None, "The last state is reserved for the extension. Cannot use it as a normal state."
            states[STATE_COUNT - 1] = StateDef(
                cond = state.extension.cond,
                output_opcode = OutputOpcode(),
                repeat_state = False,
                slow_mode = False,
                then_action = state.extension.then_action,
                else_action = Action(),
                jump_target = state.extension.jump_target
            )

    for it, state in enumerate(states):
        if state is None:
            states[it] = StateDef.placeholder()

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
    
    if extended_state is None:
        extended_state = STATE_COUNT - 1
    emit(extended_state, STATE_WIDTH)

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
    ], path="counter.dot"))

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
    ], path="serialize8.dot"))

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
    ], path="serialize16.dot"))

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
    ], path="deserialize.dot"))

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
async def state_extension_test(dut):
    clock = Clock(dut.clk, 10, 'ns')
    await cocotb.start(clock.start())

    return_to_state_0 = StateDef(
        cond = Cond.ALWAYS,
        output_opcode = OutputOpcode(),
        repeat_state = False,
        slow_mode = False,
        then_action = Action(),
        else_action = Action(),
        jump_target = 0
    )

    await setup(dut)
    await load_program(dut, assemble({}, [
        StateDef(
            cond = Cond.IN_0,
            output_opcode = OutputOpcode(),
            repeat_state = True,
            slow_mode = False,
            then_action = Action(),
            else_action = Action(),
            jump_target = 1
        ),
        StateDef(
            cond = Cond.IN_0,
            jump_target = 3,
            then_action = Action(),
            output_opcode = OutputOpcode(),
            repeat_state = False,
            slow_mode = False,
            else_action = Action(),
            extension = StateExtension(
                cond = Cond.IN_1,
                then_action = Action(),
                jump_target = 4
            )
        ),
        return_to_state_0,
        return_to_state_0,
        return_to_state_0
    ], path="state_extension.dot"))

    for (in_0, in_1, expected_state) in [
        (0, 0, 2),
        (1, 0, 3),
        (0, 1, 4),
        (1, 1, 3)
    ]:
        await ClockCycles(dut.clk, 10)
        await ReadOnly()
        assert get_state(dut) == 0

        await NextTimeStep()
        dut.ui_in[0].value = 1
        await ClockCycles(dut.clk, 1)
        await ReadOnly()

        assert get_state(dut) == 1
        
        await NextTimeStep()
        dut.ui_in[0].value = in_0
        dut.ui_in[1].value = in_1
        await ClockCycles(dut.clk, 1)
        await ReadOnly()

        assert get_state(dut) == expected_state, f"Expected state {expected_state} but got {get_state(dut)}"


@cocotb.test()
async def pwm_test(dut):
    clock = Clock(dut.clk, 10, 'ns')
    await cocotb.start(clock.start())

    for (clock_divider, resolution) in [(1, 4), (3, 2), (3, 3)]:
        await NextTimeStep()

        IS_NEW_CYCLE = 0
        WAIT = 1
        SET_HIGH = 2
        SET_LOW = 3

        await setup(dut)
        await load_program(dut, assemble({
            0: resolution,
            1: clock_divider
        }, {
            IS_NEW_CYCLE: StateDef(
                doc = "Is New Cycle?",
                cond = Cond.IS_ZERO_0,
                output_opcode = OutputOpcode(mode = OutputMode.Keep),
                repeat_state = False,
                slow_mode = False,
                then_action = Action(
                    alu = AluAction.LOAD_DATA_IN,
                    counter = CounterAction.RESET_0
                ),
                extension = StateExtension(
                    cond = Cond.IS_ALU_ZERO,
                    then_action = Action(
                        counter = CounterAction.DECR_0
                    ),
                    jump_target = WAIT
                ),
                else_action = Action(
                    counter = CounterAction.DECR_0,
                    alu = AluAction.DECR
                ),
                jump_target = WAIT
            ),
            WAIT: StateDef(
                doc = "Wait",
                slow_mode=True,
                output_opcode=OutputOpcode(mode = OutputMode.Keep),
                cond=Cond.IS_ALU_ZERO,
                repeat_state=False,
                then_action=Action(
                    counter=CounterAction.RESET_1
                ),
                else_action=Action(
                    counter=CounterAction.RESET_1
                ),
                jump_target=SET_LOW
            ),
            SET_HIGH: StateDef(
                doc = "Set High",
                cond = Cond.ALWAYS,
                output_opcode = OutputOpcode(const_0 = True),
                repeat_state = False,
                slow_mode = False,
                then_action = Action(),
                else_action = Action(),
                jump_target = IS_NEW_CYCLE
            ),
            SET_LOW: StateDef(
                doc = "Set Low",
                cond = Cond.ALWAYS,
                output_opcode = OutputOpcode(),
                repeat_state = False,
                slow_mode = False,
                then_action = Action(),
                else_action = Action(),
                jump_target = IS_NEW_CYCLE
            )
        }, path=f"pwm_{clock_divider}_{resolution}.dot"))

        pwm_value = 0
        dut.uio_in.value = pwm_value

        await ClockCycles(dut.clk, 1)
        await ReadOnly()

        assert get_state(dut) == WAIT

        for next_pwm_value in range(1, (resolution + 1) + 2):
            print(f"Testing PWM value {pwm_value} / {resolution + 1}")
            await NextTimeStep()
            dut.uio_in.value = next_pwm_value

            num, den = 0, 0
            for it in range((3 + clock_divider) * (resolution + 1)):
                await ClockCycles(dut.clk, 1)
                await ReadOnly()
                if dut.uo_out[0].value:
                    print(f"  Cycle {it}: Output is HIGH")
                    num += 1
                else:
                    print(f"  Cycle {it}: Output is LOW")
                den += 1

            duty_cycle = num / den
            expected_duty_cycle = pwm_value / (resolution + 1)
            assert duty_cycle == expected_duty_cycle, f"Expected duty cycle {expected_duty_cycle} but got {duty_cycle}"

            pwm_value = next_pwm_value

@cocotb.test()
async def uart_tx_test(dut):
    clock = Clock(dut.clk, 10, 'ns')
    await cocotb.start(clock.start())

    await setup(dut)
    await load_program(dut, assemble({
        0: 8, # 8 bit + 1 parity bit
        1: 3 # Clock divider for baud rate generation
    }, [
        # Stop Bit
        StateDef(
            doc = "Stop Bit",
            cond = Cond.ALWAYS,
            output_opcode = OutputOpcode(const_0 = True),
            repeat_state = False,
            slow_mode = True,
            then_action = Action(
                counter = CounterAction.RESET_1
            ),
            else_action = Action(),
            jump_target = 1
        ),
        StateDef(
            doc = "Ready",
            cond = Cond.IN_0,
            output_opcode = OutputOpcode(
                const_0 = True,
                const_1 = True
            ),
            repeat_state = False,
            slow_mode = False,
            then_action = Action(
                counter = CounterAction.DECR_1
            ),
            else_action = Action(
                alu = AluAction.LOAD_DATA_IN,
                counter = CounterAction.DECR_1
            ),
            jump_target = 0
        ),
        StateDef(
            doc = "Wait for Clock",
            cond = Cond.ALWAYS,
            output_opcode = OutputOpcode(const_0 = True),
            repeat_state = False,
            slow_mode = True,
            then_action = Action(
                counter = CounterAction.RESET_1
            ),
            else_action = Action(),
            jump_target = 3
        ),
        # Start Bit & Compute Parity
        StateDef(
            doc = "Start Bit & Compute Parity",
            cond = Cond.ALWAYS,
            output_opcode = OutputOpcode(
                const_0 = False
            ),
            repeat_state = False,
            slow_mode = True,
            then_action = Action(
                alu = AluAction.PARITY,
                counter = CounterAction.RESET_BOTH
            ),
            else_action = Action(),
            jump_target = 4
        ),
        # Send Data & Parity
        StateDef(
            doc = "Send",
            cond = Cond.IS_ZERO_0,
            output_opcode = OutputOpcode(mode = OutputMode.BufferLSB),
            repeat_state = True,
            slow_mode = True,
            then_action = Action(
                counter = CounterAction.RESET_BOTH
            ),
            else_action = Action(
                alu = AluAction.SHIFT_RIGHT_ZERO,
                counter = CounterAction.DECR_0_RESET_1
            ),
            jump_target = 0
        )
    ], path="uart_tx.dot"))

    await NextTimeStep()
    dut.ui_in[0].value = 1

    await ClockCycles(dut.clk, 12)

    text = "Hello, world!"
    recv = ""
    index = 0

    started_recv = False
    bits = []
    clock_cycle = 0

    prev_bit = None

    while True:
        if clock_cycle > 1000:
            assert False, f"Timeout while waiting for transmission to complete. Received so far: '{recv}'"
        
        await NextTimeStep()

        if dut.uo_out[1].value:
            if index >= len(text):
                break
            dut.uio_in.value = ord(text[index])
            dut.ui_in[0].value = 0
            index += 1
        else:
            dut.ui_in[0].value = 1

        await ClockCycles(dut.clk, 1)
        await ReadOnly()

        if clock_cycle % 4 == 0:
            if not started_recv:
                if dut.uo_out[0].value == 0:
                    started_recv = True
                    bits = []
            else:
                bits.append(dut.uo_out[0].value)

                if len(bits) == 9:
                    byte = 0
                    for it in range(8):
                        byte |= (bits[it] << it)
                    parity_bit = bits[8]
                    assert parity_bit == (bin(byte).count("1") % 2), f"Parity error for byte {byte}, bits: {bits}"
                    recv += chr(byte)
                    print(f"Received byte: {byte} ('{chr(byte)}'), bits: {bits}")
                    
                    bits = []
                    started_recv = False
        
        if prev_bit is None:
            prev_bit = (dut.uo_out[0].value, clock_cycle)
        elif dut.uo_out[0].value != prev_bit[0]:
            assert (clock_cycle - prev_bit[1]) % 4 == 0, f"Bit changed at unexpected time. Previous bit: {prev_bit[0]} at cycle {prev_bit[1]}, current bit: {dut.uo_out[0].value} at cycle {clock_cycle}"
            prev_bit = (dut.uo_out[0].value, clock_cycle)

        clock_cycle += 1
    
    assert recv == text, f"Expected to receive '{text}' but got '{recv}' after {clock_cycle} clock cycles"
            

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
