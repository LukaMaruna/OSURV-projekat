import smbus
import time
import math

# I2C setup for Si5351A
I2C_BUS = 1                        # I2C bus number (typically 1 on Raspberry Pi)
SI5351A_ADDRESS = 0x60             # I2C address of the Si5351A clock generator
XTAL_FREQ = 25000000               # External crystal frequency: 25 MHz
VCO_FREQ = 800000000               # VCO frequency (output of PLL): fixed at 800 MHz

# ----------- I2C Register Access Helpers -----------

def write_register(bus, address, reg, value):
    """Write a single byte to a register on the Si5351A"""
    bus.write_byte_data(address, reg, value)

def read_register(bus, address, reg):
    """Read a single byte from a register on the Si5351A"""
    return bus.read_byte_data(address, reg)

# ----------- Device Initialization -----------

def initialize(bus, address):
    """
    Initialize the Si5351A:
    - Set crystal load capacitance
    - Set PLLA to 800 MHz
    - Configure fanout and PLL multiplier registers
    """
    # Set crystal load capacitance to 10pF (typical value)
    write_register(bus, address, 0xB7, 0xD2)

    # Route the crystal input to PLLA
    write_register(bus, address, 0x0F, 0x00)

    # Enable fanout for the crystal input
    write_register(bus, address, 0xBB, 0xD0)

    # Set PLLA multiplier to 800 MHz = 25 MHz * 32
    p1 = 128 * 32 - 512  # Formula from datasheet (integer mode, no fraction)

    # Write PLLA registers (26–30) for multiplier config
    write_register(bus, address, 26, 0x00)              # MSNA_P3[15:8]
    write_register(bus, address, 27, 0x01)              # MSNA_P3[7:0]
    write_register(bus, address, 28, 0x00)              # MSNA_P1[17:16] + MSNA_P2[19:16]
    write_register(bus, address, 29, (p1 >> 8) & 0xFF)  # MSNA_P1[15:8]
    write_register(bus, address, 30, p1 & 0xFF)         # MSNA_P1[7:0]

    # Set PLLA to use integer mode
    write_register(bus, address, 22, 0x40)

    # Reset PLLA to apply changes
    write_register(bus, address, 0xB1, 0x20)

    time.sleep(0.01)
    print("Si5351A initialized and PLLA set to 800 MHz.")

# ----------- Frequency Configuration -----------

