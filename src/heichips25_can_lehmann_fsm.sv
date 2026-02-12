// SPDX-FileCopyrightText: © 2025 XXX Authors
// SPDX-License-Identifier: Apache-2.0

// Adapted from the Tiny Tapeout template

`default_nettype none

module heichips25_can_lehmann_fsm (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

    localparam STATE_COUNT = 8;
    localparam STATE_WIDTH = $clog2(STATE_COUNT);

    wire [STATE_WIDTH - 1:0] state;
    wire [7:0] out;

    Controller #(
        .STATE_COUNT(STATE_COUNT)
    ) controller (
        .clock(clk),
        .rst_n(rst_n),
        .prog_enable(ui_in[6]),
        .prog_advance(ui_in[5]),
        .in(ui_in[3:0]),
        .data_in(uio_in[7:0]),
        .state(state),
        .out(out)
    );

    assign uo_out = out;

    assign uio_oe = 0; // All IOs are inputs in this example
    assign uio_out = 0; // Not driving any outputs
    
    wire _unused = &{ena, uio_in[7:0], ui_in[6:1], state};
endmodule
