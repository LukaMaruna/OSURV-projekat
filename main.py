import serial
import time

# Global variables for configuration
COM_PORT = 'COM3'  # COM port 
BAUD_RATE = 9600   # Baud rate for serial communication
TIMEOUT = 1        # Timeout for serial read

def connect_to_arduino():
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=TIMEOUT) # Establish serial connection 
        print(f"Connected to Arduino on {COM_PORT} at {BAUD_RATE} baud.")
        return ser
    except Exception as e:
        print(f"Error connecting to Arduino: {e}")
        return None

def send_command_to_arduino(ser, command):
    try:
        # Send command to Arduino via serial
        print(f"Sending command: {command}")
        ser.write(command.encode())                 # Convert command string to bytes
        time.sleep(0.1)                             # Short delay to ensure Arduino receives the command
        response = ser.readline().decode().strip()  # Read the response from Arduino
        return response
    except Exception as e:
        print(f"Error sending command: {e}")
        return None

def main():
    ser = connect_to_arduino()                             # Connect to Arduino

    if not ser:
        return                                             # If no connection, exit the program

    while True:
        user_input = input("Enter a command or 'exit' to quit: ")

        if user_input.lower() == 'exit':
            print("Exiting program...")
            break
        
        
        response = send_command_to_arduino(ser, user_input) # Send the command to Arduino and get response
        
        if response:
            print(f"Arduino response: {response}")

    ser.close()                                             # Close the serial connection when done

if __name__ == "__main__":
    main()