def set_frequency(bus, address, clk_num, freq):
    """
    Set output frequency on CLK0-CLK2.
    - Calculates Multisynth divider values
    - Programs registers for selected CLK output
    """
    if clk_num < 0 or clk_num > 2:
        print("Invalid CLK number: must be 0, 1, or 2.")
        return

    if freq < 2500 or freq > 200000000:
        print("Frequency out of range: 2.5 kHz to 200 MHz.")
        return

    # Calculate divider ratio for Multisynth (VCO / desired output)
    ms_div = VCO_FREQ / freq
    a = math.floor(ms_div)                      # Integer part
    fractional = ms_div - a
    b = math.floor(fractional * 1048575)        # Fractional numerator
    c = 1048575                                 # Fractional denominator (fixed)

    # Convert a + b/c into register values using formula from datasheet
    p1 = 128 * a + math.floor(128 * b / c) - 512
    p2 = 128 * b - c * math.floor(128 * b / c)
    p3 = c

    # Special encoding for divide-by-4 mode
    divby4 = 0x00 if a != 4 else 0x03

    # Enable integer mode only if exact division and even number
    integer_mode = 1 if b == 0 and a % 2 == 0 else 0

    base_reg = 42 + clk_num * 8        # Base register for multisynth parameters
    control_reg = 16 + clk_num         # Control register for CLKx output

    # Write calculated multisynth divider values to registers
    write_register(bus, address, base_reg, (p3 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 1, p3 & 0xFF)
    write_register(bus, address, base_reg + 2, (divby4 << 3) | ((p1 >> 16) & 0x03))
    write_register(bus, address, base_reg + 3, (p1 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 4, p1 & 0xFF)
    write_register(bus, address, base_reg + 5, (((p3 >> 16) & 0x0F) << 4) | ((p2 >> 16) & 0x0F))
    write_register(bus, address, base_reg + 6, (p2 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 7, p2 & 0xFF)

    # Set control register: enable output, integer mode flag
    control_val = (integer_mode << 6) | (0x3 << 2) | 0x3
    write_register(bus, address, control_reg, control_val)

    # Reset PLLA to apply the new configuration
    write_register(bus, address, 0xB1, 0x20)
    time.sleep(0.01)
    print(f"CLK{clk_num} set to {freq} Hz.")

# ----------- User Command Loop -----------

def user_command_loop(bus, address):
    """
    Interactive command-line interface for controlling Si5351A.
    Supports initialization, setting frequency, enabling/disabling outputs, and reading registers.
    """
    print("\n=== Clock Gen Click CLI ===")
    print("Commands:")
    print(" init                 - Initialize Si5351A")
    print(" set <clk> <freq>     - Set CLK0–CLK2 to a specific frequency (e.g. set 0 100000000)")
    print(" on <clk>             - Enable clock output (CLK0–2)")
    print(" off <clk>            - Disable clock output (CLK0–2)")
    print(" read <reg>           - Read value of a register (e.g. read 0)")
    print(" status               - Show status register (0x00)")
    print(" exit                 - Exit CLI\n")

    while True:
        cmd = input(">> ").strip().lower().split()
        if not cmd:
            continue

        if cmd[0] == "exit":
            print("Exiting.")
            break

        elif cmd[0] == "init":
            initialize(bus, address)

        elif cmd[0] == "set" and len(cmd) == 3:
            try:
                clk = int(cmd[1])
                freq = int(cmd[2])
                set_frequency(bus, address, clk, freq)
            except ValueError:
                print("Usage: set <clk 0-2> <freq in Hz>")

        elif cmd[0] == "on" and len(cmd) == 2:
            try:
                clk = int(cmd[1])
                if 0 <= clk <= 2:
                    reg3 = read_register(bus, address, 0x03) & 0xF8
                    write_register(bus, address, 0x03, reg3 & ~(1 << clk))
                    print(f"CLK{clk} enabled")
                else:
                    print("CLK number must be 0, 1, or 2")
            except ValueError:
                print("Invalid CLK number")

        elif cmd[0] == "off" and len(cmd) == 2:
            try:
                clk = int(cmd[1])
                if 0 <= clk <= 2:
                    reg3 = read_register(bus, address, 0x03) & 0xF8
                    write_register(bus, address, 0x03, reg3 | (1 << clk))
                    print(f"CLK{clk} disabled")
                else:
                    print("CLK number must be 0, 1, or 2")
            except ValueError:
                print("Invalid CLK number")

        elif cmd[0] == "read" and len(cmd) == 2:
            try:
                reg = int(cmd[1])
                if 0 <= reg <= 255:
                    value = read_register(bus, address, reg)
                    print(f"Register 0x{reg:02X} = 0x{value:02X}")
                else:
                    print("Register must be between 0 and 255")
            except ValueError:
                print("Invalid register")

        elif cmd[0] == "status":
            value = read_register(bus, address, 0x00)
            print(f"Status [0x00] = 0x{value:02X} (0x00 = OK)")

        else:
            print("Unknown command. Try: init, set, on, off, read, status, exit")

# ----------- Main Program Entry Point -----------

def main():
    # Open I2C bus
    bus = smbus.SMBus(I2C_BUS)
    try:
        # Try to read register 0 to check if device is responding
        bus.read_byte_data(SI5351A_ADDRESS, 0x00)
        print("Si5351A detected at address 0x60.")
        user_command_loop(bus, SI5351A_ADDRESS)
    except OSError:
        print("Si5351A not detected. Check I2C connection.")

if __name__ == "__main__":
    main()
