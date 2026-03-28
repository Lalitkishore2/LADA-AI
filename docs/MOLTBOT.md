# MoltBot Robot Integration Guide

MoltBot is LADA's optional physical robot extension — a voice-controlled robot arm with wheels for real-world interaction.

## Hardware Requirements

### Core Components

| Component | Model | Purpose |
|-----------|-------|---------|
| Microcontroller | Arduino Mega 2560 / ESP32 | Main controller |
| Motor Driver | L298N / TB6612FNG | Wheel motor control |
| Servo Controller | PCA9685 (optional) | Multi-servo control |
| DC Motors | 2x 12V geared motors | Wheels |
| Servo Motors | 2-4x MG996R or SG90 | Arm joints + claw |
| Battery | 11.1V LiPo 3S 2200mAh | Power supply |
| USB Cable | USB-B to USB-A | Serial communication |

### Optional Components

- Ultrasonic sensor (HC-SR04) for obstacle detection
- IR sensors for line following
- Camera module (ESP32-CAM) for vision
- LED strip (WS2812B) for status indication

## Wiring Diagram

```
                    ┌─────────────────────────────┐
                    │      Arduino Mega 2560       │
                    │                             │
 ┌──────────┐       │  2 ─────── Motor1 IN1      │       ┌──────────┐
 │  L298N   │◄──────│  3 ─────── Motor1 IN2      │──────►│  Motor   │
 │  Driver  │◄──────│  4 ─────── Motor2 IN1      │       │  Left    │
 │          │◄──────│  5 ─────── Motor2 IN2      │       └──────────┘
 │          │       │                             │
 │  ENA ────│◄──────│  6 ─────── Enable A (PWM)  │       ┌──────────┐
 │  ENB ────│◄──────│  7 ─────── Enable B (PWM)  │──────►│  Motor   │
 └──────────┘       │                             │       │  Right   │
                    │  9 ─────── Base Servo       │       └──────────┘
 ┌──────────┐       │ 10 ─────── Shoulder Servo  │
 │  Servos  │◄──────│ 11 ─────── Elbow Servo     │
 │          │◄──────│ 12 ─────── Claw Servo      │
 └──────────┘       │                             │
                    │ A0 ─────── Battery Voltage  │
                    │                             │
                    │ USB ────► Computer         │
                    └─────────────────────────────┘
```

## Firmware Installation

### 1. Install Arduino IDE

