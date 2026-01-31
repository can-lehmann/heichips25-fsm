// Copyright (c) 2026 Can Joshua Lehmann
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

module ShiftReg#(
  parameter WIDTH = 8
) (
  input clock,
  input rst_n,
  input write_enable,
  input write_data,
  output [WIDTH-1:0] read_data
);

  reg [WIDTH-1:0] data;

  integer i;
  always @(posedge clock)
    if (!rst_n)
      data <= {WIDTH{1'b0}};
    else
      if (write_enable)
        data <= {data[WIDTH-2:0], write_data};

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
  parameter STATE_COUNT = 8,
  parameter COND_WIDTH = 1,
  parameter ACTION_WIDTH = 1,
  parameter CONST_WIDTH = 16,
  parameter CONST_COUNT = 2
) (
  input clock,
  input rst_n,
  input prog_enable,
  input prog_data,
  // State
  input [$clog2(STATE_COUNT)-1:0] addr,
  output [$clog2(STATE_COUNT)-1:0] jump_target,
  output [COND_WIDTH-1:0] cond,
  output [ACTION_WIDTH-1:0] then_action,
  output [ACTION_WIDTH-1:0] else_action,
  // Constants
  input [$clog2(CONST_COUNT)-1:0] const_addr,
  output [CONST_WIDTH-1:0] const_data
);

  localparam STATE_WIDTH = $clog2(STATE_COUNT);
  localparam WORD_WIDTH = STATE_WIDTH + COND_WIDTH + ACTION_WIDTH * 2;
  localparam MEM_WIDTH = CONST_WIDTH * CONST_COUNT + WORD_WIDTH * STATE_COUNT;
  localparam STATE_OFFSET = CONST_WIDTH * CONST_COUNT;

  wire [MEM_WIDTH-1:0] mem_data;

  ShiftReg #(
    .WIDTH(MEM_WIDTH)
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

  Mux #(
    .WIDTH(CONST_WIDTH),
    .COUNT(CONST_COUNT)
  ) const_mux (
    .addr(const_addr),
    .data(mem_data[0 +: CONST_WIDTH * CONST_COUNT]),
    .out(const_data)
  );

  assign jump_target = word[STATE_WIDTH-1:0];
  assign cond = word[STATE_WIDTH +: COND_WIDTH];
  assign then_action = word[STATE_WIDTH + COND_WIDTH +: ACTION_WIDTH];
  assign else_action = word[STATE_WIDTH + COND_WIDTH + ACTION_WIDTH +: ACTION_WIDTH];
endmodule