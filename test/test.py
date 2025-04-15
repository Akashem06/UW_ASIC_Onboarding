# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Edge, RisingEdge, FallingEdge
from cocotb.triggers import ClockCycles
from cocotb.types import Logic
from cocotb.types import LogicArray

async def await_half_sclk(dut):
    """Wait for the SCLK signal to go high or low."""
    start_time = cocotb.utils.get_sim_time(units="ns")
    while True:
        await ClockCycles(dut.clk, 1)
        # Wait for half of the SCLK period (10 us)
        if (start_time + 100*100*0.5) < cocotb.utils.get_sim_time(units="ns"):
            break
    return

def ui_in_logicarray(ncs, bit, sclk):
    """Setup the ui_in value as a LogicArray."""
    return LogicArray(f"00000{ncs}{bit}{sclk}")

async def send_spi_transaction(dut, r_w, address, data):
    """
    Send an SPI transaction with format:
    - 1 bit for Read/Write
    - 7 bits for address
    - 8 bits for data
    
    Parameters:
    - r_w: boolean, True for write, False for read
    - address: int, 7-bit address (0-127)
    - data: LogicArray or int, 8-bit data
    """
    # Convert data to int if it's a LogicArray
    if isinstance(data, LogicArray):
        data_int = int(data)
    else:
        data_int = data
    # Validate inputs
    if address < 0 or address > 127:
        raise ValueError("Address must be 7-bit (0-127)")
    if data_int < 0 or data_int > 255:
        raise ValueError("Data must be 8-bit (0-255)")
    # Combine RW and address into first byte
    first_byte = (int(r_w) << 7) | address
    # Start transaction - pull CS low
    sclk = 0
    ncs = 0
    bit = 0
    # Set initial state with CS low
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    await ClockCycles(dut.clk, 1)
    # Send first byte (RW + Address)
    for i in range(8):
        bit = (first_byte >> (7-i)) & 0x1
        # SCLK low, set COPI
        sclk = 0
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
        # SCLK high, keep COPI
        sclk = 1
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
    # Send second byte (Data)
    for i in range(8):
        bit = (data_int >> (7-i)) & 0x1
        # SCLK low, set COPI
        sclk = 0
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
        # SCLK high, keep COPI
        sclk = 1
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
    # End transaction - return CS high
    sclk = 0
    ncs = 1
    bit = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    await ClockCycles(dut.clk, 600)
    return ui_in_logicarray(ncs, bit, sclk)

async def sample_pwm_signal(dut, signal, channel, num_cycles=2, timeout_ns=5000000):
    """
    Samples the PWM frequency

    Parameters:
    - signal: Signal to measure
    - channel: The PWM bit channel to measure
    - num_cycles: Number of cycles to sample
    - timeout_ns: Maximum time to sample PWM signal

    Returns:
        Frequency in HZ and Duty cycle as shown:
        freq, duty
    """
    clock_period_ns = 100
    last_val = (int(signal.value) >> channel) & 1

    rising_edges = []
    high_times = []
    low_times = []

    time_of_last_rise = None
    time_of_last_fall = None

    start_time = cocotb.utils.get_sim_time(units='ns')

    while len(rising_edges) - 1 < num_cycles:
        await ClockCycles(dut.clk, 1)
        now = cocotb.utils.get_sim_time(units='ns')

        curr_val = (int(signal.value) >> channel) & 1

        if now - start_time > timeout_ns:
            # Likely held low/high
            return 0, 1.0 if curr_val == 1 else 0.0

        if last_val == 0 and curr_val == 1: # Rising edge
            rising_edges.append(now)

            if time_of_last_fall is not None:
                low_times.append(now - time_of_last_fall)
            time_of_last_rise = now
    
        elif last_val == 1 and curr_val == 0: # Falling edge
            if time_of_last_rise is not None:
                high_times.append(now - time_of_last_rise)

            time_of_last_fall = now

        last_val = curr_val

    total_period = []
    for time1, time2 in zip(rising_edges, rising_edges[1:]):
        total_period.append(time2 - time1)

    avg_period = sum(total_period) / len(total_period)
    avg_high_time = sum(high_times) / len(high_times)

    if avg_period > 0:
        duty_cycle = avg_high_time / avg_period
        frequency = (1E9) / avg_period
    else:
        duty_cycle = 0
        frequency = 0

    return frequency, duty_cycle

@cocotb.test()
async def test_spi(dut):
    dut._log.info("Start SPI test")

    # Set the clock period to 100 ns (10 MHz)
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut._log.info("Reset")
    dut.ena.value = 1
    ncs = 1
    bit = 0
    sclk = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    dut._log.info("Test project behavior")
    dut._log.info("Write transaction, address 0x00, data 0xF0")
    ui_in_val = await send_spi_transaction(dut, 1, 0x00, 0xF0)  # Write transaction
    assert dut.uo_out.value == 0xF0, f"Expected 0xF0, got {dut.uo_out.value}"
    await ClockCycles(dut.clk, 1000) 

    dut._log.info("Write transaction, address 0x01, data 0xCC")
    ui_in_val = await send_spi_transaction(dut, 1, 0x01, 0xCC)  # Write transaction
    assert dut.uio_out.value == 0xCC, f"Expected 0xCC, got {dut.uio_out.value}"
    await ClockCycles(dut.clk, 100)

    dut._log.info("Write transaction, address 0x30 (invalid), data 0xAA")
    ui_in_val = await send_spi_transaction(dut, 1, 0x30, 0xAA)
    await ClockCycles(dut.clk, 100)

    dut._log.info("Read transaction (invalid), address 0x00, data 0xBE")
    ui_in_val = await send_spi_transaction(dut, 0, 0x30, 0xBE)
    assert dut.uo_out.value == 0xF0, f"Expected 0xF0, got {dut.uo_out.value}"
    await ClockCycles(dut.clk, 100)
    
    dut._log.info("Read transaction (invalid), address 0x41 (invalid), data 0xEF")
    ui_in_val = await send_spi_transaction(dut, 0, 0x41, 0xEF)
    await ClockCycles(dut.clk, 100)

    dut._log.info("Write transaction, address 0x02, data 0xFF")
    ui_in_val = await send_spi_transaction(dut, 1, 0x02, 0xFF)  # Write transaction
    await ClockCycles(dut.clk, 100)

    dut._log.info("Write transaction, address 0x04, data 0xCF")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0xCF)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("Write transaction, address 0x04, data 0xFF")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0xFF)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("Write transaction, address 0x04, data 0x00")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0x00)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("Write transaction, address 0x04, data 0x01")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0x01)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("SPI test completed successfully")

