import smbus
import time
import math

# I2C setup for Si5351A (unchanged)
I2C_BUS = 1
SI5351A_ADDRESS = 0x60
XTAL_FREQ = 25000000
VCO_FREQ = 800000000

# ----------- I2C Register Access Helpers -----------
# (Unchanged from previous version)
def write_register(bus, address, reg, value, retries=5, skip_verify=False):
    for attempt in range(retries):
        try:
            bus.write_byte_data(address, reg, value)
            if skip_verify or reg == 0xB1 or reg == 1 or reg == 187:
                return
            read_back = bus.read_byte_data(address, reg)
            if read_back != value:
                print(f"I2C write verification failed for Reg {reg}: wrote 0x{value:02X}, read 0x{read_back:02X} (attempt {attempt+1})")
                if attempt == retries - 1:
                    raise OSError(f"Write verification failed for Reg {reg} after {retries} attempts")
                time.sleep(0.05)
                continue
            return
        except OSError as e:
            print(f"I2C write error to Reg {reg}: {e} (attempt {attempt+1})")
            if attempt == retries - 1:
                raise
            time.sleep(0.05)

def read_register(bus, address, reg, retries=5):
    for attempt in range(retries):
        try:
            return bus.read_byte_data(address, reg)
        except OSError as e:
            print(f"I2C read error from Reg {reg}: {e} (attempt {attempt+1})")
            if attempt == retries - 1:
                raise
            time.sleep(0.05)

# ----------- Device Initialization -----------
# (Unchanged from previous version)
def initialize(bus, address):
    print("Starting Si5351A initialization...")
    print("Waiting for Si5351A to complete system initialization (SYS_INIT=0)...")
    for _ in range(100):
        try:
            status = read_register(bus, address, 0x00)
            if (status & 0x80) == 0:
                print(f"Device ready. Status Reg 0 = 0x{status:02X}")
                break
            time.sleep(0.05)
        except OSError:
            time.sleep(0.05)
    else:
        print("Timeout: Si5351A initialization did not complete (SYS_INIT stuck at 1). Check power/connections.")
        return False

    revid = status & 0x03
    print(f"Device revision (REVID[1:0]) = {revid} (expected 0 or 1 for Si5351A)")
    write_register(bus, address, 2, 0x18)
    write_register(bus, address, 1, 0x00, skip_verify=True)
    write_register(bus, address, 149, 0x00)
    write_register(bus, address, 0x03, 0xFF)
    write_register(bus, address, 0xB7, 0xD2)
    crystal_load = read_register(bus, address, 0xB7)
    if crystal_load != 0xD2:
        print(f"Warning: Crystal load capacitance (Reg 183) = 0x{crystal_load:02X} (expected 0xD2 for 10pF)")
        print("Check crystal (25 MHz, 10 pF load) and connections.")
        return False

    write_register(bus, address, 19, 0x80)
    write_register(bus, address, 20, 0x80)
    write_register(bus, address, 21, 0x80)
    write_register(bus, address, 22, 0xC0)
    write_register(bus, address, 23, 0x80)
    write_register(bus, address, 0x0F, 0x00)
    write_register(bus, address, 0xBB, 0x50, skip_verify=True)

    p1 = 128 * 32 - 512
    write_register(bus, address, 26, 0x00)
    write_register(bus, address, 27, 0x01)
    write_register(bus, address, 28, 0x00)
    write_register(bus, address, 29, (p1 >> 8) & 0xFF)
    write_register(bus, address, 30, p1 & 0xFF)
    write_register(bus, address, 31, 0x00)
    write_register(bus, address, 32, 0x00)
    write_register(bus, address, 33, 0x00)

    expected_vals = [0x00, 0x01, 0x00, (p1 >> 8) & 0xFF, p1 & 0xFF, 0x00, 0x00, 0x00]
    for i, reg in enumerate(range(26, 34)):
        val = read_register(bus, address, reg)
        if val != expected_vals[i]:
            print(f"PLLA config mismatch: Reg {reg} = 0x{val:02X} (expected 0x{expected_vals[i]:02X})")

    try:
        write_register(bus, address, 0xB1, 0x20, skip_verify=True)
        time.sleep(0.1)
        val = read_register(bus, address, 0xB1)
        if val != 0x00:
            print(f"Warning: PLLA reset verification failed (Reg 177 = 0x{val:02X})")
    except OSError:
        print("Warning: PLLA reset (Reg 177) failed. Continuing.")

    for attempt in range(3):
        for _ in range(50):
            status = read_register(bus, address, 0x00)
            if (status & 0xA0) == 0:
                print(f"PLLA locked successfully. Status Reg 0 = 0x{status:02X}")
                print("PLLA register dump for verification:")
                for reg in range(26, 34):
                    val = read_register(bus, address, reg)
                    print(f"Reg {reg} = 0x{val:02X}")
                print("Si5351A initialized successfully.")
                return True
            time.sleep(0.05)
        print(f"PLLA lock attempt {attempt+1} failed. Status Reg 0 = 0x{status:02X}")
        write_register(bus, address, 0xB7, 0xD2)
        write_register(bus, address, 0xB1, 0x20, skip_verify=True)
        time.sleep(0.1)
    print("PLLA failed to lock after retries. Status Reg 0 = 0x{status:02X}")
    print("Possible causes: Incorrect crystal frequency (not 25 MHz), wrong load capacitance, or hardware issue.")
    print(f"Current crystal settings: Reg 183 = 0x{read_register(bus, address, 0xB7):02X} (expected 0xD2)")
    return False

