/*
 * MoltBot Arduino Firmware v1.0.0
 * 
 * Firmware for MoltBot robotic arm/chassis controlled by LADA.
 * 
 * Features:
 * - JSON serial protocol (115200 baud)
 * - Servo control (arm joints, claw)
 * - DC motor control (wheels via L298N/L293D)
 * - Ultrasonic sensor (HC-SR04)
 * - Temperature sensor (DHT11/DHT22)
 * - Light sensor (LDR)
 * - LED/buzzer feedback
 * - Camera trigger
 * 
 * Hardware connections (customize as needed):
 * - Servos: pins 3, 5, 6, 9, 10
 * - Motors: pins 4, 7, 8, 11, 12, 13
 * - Ultrasonic: TRIG=A0, ECHO=A1
 * - DHT: pin 2
 * - LDR: A2
 * - Buzzer: A3
 * - LED: Built-in (13) or RGB pins
 * 
 * Protocol:
 * Send JSON commands terminated with newline.
 * Example: {"cmd":"ping"}\n
 * Response: {"status":"ok","msg":"pong"}\n
 */

#include <Servo.h>
#include <ArduinoJson.h>

// ============== PIN CONFIGURATION ==============
// Servos
#define SERVO_CLAW_PIN    3
#define SERVO_WRIST_PIN   5
#define SERVO_ELBOW_PIN   6
#define SERVO_SHOULDER_PIN 9
#define SERVO_BASE_PIN    10

// Motors (L298N)
#define MOTOR_L_EN  11
#define MOTOR_L_IN1 4
#define MOTOR_L_IN2 7
#define MOTOR_R_EN  12
#define MOTOR_R_IN1 8
#define MOTOR_R_IN2 13

// Sensors
#define ULTRASONIC_TRIG A0
#define ULTRASONIC_ECHO A1
#define LDR_PIN         A2
#define BUZZER_PIN      A3
#define DHT_PIN         2

// Camera
#define CAMERA_TRIGGER  A4

// ============== CONSTANTS ==============
#define SERIAL_BAUD 115200
#define JSON_BUFFER 256

// Servo angles
#define CLAW_OPEN     180
#define CLAW_CLOSED   0
#define ARM_HOME_BASE     90
#define ARM_HOME_SHOULDER 90
#define ARM_HOME_ELBOW    90
#define ARM_HOME_WRIST    90

// ============== GLOBALS ==============
Servo servoClaw;
Servo servoWrist;
Servo servoElbow;
Servo servoShoulder;
Servo servoBase;

StaticJsonDocument<JSON_BUFFER> jsonDoc;
char inputBuffer[JSON_BUFFER];
int bufferIndex = 0;

// ============== SETUP ==============
void setup() {
  Serial.begin(SERIAL_BAUD);
  
  // Initialize servos
  servoClaw.attach(SERVO_CLAW_PIN);
  servoWrist.attach(SERVO_WRIST_PIN);
  servoElbow.attach(SERVO_ELBOW_PIN);
  servoShoulder.attach(SERVO_SHOULDER_PIN);
  servoBase.attach(SERVO_BASE_PIN);
  
  // Initialize motors
  pinMode(MOTOR_L_EN, OUTPUT);
  pinMode(MOTOR_L_IN1, OUTPUT);
  pinMode(MOTOR_L_IN2, OUTPUT);
  pinMode(MOTOR_R_EN, OUTPUT);
  pinMode(MOTOR_R_IN1, OUTPUT);
  pinMode(MOTOR_R_IN2, OUTPUT);
  
  // Initialize sensors
  pinMode(ULTRASONIC_TRIG, OUTPUT);
  pinMode(ULTRASONIC_ECHO, INPUT);
  pinMode(LDR_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(CAMERA_TRIGGER, OUTPUT);
  
  // Home position
  armHome();
  motorsStop();
  
  // Ready signal
  tone(BUZZER_PIN, 1000, 100);
  delay(150);
  tone(BUZZER_PIN, 1500, 100);
  
  sendResponse("ok", "MoltBot ready");
}

// ============== MAIN LOOP ==============
void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    
    if (c == '\n' || c == '\r') {
      if (bufferIndex > 0) {
        inputBuffer[bufferIndex] = '\0';
        processCommand(inputBuffer);
        bufferIndex = 0;
      }
    } else if (bufferIndex < JSON_BUFFER - 1) {
      inputBuffer[bufferIndex++] = c;
    }
  }
}

