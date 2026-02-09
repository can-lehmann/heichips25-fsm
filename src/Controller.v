// Copyright (c) 2026 Can Joshua Lehmann
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

module Counter2 #(
  parameter WIDTH = 16
) (
  input clock,
  input rst_n,
  input [2:0] opcode,
  input [WIDTH-1:0] const_0,
  input [WIDTH-1:0] const_1,
  input [7:0] data_in,
  output zero_0,
  output zero_1
);

  // Opcodes
  // 000: NOP
  // 100: Reset both counters
  // x01: Reset counter_x
  // x10: Decrement counter_x
  // 011: Load data_in into counter_0
  // 111: Decrement counter_0 and Reset counter_1

  reg [WIDTH-1:0] counter_0;
  reg [WIDTH-1:0] counter_1;

  always @(posedge clock)
    if (!rst_n)
      begin
        counter_0 <= 0;
        counter_1 <= 0;
      end
    else
      case (opcode)
        3'b000: ; // NOP
        3'b100:
          begin
            counter_0 <= 0;
            counter_1 <= 0;
          end
        3'b001: counter_0 <= const_0;
        3'b101: counter_1 <= const_1;
        3'b010: counter_0 <= counter_0 - 1;
        3'b110: counter_1 <= counter_1 - 1;
        3'b011: counter_0 <= {8'b0, data_in};
        3'b111:
          begin
            counter_0 <= counter_0 - 1;
            counter_1 <= 0;
          end
        default: ; // NOP
      endcase
  
  assign zero_0 = (counter_0 == 0);
  assign zero_1 = (counter_1 == 0);
endmodule

module AluBuffer #(
  parameter WIDTH = 24
) (
  input clock,
  input rst_n,
  input [2:0] opcode,
  input [7:0] data_in,
  output [7:0] low8,
  output zero,
  output lsb
);

  // Opcodes
  // 000: NOP
  // 001: Load data_in into buffer[7:0], shifting the old buffer left by 8
  // 010: Load data_in into buffer[15:8]
  // 011: Clear buffer
  // 100: Shift buffer right by 1, inserting 0 at the left
  // 101: Shift buffer right by 1, inserting data_in[0] at the left
  // 110: Shift buffer left by 1, inserting data_in[0] at the right
  // 111: Shift buffer[7:0] right by 1, inserting data_in[0] at buffer[7]


  reg [WIDTH-1:0] buffer;

  always @(posedge clock)
    if (!rst_n)
      buffer <= 0;
    else
      case (opcode)
        3'b000: ; // NOP
        3'b001: buffer <= {buffer[WIDTH - 1 - 8:0], data_in};
        3'b010: buffer[8] <= ~^buffer[7:0];
        3'b011: buffer <= 0;
        3'b100: buffer <= {1'b0, buffer[WIDTH-1:1]};
        3'b101: buffer <= {data_in[0], buffer[WIDTH-1:1]};
        3'b110: buffer <= {buffer[WIDTH-2:0], data_in[0]};
        3'b111: buffer <= {buffer[WIDTH-1:8], data_in[0], buffer[7:1]};
        default: ; // NOP
      endcase

  assign zero = (buffer == 0);
  assign lsb = buffer[0];
  assign low8 = buffer[7:0];
endmodule

module OutputController #(
  parameter STATE_WIDTH = 3
) (
  input [3:0] opcode,
  input [7:0] buffer_data,
  input [STATE_WIDTH-1:0] state,
  input zero_0,
  input zero_1,
  input alu_zero,
  input alu_lsb,
  output reg [7:0] out
);

  always @(*)
    begin
      out[7:5] = state;
      out[4] = zero_0;
      out[3] = zero_1;

      casez (opcode)
        4'b???0: out[2:0] = opcode[3:1];
        4'b??01: out[2:0] = {opcode[3:2], alu_lsb};
        4'b0011: out = buffer_data;
        default: out[2:0] = 0;
      endcase
    end

endmodule

