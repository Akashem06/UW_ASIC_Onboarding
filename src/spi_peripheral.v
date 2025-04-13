/*
 * Copyright (c) 2024 Aryan Kashem
 * SPDX-License-Identifier: Apache-2.0
 */

 `default_nettype none

module spi_peripheral #(
    parameter SPI_CPOL = 0,
    parameter SPI_CPHA = 0,
    parameter MAX_ADDRESS = 7'b0000100
) (
    input  wire       clk,      // clock
    input  wire       rst_n,    // reset_n - low to reset

    // Peripheral hardware
    input  wire spi_sclk,
    input  wire spi_cs,
    input  wire spi_mosi,

    // Registers
    output reg [7:0] en_reg_out_7_0,
    output reg [7:0] en_reg_out_15_8,
    output reg [7:0] en_reg_pwm_7_0,
    output reg [7:0] en_reg_pwm_15_8,
    output reg [7:0] pwm_duty_cycle
);

typedef enum logic [1:0] {
    SPI_STATE_IDLE      = 2'b00,
    SPI_STATE_RECEIVE   = 2'b01
} spi_state_t;

spi_state_t state;

reg [7:0] shift_reg_in;
reg [3:0] bit_count; // Wrap around at 16
reg [6:0] reg_address;
reg read_write_bit;

reg spi_sclk_sync_0, spi_sclk_sync_1;
reg spi_cs_sync_0, spi_cs_sync_1;
reg spi_mosi_sync_0, spi_mosi_sync_1;

// The sync1 is raeding sample x[n-1]. sync 0 is reading sample x[n]
wire sclk_rising_edge = ~spi_sclk_sync_1 & spi_sclk_sync_0;
wire sclk_falling_edge = spi_sclk_sync_1 & ~spi_sclk_sync_0;

// The sync1 is raeding sample x[n-1]. sync 0 is reading sample x[n]
wire cs_rising_edge   = ~spi_cs_sync_1 &  spi_cs_sync_0;
wire cs_falling_edge  =  spi_cs_sync_1 & ~spi_cs_sync_0;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        // Reset peripheral
        spi_sclk_sync_0 <= 1'b0;
        spi_sclk_sync_1 <= 1'b0;
        spi_cs_sync_0 <= 1'b0;
        spi_cs_sync_1 <= 1'b0;
        spi_mosi_sync_0 <= 1'b0;
        spi_mosi_sync_1 <= 1'b0;

        state <= SPI_STATE_IDLE;

    end else begin
        // Sample clock, chip select, data, etc. Use FSM?
        spi_sclk_sync_0 <= spi_sclk;
        spi_sclk_sync_1 <= spi_sclk_sync_0;
        spi_cs_sync_0 <= spi_cs;
        spi_cs_sync_1 <= spi_cs_sync_0;
        spi_mosi_sync_0 <= spi_mosi;
        spi_mosi_sync_1 <= spi_mosi_sync_0;
    end
end

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state <= SPI_STATE_IDLE;
    end else begin
        case (state)
            SPI_STATE_IDLE: begin
                if (cs_falling_edge) begin
                    $display("Changing into receive state");
                    state <= SPI_STATE_RECEIVE;
                end
            end

            SPI_STATE_RECEIVE: begin
                if (bit_count == 4'd15) begin
                    state <= SPI_STATE_IDLE;
                end
            end
        endcase
    end
end

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        shift_reg_in <= 8'b0;
        bit_count <= 4'b0;
        reg_address <= 7'b0;
        read_write_bit <= 1'b0;
    end else begin
        case (state)
            SPI_STATE_IDLE: begin
                bit_count <= 4'd0;
            end

            SPI_STATE_RECEIVE: begin
                if (sclk_rising_edge) begin
                    // Shift data into register
                    shift_reg_in = {shift_reg_in[6:0], spi_mosi_sync_1};

                    bit_count = bit_count + 1;
                    $display("[SPI] WRITE -> Addr: %0d, Data: 0x%02x, BitCount: %0d", reg_address, {shift_reg_in[6:0], spi_mosi_sync_1}, bit_count);

                    if (bit_count == 1)
                        read_write_bit <= spi_mosi_sync_1;
                    else if (bit_count >= 1 && bit_count <= 8)
                        reg_address <= {reg_address[5:0], spi_mosi_sync_1};

                    // On 16th bit we write and update register value
                    if (bit_count == 4'd15 && read_write_bit == 1'b1) begin
                        $display("Done!");
                        case (reg_address)
                            7'd0: en_reg_out_7_0    <= {shift_reg_in[6:0], spi_mosi_sync_1};
                            7'd1: en_reg_out_15_8   <= {shift_reg_in[6:0], spi_mosi_sync_1};
                            7'd2: en_reg_pwm_7_0    <= {shift_reg_in[6:0], spi_mosi_sync_1};
                            7'd3: en_reg_pwm_15_8   <= {shift_reg_in[6:0], spi_mosi_sync_1};
                            7'd4: pwm_duty_cycle    <= {shift_reg_in[6:0], spi_mosi_sync_1};
                            default:;
                        endcase
                    end
                end
            end

        endcase
    end
end

endmodule