@cocotb.test()
async def test_pwm_freq(dut):
    dut._log.info("Start PWM Freq test")

    # Set the clock period to 100 ns (10 MHz)
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut._log.info("Reset")
    dut.ena.value = 1
    ncs = 1
    bit = 0
    sclk = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # Duty Cycle = 50% for sampling frequency
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0x80)

    for i in range(8):
        # Test every single channel seperately on the uo_out port
        ui_in_val = await send_spi_transaction(dut, 1, 0x00, 1 << i)
        ui_in_val = await send_spi_transaction(dut, 1, 0x02, 1 << i)
        freq, duty = await sample_pwm_signal(dut, dut.uo_out, channel=i)

        assert 2970 <= freq <= 3030, f"Expected Frequency between 2970-3030 Hz, got {freq} on channel {i}"

    # Turn off channels
    ui_in_val = await send_spi_transaction(dut, 1, 0x00, 0)
    ui_in_val = await send_spi_transaction(dut, 1, 0x02, 0)

    for i in range(8):
        # Test every single channel seperately on the uio_out port
        ui_in_val = await send_spi_transaction(dut, 1, 0x01, 1 << i)
        ui_in_val = await send_spi_transaction(dut, 1, 0x03, 1 << i)
        freq, duty = await sample_pwm_signal(dut, dut.uio_out, channel=i)

        assert 2970 <= freq <= 3030, f"Expected Frequency between 2970-3030 Hz, got {freq} on channel {i + 8}"
    
    # Turn off channels
    ui_in_val = await send_spi_transaction(dut, 1, 0x01, 0)
    ui_in_val = await send_spi_transaction(dut, 1, 0x03, 0)

    dut._log.info("PWM Frequency test completed successfully")

@cocotb.test()
async def test_pwm_duty(dut):
    dut._log.info("Start PWM Duty cycle test")

    # Set the clock period to 100 ns (10 MHz)
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut._log.info("Reset")
    dut.ena.value = 1
    ncs = 1
    bit = 0
    sclk = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    for i in range(8):
        # Test every single channel seperately on the uo_out port

        ui_in_val = await send_spi_transaction(dut, 1, 0x00, 1 << i)
        ui_in_val = await send_spi_transaction(dut, 1, 0x02, 1 << i)

        # 0% DUTY CYCLE TEST
        ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0)
        freq, duty = await sample_pwm_signal(dut, dut.uo_out, channel=i)

        assert duty == 0.0, f"Expected Duty cycle at 0%, got {duty} on channel {i}"

        # 50% DUTY CYCLE TEST
        ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0x80)
        freq, duty = await sample_pwm_signal(dut, dut.uo_out, channel=i)

        assert duty == 0.5, f"Expected Duty cycle at 50%, got {duty} on channel {i}"

        # 100% DUTY CYCLE TEST
        ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0xFF)
        freq, duty = await sample_pwm_signal(dut, dut.uo_out, channel=i)

        assert duty == 1.0, f"Expected Duty cycle at 100%, got {duty} on channel {i}"

    # Turn off channels
    ui_in_val = await send_spi_transaction(dut, 1, 0x00, 0)
    ui_in_val = await send_spi_transaction(dut, 1, 0x02, 0)

    for i in range(8):
        # Test every single channel seperately on the uo_out port

        ui_in_val = await send_spi_transaction(dut, 1, 0x01, 1 << i)
        ui_in_val = await send_spi_transaction(dut, 1, 0x03, 1 << i)

        # 0% DUTY CYCLE TEST
        ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0)
        freq, duty = await sample_pwm_signal(dut, dut.uio_out, channel=i)

        assert duty == 0.0, f"Expected Duty cycle at 0%, got {duty} on channel {i + 8}"

        # 50% DUTY CYCLE TEST
        ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0x80)
        freq, duty = await sample_pwm_signal(dut, dut.uio_out, channel=i)

        assert duty == 0.5, f"Expected Duty cycle at 50%, got {duty} on channel {i + 8}"

        # 100% DUTY CYCLE TEST
        ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0xFF)
        freq, duty = await sample_pwm_signal(dut, dut.uio_out, channel=i)

        assert duty == 1.0, f"Expected Duty cycle at 100%, got {duty} on channel {i + 8}"

    # Turn off channels
    ui_in_val = await send_spi_transaction(dut, 1, 0x01, 0)
    ui_in_val = await send_spi_transaction(dut, 1, 0x03, 0)

    dut._log.info("PWM Duty cycle test completed successfully")