module Controller #(
  parameter STATE_COUNT = 8,
  parameter INPUT_COUNT = 4,
  parameter COUNTER_WIDTH = 16
) (
  input clock,
  input rst_n,
  input prog_enable,
  input [INPUT_COUNT - 1:0] in,
  input [7:0] data_in,
  output [7:0] out,
  output reg [$clog2(STATE_COUNT) - 1:0] state
);

  localparam COUNTER_COUNT = 2;
  
  localparam STATE_WIDTH = $clog2(STATE_COUNT);
  
  localparam COND_WIDTH = 3;
  localparam COND_IS_ZERO_0 = 3'b000;
  localparam COND_IS_ZERO_1 = 3'b001;
  localparam COND_IS_ALU_ZERO = 3'b010;
  localparam COND_IS_ALU_LSB = 3'b011;
  
  localparam ACTION_WIDTH = 3 + 3;
  
  wire [STATE_WIDTH-1:0] jump_target;
  wire repeat_state;
  wire slow_mode;
  wire [3:0] output_opcode;
  wire [COND_WIDTH-1:0] cond;
  wire [ACTION_WIDTH-1:0] then_action;
  wire [ACTION_WIDTH-1:0] else_action;

  wire zero_0;
  wire zero_1;
  wire alu_zero;
  wire alu_lsb;

  wire cond_result = cond == COND_IS_ZERO_0 ? zero_0
                   : cond == COND_IS_ZERO_1 ? zero_1
                   : cond == COND_IS_ALU_ZERO ? alu_zero
                   : cond == COND_IS_ALU_LSB ? alu_lsb
                   : in[cond[1:0]];

  wire slow_mode_wait = slow_mode && !zero_1;

  wire [ACTION_WIDTH-1:0] action = cond_result ? then_action : else_action;
  wire [COUNTER_WIDTH * COUNTER_COUNT - 1:0] const_data;

  InstMem #(
    .STATE_COUNT(STATE_COUNT),
    .COND_WIDTH(COND_WIDTH),
    .OUTPUT_WIDTH(4),
    .ACTION_WIDTH(ACTION_WIDTH),
    .COUNTER_WIDTH(COUNTER_WIDTH),
    .COUNTER_COUNT(2)
  ) inst_mem (
    .clock(clock),
    .rst_n(rst_n),
    .prog_enable(prog_enable),
    .prog_data(data_in),
    .addr(state),
    .jump_target(jump_target),
    .repeat_state(repeat_state),
    .slow_mode(slow_mode),
    .output_opcode(output_opcode),
    .cond(cond),
    .then_action(then_action),
    .else_action(else_action),
    .const_data(const_data)
  );

  wire [2:0] counter_action = action[2:0];
  wire [2:0] alu_buffer_action = action[5:3];

  Counter2 #(
    .WIDTH(COUNTER_WIDTH)
  ) counter2 (
    .clock(clock),
    .rst_n(rst_n),
    .opcode(slow_mode_wait ? 3'b110 : counter_action),
    .const_0(const_data[COUNTER_WIDTH-1:0]),
    .const_1(const_data[COUNTER_WIDTH*2-1:COUNTER_WIDTH]),
    .data_in(data_in),
    .zero_0(zero_0),
    .zero_1(zero_1)
  );

  wire [7:0] alu_buffer_low8;

  AluBuffer alu_buffer (
    .clock(clock),
    .rst_n(rst_n),
    .opcode(slow_mode_wait ? 3'b0 : alu_buffer_action),
    .data_in(data_in),
    .low8(alu_buffer_low8),
    .zero(alu_zero),
    .lsb(alu_lsb)
  );

  OutputController #(
    .STATE_WIDTH(STATE_WIDTH)
  ) output_controller (
    .opcode(output_opcode),
    .buffer_data(alu_buffer_low8),
    .state(state),
    .zero_0(zero_0),
    .zero_1(zero_1),
    .alu_zero(alu_zero),
    .alu_lsb(alu_lsb),
    .out(out)
  );

  always @(posedge clock)
    if (!rst_n)
      state <= 0;
    else if (prog_enable)
      state <= 0;
    else if (!slow_mode_wait)
      if (cond_result)
        state <= jump_target;
      else
        state <= repeat_state ? state : state + 1;

endmodule
