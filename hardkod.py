
import smbus
import time
import math

# I2C setup for Si5351A
I2C_BUS = 1                        # I2C bus number (typically 1 on Raspberry Pi)
SI5351A_ADDRESS = 0x60             # I2C address of the Si5351A clock generator
XTAL_FREQ = 25000000               # External crystal frequency: 25 MHz
VCO_FREQ = 800000000               # VCO frequency (output of PLL): fixed at 800 MHz

# ----------- I2C Register Access Helpers -----------

def write_register(bus, address, reg, value, retries=3):
    """Write a single byte to a register on the Si5351A with retries"""
    for attempt in range(retries):
        try:
            bus.write_byte_data(address, reg, value)
            # Verify write
            read_back = bus.read_byte_data(address, reg)
            if read_back != value:
                print(f"I2C write verification failed for Reg {reg}: wrote 0x{value:02X}, read 0x{read_back:02X} (attempt {attempt+1})")
                if attempt == retries - 1:
                    raise OSError(f"Write verification failed for Reg {reg} after {retries} attempts")
                time.sleep(0.01)
                continue
            return
        except OSError as e:
            print(f"I2C write error to Reg {reg}: {e} (attempt {attempt+1})")
            if attempt == retries - 1:
                raise
            time.sleep(0.01)

def read_register(bus, address, reg, retries=3):
    """Read a single byte from a register on the Si5351A with retries"""
    for attempt in range(retries):
        try:
            return bus.read_byte_data(address, reg)
        except OSError as e:
            print(f"I2C read error from Reg {reg}: {e} (attempt {attempt+1})")
            if attempt == retries - 1:
                raise
            time.sleep(0.01)

# ----------- Device Initialization -----------

def initialize(bus, address):
    """
    Initialize the Si5351A:
    - Perform full device reset with verification
    - Set crystal load capacitance
    - Set PLLA to 800 MHz
    - Configure fanout and PLL multiplier registers
    - Wait for PLL lock
    """
    print("Starting Si5351A initialization...")
    
    # Attempt full device reset
    try:
        write_register(bus, address, 177, 0xA0)  # PLLA_RST=1, PLLB_RST=1
        time.sleep(0.01)
    except OSError:
        print("Warning: Failed to write PLL reset (Reg 177). Attempting fallback initialization.")

    # Disable all outputs
    write_register(bus, address, 0x03, 0xFF)

    # Set crystal load capacitance to 10pF (Reg 183)
    write_register(bus, address, 0xB7, 0xD2)
    crystal_load = read_register(bus, address, 0xB7)
    print(f"Crystal load capacitance (Reg 183) = 0x{crystal_load:02X} (expected 0xD2)")

    # Route crystal input to PLLA
    write_register(bus, address, 0x0F, 0x00)

    # Enable fanout for crystal input
    write_register(bus, address, 0xBB, 0xD0)

    # Set PLLA multiplier to 800 MHz = 25 MHz * 32
    p1 = 128 * 32 - 512  # Integer mode: Feedback_Multisynth = 32
    write_register(bus, address, 26, 0x00)              # MSNA_P3[15:8]
    write_register(bus, address, 27, 0x01)              # MSNA_P3[7:0]
    write_register(bus, address, 28, 0x00)              # MSNA_P1[17:16] + MSNA_P2[19:16]
    write_register(bus, address, 29, (p1 >> 8) & 0xFF)  # MSNA_P1[15:8]
    write_register(bus, address, 30, p1 & 0xFF)         # MSNA_P1[7:0]
    write_register(bus, address, 31, 0x00)              # MSNA_P2[15:8]
    write_register(bus, address, 32, 0x00)              # MSNA_P2[7:0]
    write_register(bus, address, 33, 0x00)              # MSNA_P2[19:16] + reserved

    # Set PLLA to integer mode
    write_register(bus, address, 22, 0x40)

    # Reset PLLA
    try:
        write_register(bus, address, 0xB1, 0x20)
        time.sleep(0.01)
    except OSError:
        print("Warning: PLLA reset (Reg 177) failed. Continuing with initialization.")

    # Wait for PLLA lock (check LOL_A=0, SYS_INIT=0)
    for _ in range(20):
        status = read_register(bus, address, 0x00)
        if (status & 0x20) == 0 and (status & 0x80) == 0:
            break
        time.sleep(0.01)
    else:
        print(f"PLLA failed to lock. Status Reg 0 = 0x{status:02X}")
        return

    # Verify PLLA registers
    print("PLLA register dump for verification:")
    for reg in range(26, 34):
        val = read_register(bus, address, reg)
        print(f"Reg {reg} = 0x{val:02X}")

    print(f"Si5351A initialized and PLLA set to 800 MHz. Status Reg 0 = 0x{status:02X}")

