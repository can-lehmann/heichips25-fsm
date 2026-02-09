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
  input [3:0] opcode,
  input [7:0] data_in,
  output zero,
  output lsb
);

  // Opcodes
  // 0000: NOP
  // 0001: Load data_in into buffer[7:0]
  // 0010: Load data_in into buffer[15:8]
  // 0011: Clear buffer
  // 0100: Shift buffer right by 1, inserting 0 at the left
  // 0101: Shift buffer right by 1, inserting data_in[0] at the left
  // 0110: Shift buffer left by 1, inserting data_in[0] at the right
  // 0111: Shift buffer[7:0] right by 1, inserting data_in[0] at buffer[7]
  // 1000: Decrement buffer
  // 1001: NOT buffer
  // 1011: OR buffer with data_in
  // 1100: XOR buffer with data_in
  // 1101: Set buffer[8] to parity of buffer[7:0]
  // 1110: Load data_in into buffer[23:16]

  reg [WIDTH-1:0] buffer;

  always @(posedge clock)
    if (!rst_n)
      buffer <= 0;
    else
      case (opcode)
        4'b0000: ; // NOP
        4'b0001: buffer <= {buffer[WIDTH-1:8], data_in};
        4'b0010: buffer <= {buffer[WIDTH-1:16], data_in, buffer[7:0]};
        4'b1110: buffer <= {data_in, buffer[15:0]};
        4'b0011: buffer <= 0;
        4'b0100: buffer <= {1'b0, buffer[WIDTH-1:1]};
        4'b0101: buffer <= {data_in[0], buffer[WIDTH-1:1]};
        4'b0110: buffer <= {buffer[WIDTH-2:0], data_in[0]};
        4'b0111: buffer <= {buffer[WIDTH-1:8], data_in[0], buffer[7:1]};
        4'b1000: buffer <= buffer - 1;
        4'b1001: buffer <= ~buffer;
        4'b1011: buffer <= {buffer[WIDTH-1:8], buffer[7:0] | data_in};
        4'b1100: buffer <= {buffer[WIDTH-1:8], buffer[7:0] ^ data_in};
        4'b1101: buffer[8] <= ~^buffer[7:0];
        default: ; // NOP
      endcase

  assign zero = (buffer == 0);
  assign lsb = buffer[0];
endmodule

module Controller #(
  parameter STATE_COUNT = 8,
  parameter INPUT_COUNT = 4,
  parameter COUNTER_WIDTH = 16
) (
  input clock,
  input rst_n,
  input prog_enable,
  input prog_data,
  input [INPUT_COUNT - 1:0] in,
  input [7:0] data_in,
  output reg [$clog2(STATE_COUNT) - 1:0] state
);

  localparam COUNTER_COUNT = 2;
  
  localparam STATE_WIDTH = $clog2(STATE_COUNT);
  
  localparam COND_WIDTH = 3;
  localparam COND_IS_ZERO_0 = 3'b000;
  localparam COND_IS_ZERO_1 = 3'b001;
  localparam COND_IS_ALU_ZERO = 3'b010;
  localparam COND_IS_ALU_LSB = 3'b011;
  localparam COND_INPUT_0 = 3'b100;
  
  localparam ACTION_WIDTH = 3 + 4;
  
  wire [STATE_WIDTH-1:0] jump_target;
  wire repeat_state;
  wire slow_mode;
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
                   : in[cond - COND_INPUT_0];

  wire slow_mode_wait = slow_mode && !zero_1;

  wire [ACTION_WIDTH-1:0] action = cond_result ? then_action : else_action;
  wire [COUNTER_WIDTH * COUNTER_COUNT - 1:0] const_data;

  InstMem #(
    .STATE_COUNT(STATE_COUNT),
    .COND_WIDTH(COND_WIDTH),
    .ACTION_WIDTH(ACTION_WIDTH),
    .COUNTER_WIDTH(COUNTER_WIDTH),
    .COUNTER_COUNT(2)
  ) inst_mem (
    .clock(clock),
    .rst_n(rst_n),
    .prog_enable(prog_enable),
    .prog_data(prog_data),
    .addr(state),
    .jump_target(jump_target),
    .repeat_state(repeat_state),
    .slow_mode(slow_mode),
    .cond(cond),
    .then_action(then_action),
    .else_action(else_action),
    .const_data(const_data)
  );

  wire [2:0] counter_action = action[2:0];
  wire [3:0] alu_buffer_action = action[6:3];

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

  AluBuffer alu_buffer (
    .clock(clock),
    .rst_n(rst_n),
    .opcode(slow_mode_wait ? 4'b0 : alu_buffer_action),
    .data_in(data_in),
    .zero(alu_zero),
    .lsb(alu_lsb)
  );

  task reset();
    begin
      state <= 0;
    end
  endtask

  always @(posedge clock)
    if (!rst_n)
      reset();
    else if (prog_enable)
      reset();
    else if (!slow_mode_wait)
      if (cond_result)
        state <= jump_target;
      else
        state <= repeat_state ? state : state + 1;

endmodule
