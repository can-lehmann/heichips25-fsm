// SPDX-FileCopyrightText: © 2025 XXX Authors
// SPDX-License-Identifier: Apache-2.0

// Adapted from the Tiny Tapeout template

`default_nettype none

module heichips25_template (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

/*
    // List all unused inputs to prevent warnings
    wire _unused = &{ena, ui_in[7:1], uio_in[7:0]};

    logic [7:0] count;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            count <= '0;
        end else begin
            if (ui_in[0]) begin
                count <= count + 1;
            end
        end
    end
    
    assign uo_out  = count;
    assign uio_out = count;
    assign uio_oe  = '1;
*/

    localparam STATE_COUNT = 8;

    localparam CONST_WIDTH = 16;
    localparam CONST_COUNT = 2;
    
    localparam STATE_WIDTH = $clog2(STATE_COUNT);
    localparam COND_WIDTH = 1;
    localparam ACTION_WIDTH = 2 + $clog2(CONST_COUNT);

    localparam REG_COUNT = 1;

    reg [STATE_WIDTH-1:0] state;
    reg [CONST_WIDTH-1:0] reg_file [REG_COUNT-1:0];
    
    wire [STATE_WIDTH-1:0] jump_target;
    wire [COND_WIDTH-1:0] cond;
    wire [ACTION_WIDTH-1:0] then_action;
    wire [ACTION_WIDTH-1:0] else_action;

    wire [CONST_WIDTH-1:0] const_data;

    wire cond_result = cond ? ui_in[0] : reg_file[0] == 0;

    wire [ACTION_WIDTH-1:0] action = cond_result ? then_action : else_action;

    wire [$clog2(CONST_COUNT)-1:0] const_addr = action[ACTION_WIDTH-1:1];

    wire prog_enable = ui_in[7];

    InstMem #(
        .STATE_COUNT(STATE_COUNT),
        .COND_WIDTH(COND_WIDTH),
        .ACTION_WIDTH(ACTION_WIDTH),
        .CONST_WIDTH(CONST_WIDTH),
        .CONST_COUNT(CONST_COUNT)
    ) inst_mem (
        .clock(clk),
        .rst_n(rst_n),
        .prog_enable(prog_enable),
        .prog_data(ui_in[0]),
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

    always @(posedge clk)
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
    
    assign uo_out = { {(8-STATE_WIDTH){1'b0}}, state };

    assign uio_oe = '1;
    assign uio_out = 0;
    wire _unused = &{ena, uio_in[7:0], ui_in[6:1]};
endmodule
