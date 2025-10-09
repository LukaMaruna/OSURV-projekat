def set_frequency(bus, address, clk_num, freq):
    if clk_num < 0 or clk_num > 2:
        print("Invalid CLK number: must be 0, 1, or 2.")
        return
    if freq < 2500 or freq > 200000000:
        print("Frequency out of range: 2.5 kHz to 200 MHz.")
        return

    # Calculate R divider for low frequencies
    if freq < 500000:
        for r in [1, 2, 4, 8, 16, 32, 64, 128]:
            ms_div = VCO_FREQ / (freq * r)
            if 8 <= ms_div <= 2048:
                break
        else:
            print("Cannot achieve frequency with valid divider.")
            return
        r_div = int(math.log2(r))
    else:
        r = 1
        r_div = 0
        ms_div = VCO_FREQ / freq

    # Handle high frequencies (150–200 MHz)
    if 150000000 < freq <= 200000000:
        ms_div = 4
        a = 4
        b = 0
        c = 1
        p1 = 0
        p2 = 0
        p3 = 1
        divby4 = 0x03
        integer_mode = 1
    else:
        a = math.floor(ms_div)
        fractional = ms_div - a
        b = math.floor(fractional * 1048575)
        c = 1048575
        p1 = 128 * a + math.floor(128 * b / c) - 512
        p2 = 128 * b - c * math.floor(128 * b / c)
        p3 = c
        divby4 = 0x00
        integer_mode = 1 if b == 0 and a % 2 == 0 else 0

    base_reg = 42 + clk_num * 8
    control_reg = 16 + clk_num

    # Write Multisynth registers
    write_register(bus, address, base_reg, (p3 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 1, p3 & 0xFF)
    write_register(bus, address, base_reg + 2, (r_div << 4) | (divby4 << 3) | ((p1 >> 16) & 0x03))
    write_register(bus, address, base_reg + 3, (p1 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 4, p1 & 0xFF)
    write_register(bus, address, base_reg + 5, (((p3 >> 16) & 0x0F) << 4) | ((p2 >> 16) & 0x0F))
    write_register(bus, address, base_reg + 6, (p2 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 7, p2 & 0xFF)

    # Configure control register (PLLA source, enable output)
    write_register(bus, address, control_reg, (integer_mode << 6) | (0x3 << 2) | 0x3)

    # Enable output
    reg3 = read_register(bus, address, 0x03) & 0xF8
    write_register(bus, address, 0x03, reg3 & ~(1 << clk_num))

    # Reset PLLA
    write_register(bus, address, 0xB1, 0x20)
    time.sleep(0.01)

    # Debug output
    print(f"CLK{clk_num} set to {freq} Hz: ms_div={ms_div}, R={r}, P1={p1}, P2={p2}, P3={p3}")