# ----------- Frequency Configuration -----------

def set_frequency(bus, address, clk_num, freq):
    """
    Set output frequency on CLK0-CLK2.
    - Calculates Multisynth divider values
    - Programs registers for selected CLK output
    - Includes diagnostics for register verification
    """
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

    # Set control register: enable output, integer mode, Multisynth source, 8mA drive
    write_register(bus, address, control_reg, (integer_mode << 6) | (0x3 << 2) | 0x3)

    # Enable output
    reg3 = read_register(bus, address, 0x03) & 0xF8
    write_register(bus, address, 0x03, reg3 & ~(1 << clk_num))

    # Reset PLLA
    try:
        write_register(bus, address, 0xB1, 0x20)
        time.sleep(0.01)
    except OSError:
        print("Warning: PLLA reset (Reg 177) failed. Continuing.")

    # Verify PLLA lock
    status = read_register(bus, address, 0x00)
    if (status & 0x20) != 0 or (status & 0x80) != 0:
        print(f"PLLA lock failed after setting frequency. Status Reg 0 = 0x{status:02X}")

    # Diagnostic register dump
    print(f"CLK{clk_num} set to {freq} Hz: ms_div={ms_div:.2f}, R={r}, P1={p1}, P2={p2}, P3={p3}, r_div={r_div}, divby4={divby4}")
    print("Register dump for verification:")
    for i in range(8):
        val = read_register(bus, address, base_reg + i)
        print(f"Reg {base_reg+i} = 0x{val:02X}")
    val = read_register(bus, address, control_reg)
    print(f"Control Reg {control_reg} = 0x{val:02X}")
    val = read_register(bus, address, 0x03)
    print(f"Output Enable Reg 3 = 0x{val:02X}")
    print(f"Status Reg 0 = 0x{status:02X} (0x00 = OK)")

# ----------- User Command Loop -----------

def user_command_loop(bus, address):
    """
    Interactive command-line interface for controlling Si5351A.
    Supports initialization, setting frequency, enabling/disabling outputs, and reading registers.
    """
    print("\n=== Clock Gen Click CLI ===")
    print("Commands:")
    print(" init                 - Initialize Si5351A")
    print(" set <clk> <freq>     - Set CLK0–CLK2 to a specific frequency (e.g. set 0 1000000)")
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
            try:
                initialize(bus, address)
            except OSError:
                print("I2C error during initialization")

        elif cmd[0] == "set" and len(cmd) == 3:
            try:
                clk = int(cmd[1])
                freq = int(cmd[2])
                set_frequency(bus, address, clk, 4*freq)
            except ValueError:
                print("Usage: set <clk 0-2> <freq in Hz>")
            except OSError:
                print("I2C error during frequency setting")

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
            except OSError:
                print("I2C error during output enable")

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
            except OSError:
                print("I2C error during output disable")

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
            except OSError:
                print("I2C error during register read")

        elif cmd[0] == "status":
            try:
                value = read_register(bus, address, 0x00)
                print(f"Status [0x00] = 0x{value:02X} (0x00 = OK)")
            except OSError:
                print("I2C error during status read")

        else:
            print("Unknown command. Try: init, set, on, off, read, status, exit")

# ----------- Main Program Entry Point -----------

def main():
    # Open I2C bus
    try:
        bus = smbus.SMBus(I2C_BUS)
        # Try to read register 0 to check if device is responding
        bus.read_byte_data(SI5351A_ADDRESS, 0x00)
        print("Si5351A detected at address 0x60.")
        user_command_loop(bus, SI5351A_ADDRESS)
    except OSError as e:
        print(f"Si5351A not detected. Check I2C connection: {e}")

if __name__ == "__main__":
    main()
