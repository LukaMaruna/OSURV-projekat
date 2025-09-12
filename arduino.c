#include <Wire.h>

#define MAX2870_I2C_ADDRESS 0x68  // MAX2870 I2C address 
#define BAUD_RATE 9600            // serial baud rate for communication with Python

void setup() {
  Serial.begin(BAUD_RATE); // Initialize serial communication (Python program)
  while (!Serial);         // Wait for serial to initialize

  Wire.begin();            // Initialize I2C communication (MAX2870)
  
  sendSuccessToPython("Arduino Nano is ready to receive commands...");
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readString();          // Read the command sent from Python

    if (command.length() > 0) {
      byte result = sendCommandToMAX2870(command);  // Send the string to MAX2870 over I2C
      if (result != 0) {
        sendErrorToPython("I2C transmission failed", result);
      } else {
        sendSuccessToPython("I2C transmission successful, command sent: " + command);
      }
    } else {
      sendErrorToPython("No command received", 0);
    }
  }
}

byte sendCommandToMAX2870(String command) {
  Wire.beginTransmission(MAX2870_I2C_ADDRESS);  // Start communication with MAX2870
  
  for (int i = 0; i < command.length(); i++) {  // Send each byte of the string, excluding the null terminator
    if (command[i] == '\0') {
      break;                                    // Stop sending when the null terminator is encountered
    }
    Wire.write(command[i]);                     // Send each byte of the string
  }

  byte result = Wire.endTransmission();         // Check if transmission was successful
  return result;                                // Return the error code (non-zero indicates failure)
}

void sendErrorToPython(String errorMessage, byte errorCode) {
  // Send a formatted error message and code to Python
  Serial.print("ERROR: ");
  Serial.print(errorMessage);
  Serial.print(" | Error Code: ");
  Serial.println(errorCode);
}

void sendSuccessToPython(String successMessage) {
  // Send a success message to Python
  Serial.print("SUCCESS: ");
  Serial.println(successMessage);
}