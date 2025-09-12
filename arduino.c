#include <Wire.h>

#define MAX2870_I2C_ADDRESS 0x68  // MAX2870 I2C address 
#define BAUD_RATE 9600            // serial baud rate for communication with Python
byte COMMAND_BYTE = 0x51;         //command byte for frequency setting

void setup() {
  Serial.begin(BAUD_RATE); // Initialize serial communication (Python program)
  while (!Serial);         // Wait for serial to initialize

  Wire.begin();            // Initialize I2C communication (MAX2870)
  
  Serial.println("Arduino Nano is ready to receive commands...");
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readString();       // Read the command sent from Python
    long frequency = extractFrequency(command); // Extract frequency
    if (frequency > 0) {
      // Valid frequency received, send to MAX2870
      byte result = sendFrequencyToMAX2870(frequency);
      if (result != 0) {
        sendErrorToPython("I2C transmission failed", result);
      } else {
        Serial.println("SUCCESS: Frequency set to: " + String(frequency));
      }
    } else {
      // Invalid frequency received, send error to Python
      sendErrorToPython("Invalid frequency command received", 1);
    }
  }
}

long extractFrequency(String command) {
  int spaceIndex = command.indexOf(' ');                                  // Find the space between command and the frequency value
  if (spaceIndex == -1) {
    sendErrorToPython("No space found between command and frequency", 1);
    return 0;                                                             // No space found, invalid command
  }

  String frequencyStr = command.substring(spaceIndex + 1);    // Get the frequency part of the command
  
  long frequency = frequencyStr.toInt();                      // Check if frequency is a valid integer
  if (frequency == 0 && frequencyStr != "0") {
    sendErrorToPython("Frequency is not a valid number", 1);
    return 0;                                                 
  }

  return frequency;
}

byte sendFrequencyToMAX2870(long frequency) {
  Wire.beginTransmission(MAX2870_I2C_ADDRESS);  // Start communication with MAX2870
  
  //******************************************
  // Example: Send frequency (customize as needed based on MAX2870's I2C protocol)
  byte highByte = (frequency >> 8) & 0xFF;  // Extract high byte of frequency
  byte lowByte = frequency & 0xFF;          // Extract low byte of frequency
  //******************************************

  Wire.write(COMMAND_BYTE);  // Send command byte
  Wire.write(highByte);      // Send the high byte
  Wire.write(lowByte);       // Send the low byte

  
  byte result = Wire.endTransmission(); // Check if transmission was successful
  if (result != 0) {
    return result;                      // Return the error code (non-zero indicates failure)
  }
  
  return 0;                             // Return 0 if no error
}

void sendErrorToPython(String errorMessage, byte errorCode) {
  // Send a formatted error message and code to Python
  Serial.print("ERROR: ");
  Serial.print(errorMessage);
  Serial.print(" | Error Code: ");
  Serial.println(errorCode);
}
