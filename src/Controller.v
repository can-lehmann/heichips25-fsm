// Copyright (c) 2026 Can Joshua Lehmann
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

module Controller #(
  parameter STATE_COUNT = 8
) (
  input clock,
  input rst_n,
  input prog_enable,
  input prog_data,
  input [0:0] in,
  output reg [$clog2(STATE_COUNT) - 1:0] state
);

  localparam CONST_WIDTH = 16;
  localparam CONST_COUNT = 2;
  
  localparam STATE_WIDTH = $clog2(STATE_COUNT);
  localparam COND_WIDTH = 1;
  localparam ACTION_WIDTH = 2 + $clog2(CONST_COUNT);

  localparam REG_COUNT = 1;

  reg [CONST_WIDTH-1:0] reg_file [REG_COUNT-1:0];
  
  wire [STATE_WIDTH-1:0] jump_target;
  wire [COND_WIDTH-1:0] cond;
  wire [ACTION_WIDTH-1:0] then_action;
  wire [ACTION_WIDTH-1:0] else_action;

  wire [CONST_WIDTH-1:0] const_data;

  wire cond_result = cond ? in[0] : reg_file[0] == 0;

  wire [ACTION_WIDTH-1:0] action = cond_result ? then_action : else_action;

  wire [$clog2(CONST_COUNT)-1:0] const_addr = action[ACTION_WIDTH-1:1];

  InstMem #(
    .STATE_COUNT(STATE_COUNT),
    .COND_WIDTH(COND_WIDTH),
    .ACTION_WIDTH(ACTION_WIDTH),
    .CONST_WIDTH(CONST_WIDTH),
    .CONST_COUNT(CONST_COUNT)
  ) inst_mem (
    .clock(clock),
    .rst_n(rst_n),
    .prog_enable(prog_enable),
    .prog_data(prog_data),
    .addr(state),
    .jump_target(jump_target),
    .cond(cond),
    .then_action(then_action),
    .else_action(else_action),
    .const_addr(const_addr),
    .const_data(const_data)
  );

  integer i;

  task reset();
    begin
      state <= 0;
      for (i = 0; i < REG_COUNT; i = i + 1) begin
        reg_file[i] <= 0;
      end
    end
  endtask

  always @(posedge clock)
    if (!rst_n)
      reset();
    else if (prog_enable)
      reset();
    else
      begin
        if (cond_result)
          state <= jump_target;
        else
          state <= state + 1;
        
        case (action[1:0])
          2'b00: ; // NOP
          2'b01: reg_file[0] <= const_data;
          2'b10: reg_file[0] <= reg_file[0] - 1;
          2'b11: reg_file[0] <= reg_file[0] + 1;
        endcase
      end

endmodule