// ============== COMMAND PROCESSING ==============
void processCommand(const char* json) {
  DeserializationError error = deserializeJson(jsonDoc, json);
  
  if (error) {
    sendError("JSON parse error");
    return;
  }
  
  const char* cmd = jsonDoc["cmd"];
  
  if (!cmd) {
    sendError("Missing cmd");
    return;
  }
  
  // Route command
  if (strcmp(cmd, "ping") == 0) {
    sendResponse("ok", "pong");
  }
  else if (strcmp(cmd, "status") == 0) {
    sendStatus();
  }
  else if (strcmp(cmd, "move") == 0) {
    handleMove();
  }
  else if (strcmp(cmd, "turn") == 0) {
    handleTurn();
  }
  else if (strcmp(cmd, "stop") == 0) {
    motorsStop();
    sendResponse("ok", "stopped");
  }
  else if (strcmp(cmd, "claw") == 0) {
    handleClaw();
  }
  else if (strcmp(cmd, "arm") == 0) {
    handleArm();
  }
  else if (strcmp(cmd, "sensor") == 0) {
    handleSensor();
  }
  else if (strcmp(cmd, "camera") == 0) {
    handleCamera();
  }
  else if (strcmp(cmd, "led") == 0) {
    handleLed();
  }
  else if (strcmp(cmd, "buzzer") == 0) {
    handleBuzzer();
  }
  else if (strcmp(cmd, "reset") == 0) {
    armHome();
    motorsStop();
    sendResponse("ok", "reset complete");
  }
  else {
    sendError("Unknown command");
  }
}

// ============== MOVEMENT ==============
void handleMove() {
  const char* dir = jsonDoc["direction"];
  float dist = jsonDoc["distance"] | 10.0;
  int speed = jsonDoc["speed"] | 200;
  
  if (!dir) {
    sendError("Missing direction");
    return;
  }
  
  // Calculate duration (rough approximation: 10cm/s at full speed)
  int duration = (dist / 10.0) * 1000 * (255.0 / speed);
  
  if (strcmp(dir, "forward") == 0) {
    motorsForward(speed);
  } else if (strcmp(dir, "backward") == 0) {
    motorsBackward(speed);
  } else {
    sendError("Invalid direction");
    return;
  }
  
  delay(duration);
  motorsStop();
  
  sendResponse("ok", "move complete");
}

void handleTurn() {
  const char* dir = jsonDoc["direction"];
  float angle = jsonDoc["angle"] | 90.0;
  int speed = jsonDoc["speed"] | 200;
  
  if (!dir) {
    sendError("Missing direction");
    return;
  }
  
  // Duration approximation (90° = 500ms at full speed)
  int duration = (angle / 90.0) * 500 * (255.0 / speed);
  
  if (strcmp(dir, "left") == 0) {
    motorsTurnLeft(speed);
  } else if (strcmp(dir, "right") == 0) {
    motorsTurnRight(speed);
  } else {
    sendError("Invalid direction");
    return;
  }
  
  delay(duration);
  motorsStop();
  
  sendResponse("ok", "turn complete");
}

void motorsForward(int speed) {
  analogWrite(MOTOR_L_EN, speed);
  analogWrite(MOTOR_R_EN, speed);
  digitalWrite(MOTOR_L_IN1, HIGH);
  digitalWrite(MOTOR_L_IN2, LOW);
  digitalWrite(MOTOR_R_IN1, HIGH);
  digitalWrite(MOTOR_R_IN2, LOW);
}

void motorsBackward(int speed) {
  analogWrite(MOTOR_L_EN, speed);
  analogWrite(MOTOR_R_EN, speed);
  digitalWrite(MOTOR_L_IN1, LOW);
  digitalWrite(MOTOR_L_IN2, HIGH);
  digitalWrite(MOTOR_R_IN1, LOW);
  digitalWrite(MOTOR_R_IN2, HIGH);
}

void motorsTurnLeft(int speed) {
  analogWrite(MOTOR_L_EN, speed);
  analogWrite(MOTOR_R_EN, speed);
  digitalWrite(MOTOR_L_IN1, LOW);
  digitalWrite(MOTOR_L_IN2, HIGH);
  digitalWrite(MOTOR_R_IN1, HIGH);
  digitalWrite(MOTOR_R_IN2, LOW);
}

void motorsTurnRight(int speed) {
  analogWrite(MOTOR_L_EN, speed);
  analogWrite(MOTOR_R_EN, speed);
  digitalWrite(MOTOR_L_IN1, HIGH);
  digitalWrite(MOTOR_L_IN2, LOW);
  digitalWrite(MOTOR_R_IN1, LOW);
  digitalWrite(MOTOR_R_IN2, HIGH);
}

void motorsStop() {
  analogWrite(MOTOR_L_EN, 0);
  analogWrite(MOTOR_R_EN, 0);
  digitalWrite(MOTOR_L_IN1, LOW);
  digitalWrite(MOTOR_L_IN2, LOW);
  digitalWrite(MOTOR_R_IN1, LOW);
  digitalWrite(MOTOR_R_IN2, LOW);
}

// ============== CLAW/ARM ==============
void handleClaw() {
  const char* action = jsonDoc["action"];
  
  if (!action) {
    sendError("Missing action");
    return;
  }
  
  if (strcmp(action, "open") == 0) {
    servoClaw.write(CLAW_OPEN);
  } else if (strcmp(action, "close") == 0) {
    servoClaw.write(CLAW_CLOSED);
  } else if (strcmp(action, "position") == 0) {
    int pos = jsonDoc["value"] | 90;
    servoClaw.write(constrain(pos, 0, 180));
  } else {
    sendError("Invalid claw action");
    return;
  }
  
  sendResponse("ok", "claw command sent");
}