# ----------- Frequency Configuration -----------
# (Unchanged from previous version)
def set_frequency(bus, address, clk_num, freq):
    if clk_num < 0 or clk_num > 2:
        print("Invalid CLK number: must be 0, 1, or 2.")
        return
    if freq < 2500 or freq > 200000000:
        print("Frequency out of range: 2.5 kHz to 200 MHz.")
        return

    r = 1
    r_div = 0
    ms_div = VCO_FREQ / freq
    if freq < 500000:
        for r_val in [1, 2, 4, 8, 16, 32, 64, 128]:
            temp_ms_div = VCO_FREQ / (freq * r_val)
            if 8 <= temp_ms_div <= 2048:
                r = r_val
                ms_div = temp_ms_div
                break
        else:
            print("Cannot achieve frequency with valid divider.")
            return
        r_div = int(math.log2(r))
    else:
        ms_div = VCO_FREQ / freq

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
        if b == 0:
            c = 1
        p1 = 128 * a + math.floor(128 * b / c) - 512
        p2 = 128 * b - c * math.floor(128 * b / c)
        p3 = c
        divby4 = 0x00
        integer_mode = 1 if b == 0 and a % 2 == 0 else 0

    base_reg = 42 + clk_num * 8
    control_reg = 16 + clk_num

    write_register(bus, address, base_reg, (p3 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 1, p3 & 0xFF)
    write_register(bus, address, base_reg + 2, (r_div << 4) | (divby4 << 2) | ((p1 >> 16) & 0x03))
    write_register(bus, address, base_reg + 3, (p1 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 4, p1 & 0xFF)
    write_register(bus, address, base_reg + 5, (((p3 >> 16) & 0x0F) << 4) | ((p2 >> 16) & 0x0F))
    write_register(bus, address, base_reg + 6, (p2 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 7, p2 & 0xFF)

    write_register(bus, address, control_reg, (integer_mode << 6) | (0 << 5) | (0 << 4) | (0x3 << 2) | 0x3)

    reg3 = read_register(bus, address, 0x03) & 0xF8
    write_register(bus, address, 0x03, reg3 & ~(1 << clk_num))

    try:
        write_register(bus, address, 0xB1, 0x20, skip_verify=True)
        time.sleep(0.1)
        status = read_register(bus, address, 0x00)
        if (status & 0x20) != 0 or (status & 0x80) != 0:
            print(f"PLLA lock failed after setting frequency. Status Reg 0 = 0x{status:02X}")
            print("Possible causes: Incorrect Multisynth settings, crystal issue, or PLL instability.")
        else:
            print(f"PLLA locked successfully after frequency set. Status Reg 0 = 0x{status:02X}")
    except OSError:
        print("Warning: PLLA reset (Reg 177) failed. Continuing.")

    print(f"CLK{clk_num} set to {freq} Hz: ms_div={ms_div:.2f}, R={r}, P1={p1}, P2={p2}, P3={p3}, r_div={r_div}, divby4={divby4}")
    print("Register dump for verification:")
    for i in range(8):
        val = read_register(bus, address, base_reg + i)
        print(f"Reg {base_reg+i} = 0x{val:02X}")
    val = read_register(bus, address, control_reg)
    print(f"Control Reg {control_reg} = 0x{val:02X}")
    val = read_register(bus, address, 0x03)
    print(f"Output Enable Reg 3 = 0x{val:02X}")
    val = read_register(bus, address, 0x00)
    print(f"Status Reg 0 = 0x{val:02X} (0x00 = OK, LOS_XTAL=0x10)")

# ----------- Reset and Disable Clocks -----------

def reset_and_disable_clocks(bus, address):
    """
    Reset Si5351A and disable all clock outputs to leave the board in a clean state.
    """
    print("Resetting Si5351A and disabling all clock outputs...")
    try:
        # Disable all outputs (CLK0–CLK7)
        write_register(bus, address, 0x03, 0xFF)
        print("All clock outputs disabled (Reg 3 = 0xFF)")

        # Power down all clock outputs (CLK0–CLK7)
        for reg in range(16, 24):
            write_register(bus, address, reg, 0x80)  # Set CLKx_PDN=1
        print("All clock outputs powered down (Reg 16–23 = 0x80)")

        # Reset PLLA and PLLB
        write_register(bus, address, 0xB1, 0xA0, skip_verify=True)  # PLLA_RST=1, PLLB_RST=1
        time.sleep(0.1)
        print("PLLA and PLLB reset (Reg 177 = 0xA0)")

        # Clear sticky interrupts
        write_register(bus, address, 1, 0x00, skip_verify=True)
        print("Sticky interrupts cleared (Reg 1 = 0x00)")

        # Verify status
        status = read_register(bus, address, 0x00)
        print(f"Final status Reg 0 = 0x{status:02X} (0x00 = OK, LOS_XTAL=0x10)")
        print("Si5351A reset and clocks disabled successfully.")
    except OSError as e:
        print(f"Error during reset and disable: {e}")
        print("Check I2C connection and try again.")

# ----------- User Command Loop -----------

def user_command_loop(bus, address):
    """
    Interactive command-line interface for controlling Si5351A.
    Enhanced exit command to reset and disable clocks.
    """
    print("\n=== Clock Gen Click CLI ===")
    print("Commands:")
    print(" init                 - Initialize Si5351A")
    print(" set <clk> <freq>     - Set CLK0–CLK2 to a specific frequency (e.g. set 0 1000000)")
    print(" on <clk>             - Enable clock output (CLK0–2)")
    print(" off <clk>            - Disable clock output (CLK0–2)")
    print(" read <reg>           - Read value of a register (e.g. read 0)")
    print(" status               - Show status register (0x00)")
    print(" exit                 - Reset Si5351A, disable all clocks, and exit CLI\n")

    while True:
        cmd = input(">> ").strip().lower().split()
        if not cmd:
            continue

        if cmd[0] == "exit":
            print("Exiting CLI and resetting Si5351A...")
            reset_and_disable_clocks(bus, address)
            print("Program terminated.")
            break

        elif cmd[0] == "init":
            try:
                if initialize(bus, address):
                    print("Initialization completed successfully.")
                else:
                    print("Initialization failed. Check hardware and crystal settings.")
            except OSError:
                print("I2C error during initialization")

        elif cmd[0] == "set" and len(cmd) == 3:
            try:
                clk = int(cmd[1])
                freq = int(cmd[2])
                set_frequency(bus, address, clk, freq)
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
                print(f"Status [0x00] = 0x{value:02X} (0x00 = OK, LOS_XTAL=0x10)")
            except OSError:
                print("I2C error during status read")

        else:
            print("Unknown command. Try: init, set, on, off, read, status, exit")

# ----------- Main Program Entry Point -----------

def main():
    try:
        bus = smbus.SMBus(I2C_BUS)
        bus.read_byte_data(SI5351A_ADDRESS, 0x00)
        print("Si5351A detected at address 0x60.")
        user_command_loop(bus, SI5351A_ADDRESS)
    except OSError as e:
        print(f"Si5351A not detected. Check I2C connection: {e}")

if __name__ == "__main__":
    main()
