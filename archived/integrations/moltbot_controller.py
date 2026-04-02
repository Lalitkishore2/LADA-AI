"""LADA MoltBot Controller

Serial communication controller for MoltBot robotic arm/chassis.

Features:
- Auto-detect COM port
- JSON command protocol
- Servo control (arm, claw)
- Motor control (wheels)
- Sensor reading (ultrasonic, temperature)
- Camera trigger
- Connection health monitoring

Environment variables:
- MOLTBOT_PORT: Serial port (default: auto-detect)
- MOLTBOT_BAUD: Baud rate (default: 115200)
- MOLTBOT_TIMEOUT: Command timeout in seconds (default: 5)
- MOLTBOT_RECONNECT: Auto-reconnect on disconnect (default: true)

Usage:
    from integrations.moltbot_controller import MoltBotController
    
    bot = MoltBotController()
    bot.connect()
    bot.move_forward(10)  # Move 10cm
    bot.open_claw()
    bot.close_claw()
    bot.read_sensor("ultrasonic")
"""

from __future__ import annotations

import os
import json
import time
import logging
import threading
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Optional dependency
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    serial = None
    SERIAL_AVAILABLE = False


class MoltBotState(Enum):
    """MoltBot connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MoltBotConfig:
    """MoltBot configuration."""
    port: Optional[str] = None  # None = auto-detect
    baud_rate: int = 115200
    timeout: float = 5.0
    auto_reconnect: bool = True
    reconnect_interval: float = 5.0
    health_check_interval: float = 10.0
    
    @classmethod
    def from_env(cls) -> "MoltBotConfig":
        """Load config from environment."""
        return cls(
            port=os.getenv("MOLTBOT_PORT"),  # None means auto-detect
            baud_rate=int(os.getenv("MOLTBOT_BAUD", "115200")),
            timeout=float(os.getenv("MOLTBOT_TIMEOUT", "5")),
            auto_reconnect=os.getenv("MOLTBOT_RECONNECT", "true").lower() == "true",
        )


@dataclass
class SensorReading:
    """Sensor data from MoltBot."""
    sensor_type: str
    value: float
    unit: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class MoltBotStatus:
    """MoltBot status information."""
    connected: bool
    port: Optional[str]
    state: MoltBotState
    battery_level: Optional[float] = None
    firmware_version: Optional[str] = None
    last_command: Optional[str] = None
    last_response: Optional[Dict] = None
    error_message: Optional[str] = None


class MoltBotController:
    """Serial controller for MoltBot robotic arm/chassis.
    
    Communicates with Arduino-based MoltBot via JSON over serial.
    """
    
    # Arduino identifiers for auto-detection
    ARDUINO_VIDS = ["2341", "1A86", "10C4", "0403", "2A03"]  # Common Arduino vendor IDs
    
    def __init__(self, config: Optional[MoltBotConfig] = None):
        """Initialize MoltBot controller.
        
        Args:
            config: Configuration object
        """
        if not SERIAL_AVAILABLE:
            logger.warning("[MoltBot] pyserial not installed. Install with: pip install pyserial")
        
        self.config = config or MoltBotConfig.from_env()
        self._serial: Optional["serial.Serial"] = None
        self._state = MoltBotState.DISCONNECTED
        self._lock = threading.Lock()
        self._reconnect_thread: Optional[threading.Thread] = None
        self._health_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Event callbacks
        self._on_connect: List[Callable] = []
        self._on_disconnect: List[Callable] = []
        self._on_error: List[Callable[[str], None]] = []
        self._on_sensor: List[Callable[[SensorReading], None]] = []
        
        # Status tracking
        self._last_command: Optional[str] = None
        self._last_response: Optional[Dict] = None
        self._error_message: Optional[str] = None
        
        logger.info("[MoltBot] Controller initialized")
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to MoltBot."""
        return self._state == MoltBotState.CONNECTED and self._serial is not None
    
    @property
    def status(self) -> MoltBotStatus:
        """Get current status."""
        return MoltBotStatus(
            connected=self.is_connected,
            port=self._serial.port if self._serial else None,
            state=self._state,
            last_command=self._last_command,
            last_response=self._last_response,
            error_message=self._error_message,
        )
    
    def _detect_port(self) -> Optional[str]:
        """Auto-detect MoltBot serial port.
        
        Returns:
            Port name or None
        """
        if not SERIAL_AVAILABLE:
            return None
        
        ports = list(serial.tools.list_ports.comports())
        logger.debug(f"[MoltBot] Found {len(ports)} serial ports")
        
        for port in ports:
            # Check for Arduino vendor IDs
            if port.vid and f"{port.vid:04X}" in self.ARDUINO_VIDS:
                logger.info(f"[MoltBot] Auto-detected Arduino: {port.device}")
                return port.device
            
            # Check for common Arduino descriptions
            if any(keyword in (port.description or "").lower() 
                   for keyword in ["arduino", "ch340", "cp210", "ftdi"]):
                logger.info(f"[MoltBot] Auto-detected: {port.device} ({port.description})")
                return port.device
        
        # Fallback: return first available port
        if ports:
            logger.warning(f"[MoltBot] No Arduino found, using: {ports[0].device}")
            return ports[0].device
        
        logger.error("[MoltBot] No serial ports found")
        return None
    
    def connect(self) -> bool:
        """Connect to MoltBot.
        
        Returns:
            True if connected successfully
        """
        if not SERIAL_AVAILABLE:
            logger.error("[MoltBot] pyserial not available")
            return False
        
        with self._lock:
            if self.is_connected:
                return True
            
            self._state = MoltBotState.CONNECTING
            
            # Get port
            port = self.config.port or self._detect_port()
            if not port:
                self._state = MoltBotState.ERROR
                self._error_message = "No serial port found"
                return False
            
            try:
                self._serial = serial.Serial(
                    port=port,
                    baudrate=self.config.baud_rate,
                    timeout=self.config.timeout,
                )
                
                # Wait for Arduino to reset
                time.sleep(2)
                
                # Flush any startup garbage
                self._serial.reset_input_buffer()
                
                # Send handshake
                response = self._send_command({"cmd": "ping"})
                if response and response.get("status") == "ok":
                    self._state = MoltBotState.CONNECTED
                    logger.info(f"[MoltBot] Connected to {port}")
                    
                    # Start health check
                    self._start_health_check()
                    
                    # Notify listeners
                    for cb in self._on_connect:
                        try:
                            cb()
                        except Exception:
                            pass
                    
                    return True
                else:
                    raise Exception("Handshake failed")
                    
            except Exception as e:
                logger.error(f"[MoltBot] Connection failed: {e}")
                self._state = MoltBotState.ERROR
                self._error_message = str(e)
                if self._serial:
                    try:
                        self._serial.close()
                    except Exception:
                        pass
                    self._serial = None
                return False
    
    def disconnect(self):
        """Disconnect from MoltBot."""
        self._stop_event.set()
        
        with self._lock:
            if self._serial:
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None
            
            self._state = MoltBotState.DISCONNECTED
        
        logger.info("[MoltBot] Disconnected")
        
        # Notify listeners
        for cb in self._on_disconnect:
            try:
                cb()
            except Exception:
                pass
    
    def _send_command(self, command: Dict) -> Optional[Dict]:
        """Send command to MoltBot.
        
        Args:
            command: Command dict
            
        Returns:
            Response dict or None
        """
        if not self._serial:
            return None
        
        try:
            # Serialize command
            cmd_str = json.dumps(command) + "\n"
            self._last_command = command.get("cmd", "unknown")
            
            # Send
            self._serial.write(cmd_str.encode())
            self._serial.flush()
            
            # Read response
            response_str = self._serial.readline().decode().strip()
            if response_str:
                self._last_response = json.loads(response_str)
                return self._last_response
            
            return None
            
        except Exception as e:
            logger.error(f"[MoltBot] Command error: {e}")
            self._error_message = str(e)
            return None
    
    def send(self, cmd: str, **params) -> Optional[Dict]:
        """Send command with parameters.
        
        Args:
            cmd: Command name
            **params: Command parameters
            
        Returns:
            Response dict or None
        """
        with self._lock:
            if not self.is_connected:
                logger.warning("[MoltBot] Not connected")
                return None
            
            command = {"cmd": cmd, **params}
            return self._send_command(command)
    
    def _start_health_check(self):
        """Start health check thread."""
        self._stop_event.clear()
        
        def health_loop():
            while not self._stop_event.is_set():
                time.sleep(self.config.health_check_interval)
                
                if self._stop_event.is_set():
                    break
                
                with self._lock:
                    if self.is_connected:
                        response = self._send_command({"cmd": "ping"})
                        if not response or response.get("status") != "ok":
                            logger.warning("[MoltBot] Health check failed")
                            self._state = MoltBotState.ERROR
                            
                            if self.config.auto_reconnect:
                                self._start_reconnect()
        
        self._health_thread = threading.Thread(target=health_loop, daemon=True)
        self._health_thread.start()
    
    def _start_reconnect(self):
        """Start reconnection attempts."""
        def reconnect_loop():
            while not self._stop_event.is_set():
                time.sleep(self.config.reconnect_interval)
                
                if self._stop_event.is_set():
                    break
                
                logger.info("[MoltBot] Attempting reconnect...")
                if self.connect():
                    break
        
        self._reconnect_thread = threading.Thread(target=reconnect_loop, daemon=True)
        self._reconnect_thread.start()
    
    # ─────────────────────────────────────────────────────────────────
    # Movement Commands
    # ─────────────────────────────────────────────────────────────────
    
    def move_forward(self, distance_cm: float) -> bool:
        """Move forward.
        
        Args:
            distance_cm: Distance in centimeters
            
        Returns:
            True if command sent
        """
        response = self.send("move", direction="forward", distance=distance_cm)
        return response is not None and response.get("status") == "ok"
    
    def move_backward(self, distance_cm: float) -> bool:
        """Move backward.
        
        Args:
            distance_cm: Distance in centimeters
            
        Returns:
            True if command sent
        """
        response = self.send("move", direction="backward", distance=distance_cm)
        return response is not None and response.get("status") == "ok"
    
    def turn_left(self, degrees: float) -> bool:
        """Turn left.
        
        Args:
            degrees: Rotation angle
            
        Returns:
            True if command sent
        """
        response = self.send("turn", direction="left", angle=degrees)
        return response is not None and response.get("status") == "ok"
    
    def turn_right(self, degrees: float) -> bool:
        """Turn right.
        
        Args:
            degrees: Rotation angle
            
        Returns:
            True if command sent
        """
        response = self.send("turn", direction="right", angle=degrees)
        return response is not None and response.get("status") == "ok"
    
    def stop(self) -> bool:
        """Emergency stop all motors.
        
        Returns:
            True if command sent
        """
        response = self.send("stop")
        return response is not None and response.get("status") == "ok"
    
    # ─────────────────────────────────────────────────────────────────
    # Arm/Claw Commands
    # ─────────────────────────────────────────────────────────────────
    
    def open_claw(self) -> bool:
        """Open the claw/gripper.
        
        Returns:
            True if command sent
        """
        response = self.send("claw", action="open")
        return response is not None and response.get("status") == "ok"
    
    def close_claw(self) -> bool:
        """Close the claw/gripper.
        
        Returns:
            True if command sent
        """
        response = self.send("claw", action="close")
        return response is not None and response.get("status") == "ok"
    
    def set_claw_position(self, position: int) -> bool:
        """Set claw position (0-180 degrees).
        
        Args:
            position: Servo angle (0=closed, 180=open)
            
        Returns:
            True if command sent
        """
        response = self.send("claw", action="position", value=max(0, min(180, position)))
        return response is not None and response.get("status") == "ok"
    
    def set_arm_position(self, joint: str, angle: int) -> bool:
        """Set arm joint position.
        
        Args:
            joint: Joint name (base, shoulder, elbow, wrist)
            angle: Target angle (0-180)
            
        Returns:
            True if command sent
        """
        response = self.send("arm", joint=joint, angle=max(0, min(180, angle)))
        return response is not None and response.get("status") == "ok"
    
    def arm_home(self) -> bool:
        """Move arm to home position.
        
        Returns:
            True if command sent
        """
        response = self.send("arm", action="home")
        return response is not None and response.get("status") == "ok"
    
    # ─────────────────────────────────────────────────────────────────
    # Sensor Commands
    # ─────────────────────────────────────────────────────────────────
    
    def read_sensor(self, sensor_type: str) -> Optional[SensorReading]:
        """Read sensor value.
        
        Args:
            sensor_type: Sensor name (ultrasonic, temperature, light, etc.)
            
        Returns:
            SensorReading or None
        """
        response = self.send("sensor", type=sensor_type)
        
        if response and response.get("status") == "ok":
            reading = SensorReading(
                sensor_type=sensor_type,
                value=response.get("value", 0),
                unit=response.get("unit", ""),
            )
            
            # Notify listeners
            for cb in self._on_sensor:
                try:
                    cb(reading)
                except Exception:
                    pass
            
            return reading
        
        return None
    
    def read_distance(self) -> Optional[float]:
        """Read ultrasonic distance sensor.
        
        Returns:
            Distance in cm or None
        """
        reading = self.read_sensor("ultrasonic")
        return reading.value if reading else None
    
    def read_temperature(self) -> Optional[float]:
        """Read temperature sensor.
        
        Returns:
            Temperature in Celsius or None
        """
        reading = self.read_sensor("temperature")
        return reading.value if reading else None
    
    def read_light(self) -> Optional[float]:
        """Read light sensor.
        
        Returns:
            Light level (0-1023) or None
        """
        reading = self.read_sensor("light")
        return reading.value if reading else None
    
    def read_all_sensors(self) -> Dict[str, Optional[SensorReading]]:
        """Read all available sensors.
        
        Returns:
            Dict of sensor name to reading
        """
        sensors = ["ultrasonic", "temperature", "light", "battery"]
        return {s: self.read_sensor(s) for s in sensors}
    
    # ─────────────────────────────────────────────────────────────────
    # Camera Commands
    # ─────────────────────────────────────────────────────────────────
    
    def capture_image(self) -> bool:
        """Trigger camera capture.
        
        Returns:
            True if command sent
        """
        response = self.send("camera", action="capture")
        return response is not None and response.get("status") == "ok"
    
    def camera_on(self) -> bool:
        """Turn camera on.
        
        Returns:
            True if command sent
        """
        response = self.send("camera", action="on")
        return response is not None and response.get("status") == "ok"
    
    def camera_off(self) -> bool:
        """Turn camera off.
        
        Returns:
            True if command sent
        """
        response = self.send("camera", action="off")
        return response is not None and response.get("status") == "ok"
    
    # ─────────────────────────────────────────────────────────────────
    # LED/Buzzer Commands
    # ─────────────────────────────────────────────────────────────────
    
    def set_led(self, color: str = "white", brightness: int = 255) -> bool:
        """Set LED color/brightness.
        
        Args:
            color: Color name (red, green, blue, white, off)
            brightness: Brightness (0-255)
            
        Returns:
            True if command sent
        """
        response = self.send("led", color=color, brightness=brightness)
        return response is not None and response.get("status") == "ok"
    
    def beep(self, frequency: int = 1000, duration_ms: int = 200) -> bool:
        """Play beep sound.
        
        Args:
            frequency: Tone frequency in Hz
            duration_ms: Duration in milliseconds
            
        Returns:
            True if command sent
        """
        response = self.send("buzzer", frequency=frequency, duration=duration_ms)
        return response is not None and response.get("status") == "ok"
    
    # ─────────────────────────────────────────────────────────────────
    # Utility Commands
    # ─────────────────────────────────────────────────────────────────
    
    def get_status(self) -> Optional[Dict]:
        """Get MoltBot status.
        
        Returns:
            Status dict or None
        """
        return self.send("status")
    
    def get_battery(self) -> Optional[float]:
        """Get battery voltage.
        
        Returns:
            Voltage or None
        """
        reading = self.read_sensor("battery")
        return reading.value if reading else None
    
    def reset(self) -> bool:
        """Reset MoltBot (software reset).
        
        Returns:
            True if command sent
        """
        response = self.send("reset")
        return response is not None
    
    # ─────────────────────────────────────────────────────────────────
    # Event Registration
    # ─────────────────────────────────────────────────────────────────
    
    def on_connect(self, callback: Callable):
        """Register connection callback."""
        self._on_connect.append(callback)
    
    def on_disconnect(self, callback: Callable):
        """Register disconnection callback."""
        self._on_disconnect.append(callback)
    
    def on_error(self, callback: Callable[[str], None]):
        """Register error callback."""
        self._on_error.append(callback)
    
    def on_sensor(self, callback: Callable[[SensorReading], None]):
        """Register sensor reading callback."""
        self._on_sensor.append(callback)
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


# Singleton instance
_controller: Optional[MoltBotController] = None


def get_moltbot_controller(**kwargs) -> MoltBotController:
    """Get or create MoltBot controller singleton."""
    global _controller
    if _controller is None:
        _controller = MoltBotController(**kwargs)
    return _controller


def connect_moltbot() -> bool:
    """Connect to MoltBot (convenience function)."""
    return get_moltbot_controller().connect()


def moltbot_command(cmd: str, **params) -> Optional[Dict]:
    """Send command to MoltBot (convenience function)."""
    controller = get_moltbot_controller()
    if not controller.is_connected:
        controller.connect()
    return controller.send(cmd, **params)