void handleArm() {
  const char* action = jsonDoc["action"];
  
  if (action && strcmp(action, "home") == 0) {
    armHome();
    sendResponse("ok", "arm homed");
    return;
  }
  
  const char* joint = jsonDoc["joint"];
  int angle = jsonDoc["angle"] | 90;
  angle = constrain(angle, 0, 180);
  
  if (!joint) {
    sendError("Missing joint");
    return;
  }
  
  if (strcmp(joint, "base") == 0) {
    servoBase.write(angle);
  } else if (strcmp(joint, "shoulder") == 0) {
    servoShoulder.write(angle);
  } else if (strcmp(joint, "elbow") == 0) {
    servoElbow.write(angle);
  } else if (strcmp(joint, "wrist") == 0) {
    servoWrist.write(angle);
  } else {
    sendError("Invalid joint");
    return;
  }
  
  sendResponse("ok", "arm position set");
}

void armHome() {
  servoBase.write(ARM_HOME_BASE);
  servoShoulder.write(ARM_HOME_SHOULDER);
  servoElbow.write(ARM_HOME_ELBOW);
  servoWrist.write(ARM_HOME_WRIST);
  servoClaw.write(CLAW_OPEN);
  delay(500);
}

// ============== SENSORS ==============
void handleSensor() {
  const char* type = jsonDoc["type"];
  
  if (!type) {
    sendError("Missing sensor type");
    return;
  }
  
  StaticJsonDocument<128> response;
  response["status"] = "ok";
  
  if (strcmp(type, "ultrasonic") == 0) {
    response["value"] = readUltrasonic();
    response["unit"] = "cm";
  } 
  else if (strcmp(type, "temperature") == 0) {
    response["value"] = readTemperature();
    response["unit"] = "C";
  }
  else if (strcmp(type, "light") == 0) {
    response["value"] = analogRead(LDR_PIN);
    response["unit"] = "raw";
  }
  else if (strcmp(type, "battery") == 0) {
    // Approximate battery voltage (assumes voltage divider on A5)
    response["value"] = analogRead(A5) * 5.0 / 1023.0 * 2.0;
    response["unit"] = "V";
  }
  else {
    sendError("Unknown sensor type");
    return;
  }
  
  serializeJson(response, Serial);
  Serial.println();
}

float readUltrasonic() {
  digitalWrite(ULTRASONIC_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(ULTRASONIC_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(ULTRASONIC_TRIG, LOW);
  
  long duration = pulseIn(ULTRASONIC_ECHO, HIGH, 30000);
  return duration * 0.034 / 2.0;  // cm
}

float readTemperature() {
  // Simplified - implement DHT reading here
  // For now, return placeholder
  return 25.0;
}

// ============== CAMERA ==============
void handleCamera() {
  const char* action = jsonDoc["action"];
  
  if (!action) {
    sendError("Missing camera action");
    return;
  }
  
  if (strcmp(action, "capture") == 0 || strcmp(action, "trigger") == 0) {
    // Pulse camera trigger
    digitalWrite(CAMERA_TRIGGER, HIGH);
    delay(100);
    digitalWrite(CAMERA_TRIGGER, LOW);
    sendResponse("ok", "camera triggered");
  }
  else if (strcmp(action, "on") == 0) {
    digitalWrite(CAMERA_TRIGGER, HIGH);
    sendResponse("ok", "camera on");
  }
  else if (strcmp(action, "off") == 0) {
    digitalWrite(CAMERA_TRIGGER, LOW);
    sendResponse("ok", "camera off");
  }
  else {
    sendError("Invalid camera action");
  }
}

// ============== LED/BUZZER ==============
void handleLed() {
  const char* color = jsonDoc["color"];
  int brightness = jsonDoc["brightness"] | 255;
  
  // Simplified - assumes single LED on pin 13
  // Extend for RGB LED control
  if (color && strcmp(color, "off") == 0) {
    digitalWrite(LED_BUILTIN, LOW);
  } else {
    analogWrite(LED_BUILTIN, brightness);
  }
  
  sendResponse("ok", "led set");
}

void handleBuzzer() {
  int freq = jsonDoc["frequency"] | 1000;
  int duration = jsonDoc["duration"] | 200;
  
  tone(BUZZER_PIN, freq, duration);
  
  sendResponse("ok", "buzzer played");
}

// ============== STATUS ==============
void sendStatus() {
  StaticJsonDocument<256> response;
  response["status"] = "ok";
  response["firmware"] = "MoltBot v1.0.0";
  response["uptime_ms"] = millis();
  response["distance_cm"] = readUltrasonic();
  response["light"] = analogRead(LDR_PIN);
  
  serializeJson(response, Serial);
  Serial.println();
}

// ============== HELPERS ==============
void sendResponse(const char* status, const char* msg) {
  StaticJsonDocument<128> response;
  response["status"] = status;
  response["msg"] = msg;
  serializeJson(response, Serial);
  Serial.println();
}

void sendError(const char* msg) {
  StaticJsonDocument<128> response;
  response["status"] = "error";
  response["error"] = msg;
  serializeJson(response, Serial);
  Serial.println();
}