Download from [arduino.cc](https://www.arduino.cc/en/software)

### 2. Install Required Libraries

```
Servo (built-in)
```

### 3. Upload Firmware

1. Open `integrations/moltbot_firmware.ino` in Arduino IDE
2. Select Board: **Arduino Mega 2560** (or your board)
3. Select Port: **COM3** (or your port)
4. Click **Upload**

### 4. Verify Connection

```bash
# Test serial communication
python -c "
import serial
ser = serial.Serial('COM3', 115200, timeout=1)
ser.write(b'PING\n')
print(ser.readline().decode())
ser.close()
"
# Should print: PONG
```

## LADA Configuration

Add to `.env`:

```bash
# MoltBot Configuration
MOLTBOT_PORT=COM3          # Serial port (COM3 on Windows, /dev/ttyUSB0 on Linux)
MOLTBOT_BAUD=115200        # Baud rate (must match firmware)
MOLTBOT_ENABLED=true       # Enable MoltBot integration
```

## Voice Commands

Once configured, control MoltBot with voice:

| Command | Action |
|---------|--------|
| "Move forward" | Drive forward 1 meter |
| "Move backward" | Drive backward 1 meter |
| "Turn left" | Rotate 90° left |
| "Turn right" | Rotate 90° right |
| "Open claw" | Open gripper |
| "Close claw" | Close gripper |
| "Grab that" | Open, move forward, close |
| "Wave hello" | Arm wave animation |
| "Stop" | Emergency stop |
| "Robot status" | Report battery, position |

## Serial Protocol

LADA communicates with MoltBot over serial using simple text commands:

### Command Format

```
COMMAND:arg1,arg2,...\n
```

### Commands

| Command | Arguments | Description |
|---------|-----------|-------------|
| `PING` | - | Connection test |
| `MOVE` | speed,duration_ms | Move forward/backward |
| `TURN` | speed,duration_ms | Turn left/right |
| `SERVO` | id,angle | Set servo position |
| `CLAW` | position | 0=closed, 180=open |
| `STATUS` | - | Get status |
| `STOP` | - | Emergency stop |
| `LED` | r,g,b | Set status LED |
| `BATTERY` | - | Get battery voltage |
| `HOME` | - | Move arm to home position |

### Response Format

```
OK:data\n
ERROR:message\n
```

### Examples

```
MOVE:255,1000     # Full speed forward for 1 second
TURN:-128,500     # Half speed left turn for 0.5 seconds
SERVO:0,90        # Move base servo to 90 degrees
CLAW:180          # Open claw fully
STATUS            # Returns: OK:battery=11.2,position=home,claw=open
```

## Python API

```python
from integrations.moltbot_controller import MoltBotController

bot = MoltBotController()

# Movement
bot.move_forward(speed=0.5, duration=1.0)
bot.turn_right(angle=90)

# Arm control
bot.set_servo("base", 45)
bot.set_servo("shoulder", 90)
bot.claw_open()
bot.claw_close()

# Status
status = bot.get_status()
print(f"Battery: {status['battery']}V")

# Disconnect
bot.disconnect()
```

## Tool Registry Integration

MoltBot tools are registered in `modules/tool_registry.py`:

```python
# Available tools
moltbot_move       # Move forward/backward
moltbot_turn       # Turn left/right
moltbot_claw       # Open/close claw
moltbot_servo      # Control servo
moltbot_status     # Get status
moltbot_led        # Set LED color
moltbot_home       # Home position
moltbot_execute    # Run action sequence
```

## Safety Features

### Emergency Stop

- Send `STOP` command
- Pull USB cable
- Press physical stop button (if installed)

### Watchdog Timer

Firmware includes 5-second watchdog:
- If no command received for 5 seconds, motors stop
- Prevents runaway if connection drops

### Servo Limits

Default safe ranges (configurable in firmware):

| Servo | Min | Max | Home |
|-------|-----|-----|------|
| Base | 0° | 180° | 90° |
| Shoulder | 30° | 150° | 90° |
| Elbow | 20° | 160° | 90° |
| Claw | 0° | 180° | 90° |

### Battery Monitoring

- Low battery warning at 10.5V
- Auto-shutdown at 10.0V (protects LiPo cells)

## Troubleshooting

### "MoltBot not responding"

1. Check USB connection
2. Verify correct COM port in `.env`
3. Check baud rate matches firmware (115200)
4. Try Arduino Serial Monitor to test

### "Servos jittering"

- Insufficient power supply
- Add capacitor (470µF) across servo power
- Use separate BEC for servos

### "Motors not moving"

- Check motor driver wiring
- Verify enable pins connected
- Check motor driver power supply

### "Commands execute slowly"

- Reduce serial buffer size
- Use faster baud rate
- Check for serial port conflicts

## Customization

### Adding New Actions

1. Add command handler in `moltbot_firmware.ino`:
```cpp
else if (cmd == "DANCE") {
  // Your dance routine
  Serial.println("OK:dancing");
}
```

2. Add Python method in `moltbot_controller.py`:
```python
def dance(self) -> str:
    return self._send_command("DANCE")
```

3. Add tool in `tool_registry.py`:
```python
{
    "name": "moltbot_dance",
    "description": "Make MoltBot dance",
    "parameters": {"type": "object", "properties": {}}
}
```

### Custom Servo Configuration

Edit in `moltbot_firmware.ino`:
```cpp
#define BASE_PIN 9
#define SHOULDER_PIN 10
#define ELBOW_PIN 11
#define CLAW_PIN 12

#define BASE_MIN 0
#define BASE_MAX 180
// ... etc
```

## Related Files

- `integrations/moltbot_controller.py` - Python controller
- `integrations/moltbot_firmware.ino` - Arduino firmware
- `modules/agents/robot_agent.py` - AI robot agent
- `modules/tool_registry.py` - Tool definitions
