// Copyright (c) 2026 Can Joshua Lehmann
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

module ShiftReg#(
  parameter WIDTH = 8,
  parameter INPUT_WIDTH = 1
) (
  input clock,
  input rst_n,
  input write_enable,
  input [INPUT_WIDTH-1:0] write_data,
  output [WIDTH-1:0] read_data
);

  reg [WIDTH-1:0] data;

  always @(posedge clock)
    if (!rst_n)
      data <= {WIDTH{1'b0}};
    else
      if (write_enable)
        data <= {data[WIDTH - 1 - INPUT_WIDTH:0], write_data};

  assign read_data = data;
endmodule

module Mux #(
  parameter WIDTH = 8,
  parameter COUNT = 4
) (
  input [$clog2(COUNT)-1:0] addr,
  input [WIDTH * COUNT-1:0] data,
  output [WIDTH-1:0] out
);

  wire [WIDTH-1:0] words [COUNT];
  genvar i;
  for (i = 0; i < COUNT; i = i + 1) begin
    assign words[i] = data[(i+1)*WIDTH-1 -: WIDTH];
  end

  assign out = words[addr];
endmodule

module InstMem#(
  parameter INPUT_WIDTH = 1,
  parameter STATE_COUNT = 8,
  parameter COND_WIDTH = 1,
  parameter OUTPUT_WIDTH = 4,
  parameter ACTION_WIDTH = 1,
  parameter COUNTER_WIDTH = 16,
  parameter COUNTER_COUNT = 2
) (
  input clock,
  input rst_n,
  input prog_enable,
  input [INPUT_WIDTH-1:0] prog_data,
  // State
  input [$clog2(STATE_COUNT)-1:0] addr,
  output [$clog2(STATE_COUNT)-1:0] jump_target,
  output repeat_state,
  output slow_mode,
  output [OUTPUT_WIDTH-1:0] output_opcode,
  output [COND_WIDTH-1:0] cond_opcode,
  output [ACTION_WIDTH-1:0] then_action,
  output [ACTION_WIDTH-1:0] else_action,
  // Extended State
  output [$clog2(STATE_COUNT)-1:0] extended_state,
  output [COND_WIDTH-1:0] extended_cond_opcode,
  output [ACTION_WIDTH-1:0] extended_then_action,
  output [$clog2(STATE_COUNT)-1:0] extended_jump_target,
  // Constants
  output [COUNTER_WIDTH * COUNTER_COUNT - 1:0] const_data
);

  localparam STATE_WIDTH = $clog2(STATE_COUNT);
  localparam WORD_WIDTH = STATE_WIDTH + 1 + 1 + OUTPUT_WIDTH + COND_WIDTH + ACTION_WIDTH * 2;
  localparam MEM_WIDTH = COUNTER_WIDTH * COUNTER_COUNT + WORD_WIDTH * STATE_COUNT + STATE_WIDTH;
  localparam STATE_OFFSET = COUNTER_WIDTH * COUNTER_COUNT;

  wire [MEM_WIDTH-1:0] mem_data;

  ShiftReg #(
    .WIDTH(MEM_WIDTH),
    .INPUT_WIDTH(INPUT_WIDTH)
  ) shiftreg (
    .clock(clock),
    .rst_n(rst_n),
    .write_enable(prog_enable),
    .write_data(prog_data),
    .read_data(mem_data)
  );

  wire [WORD_WIDTH-1:0] word;

  Mux #(
    .WIDTH(WORD_WIDTH),
    .COUNT(STATE_COUNT)
  ) mux (
    .addr(addr),
    .data(mem_data[STATE_OFFSET +: WORD_WIDTH * STATE_COUNT]),
    .out(word)
  );

  assign const_data = mem_data[0 +: COUNTER_WIDTH * COUNTER_COUNT];

  assign jump_target = word[STATE_WIDTH-1:0];
  assign repeat_state = word[STATE_WIDTH];
  assign slow_mode = word[STATE_WIDTH + 1];
  assign output_opcode = word[STATE_WIDTH + 1 + 1 +: OUTPUT_WIDTH];
  assign cond_opcode = word[STATE_WIDTH + 1 + 1 + OUTPUT_WIDTH +: COND_WIDTH];
  assign then_action = word[STATE_WIDTH + 1 + 1 + OUTPUT_WIDTH + COND_WIDTH +: ACTION_WIDTH];
  assign else_action = word[STATE_WIDTH + 1 + 1 + OUTPUT_WIDTH + COND_WIDTH + ACTION_WIDTH +: ACTION_WIDTH];

  assign extended_state = mem_data[STATE_OFFSET + WORD_WIDTH * STATE_COUNT +: STATE_WIDTH];

  localparam EXTENDED_STATE_ID = STATE_COUNT - 1;
  wire [WORD_WIDTH-1:0] extended_word = mem_data[STATE_OFFSET + WORD_WIDTH * EXTENDED_STATE_ID +: WORD_WIDTH];
  
  assign extended_jump_target = extended_word[STATE_WIDTH-1:0];
  assign extended_cond_opcode = extended_word[STATE_WIDTH + 1 + 1 + OUTPUT_WIDTH +: COND_WIDTH];
  assign extended_then_action = extended_word[STATE_WIDTH + 1 + 1 + OUTPUT_WIDTH + COND_WIDTH +: ACTION_WIDTH];
endmodule