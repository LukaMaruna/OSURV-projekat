import smbus
import time
import math

# Podešavanja za Clock Gen Click
I2C_BUS = 1
SI5351A_ADDRESS = 0x60  # I2C adresa
XTAL_FREQ = 25000000    # 25 MHz kristal
VCO_FREQ = 800000000    # Fiksna VCO frekvencija

def write_register(bus, address, reg, value):
    bus.write_byte_data(address, reg, value)

def read_register(bus, address, reg):
    return bus.read_byte_data(address, reg)

def initialize(bus, address):
    """Inicijalizacija Si5351: postavi kristal, PLLA na 800 MHz."""
    write_register(bus, address, 0xB7, 0xD2)  # 10 pF kristal
    write_register(bus, address, 0x0F, 0x00)  # XTAL za PLLA
    write_register(bus, address, 0xBB, 0xD0)  # Omogući fanout
    p1 = 128 * 32 - 512
    write_register(bus, address, 26, 0x00)
    write_register(bus, address, 27, 0x01)
    write_register(bus, address, 28, 0x00)
    write_register(bus, address, 29, (p1 >> 8) & 0xFF)
    write_register(bus, address, 30, p1 & 0xFF)
    write_register(bus, address, 22, 0x40)  # Integer mode
    write_register(bus, address, 0xB1, 0x20)  # Reset PLLA
    time.sleep(0.01)
    print("Ploča inicijalizovana.")

def set_frequency(bus, address, clk_num, freq):
    """Podesi frekvenciju na CLK0-CLK2."""
    if clk_num < 0 or clk_num > 2:
        print("Pogrešan CLK: Koristi 0, 1 ili 2.")
        return
    if freq < 2500 or freq > 200000000:
        print("Frekvencija van opsega: 2.5 kHz do 200 MHz.")
        return

    ms_div = VCO_FREQ / freq
    a = math.floor(ms_div)
    fractional = ms_div - a
    b = math.floor(fractional * 1048575)
    c = 1048575
    p1 = 128 * a + math.floor(128 * b / c) - 512
    p2 = 128 * b - c * math.floor(128 * b / c)
    p3 = c
    divby4 = 0x00 if a != 4 else 0x03
    integer_mode = 1 if b == 0 and a % 2 == 0 else 0

    base_reg = 42 + clk_num * 8
    control_reg = 16 + clk_num
    write_register(bus, address, base_reg, (p3 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 1, p3 & 0xFF)
    write_register(bus, address, base_reg + 2, (0 << 5) | (divby4 << 3) | ((p1 >> 16) & 0x03))
    write_register(bus, address, base_reg + 3, (p1 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 4, p1 & 0xFF)
    write_register(bus, address, base_reg + 5, (((p3 >> 16) & 0x0F) << 4) | ((p2 >> 16) & 0x0F))
    write_register(bus, address, base_reg + 6, (p2 >> 8) & 0xFF)
    write_register(bus, address, base_reg + 7, p2 & 0xFF)
    control_val = (0 << 7) | (integer_mode << 6) | (0 << 5) | (0 << 4) | (0x3 << 2) | 0x3
    write_register(bus, address, control_reg, control_val)
    write_register(bus, address, 0xB1, 0x20)  # Reset PLLA
    time.sleep(0.01)
    print(f"CLK{clk_num} postavljen na {freq} Hz.")

def user_command_loop(bus, address):
    print("\n=== Clock Gen Click Test ===")
    print("Komande:")
    print(" init    - Inicijalizuj ploču")
    print(" set <clk> <freq> - Podesi frekvenciju (npr. set 0 100000000)")
    print(" on <clk>  - Uključi CLK izlaz")
    print(" off <clk> - Isključi CLK izlaz")
    print(" read <reg> - Pročitaj vrednost registra (npr. read 0)")
    print(" status  - Proveri status Reg 0")
    print(" exit    - Izlaz\n")

    while True:
        cmd = input(">> ").strip().lower().split()
        if len(cmd) == 0:
            continue
        if cmd[0] == "exit":
            print("Izlaz.")
            break
        elif cmd[0] == "init":
            initialize(bus, address)
        elif cmd[0] == "set" and len(cmd) == 3:
            try:
                clk = int(cmd[1])
                freq = int(cmd[2])
                set_frequency(bus, address, clk, freq)
            except ValueError:
                print("Pogrešno: Koristi set <clk 0-2> <freq u Hz>")
        elif cmd[0] == "on" and len(cmd) == 2:
            try:
                clk = int(cmd[1])
                if 0 <= clk <= 2:
                    reg3 = read_register(bus, address, 0x03) & 0xF8
                    write_register(bus, address, 0x03, reg3 & ~(1 << clk))
                    print(f"CLK{clk} uključen")
                else:
                    print("CLK mora biti 0, 1 ili 2")
            except ValueError:
                print("Pogrešan CLK")
        elif cmd[0] == "off" and len(cmd) == 2:
            try:
                clk = int(cmd[1])
                if 0 <= clk <= 2:
                    reg3 = read_register(bus, address, 0x03) & 0xF8
                    write_register(bus, address, 0x03, reg3 | (1 << clk))
                    print(f"CLK{clk} isključen")
                else:
                    print("CLK mora biti 0, 1 ili 2")
            except ValueError:
                print("Pogrešan CLK")
        elif cmd[0] == "read" and len(cmd) == 2:
            try:
                reg = int(cmd[1])
                if 0 <= reg <= 255:
                    value = read_register(bus, address, reg)
                    print(f"Vrednost Reg 0x{reg:02X} = 0x{value:02X}")
                else:
                    print("Registar mora biti 0-255")
            except ValueError:
                print("Pogrešan registar")
        elif cmd[0] == "status":
            value = read_register(bus, address, 0x00)
            if value is not None:
                print(f"Status [0x00] = 0x{value:02X} (0x00 = OK)")
        else:
            print("Nepoznata komanda. Pokušaj: init, set, on, off, read, status, exit")

def main():
    bus = smbus.SMBus(I2C_BUS)
    try:
        bus.read_byte_data(SI5351A_ADDRESS, 0x00)
        print("Clock Gen Click detektovan na 0x60.")
        user_command_loop(bus, SI5351A_ADDRESS)
    except OSError:
        print("Clock Gen Click nije detektovan. Proveri I2C konekciju.")

if __name__ == "__main__":
    main()
