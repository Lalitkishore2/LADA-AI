"""LADA RobotAgent

Specialized agent for MoltBot robotic control.

Features:
- Movement commands (forward, backward, turn)
- Arm/claw operations
- Sensor reading
- Camera capture
- Autonomous behaviors
- Safety controls

Usage:
    from modules.agents.robot_agent import RobotAgent
    
    agent = RobotAgent()
    await agent.connect()
    await agent.move_forward(10)
    await agent.pick_up_object()
"""

from __future__ import annotations

import os
import asyncio
import logging
import importlib
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Optional MoltBot integration loader. Integration files may be archived.
MOLTBOT_AVAILABLE = False
MoltBotController = Any
MoltBotConfig = Any
SensorReading = Any
get_moltbot_controller = None


def _load_moltbot_symbols() -> bool:
    """Attempt to load MoltBot symbols from active integrations package."""
    global MOLTBOT_AVAILABLE, MoltBotController, MoltBotConfig, SensorReading, get_moltbot_controller

    module_name = ".".join(["integrations", "moltbot_controller"])
    try:
        module = importlib.import_module(module_name)
        MoltBotController = getattr(module, "MoltBotController")
        MoltBotConfig = getattr(module, "MoltBotConfig")
        SensorReading = getattr(module, "SensorReading")
        get_moltbot_controller = getattr(module, "get_moltbot_controller")
        MOLTBOT_AVAILABLE = True
        return True
    except Exception:
        MOLTBOT_AVAILABLE = False
        MoltBotController = Any
        MoltBotConfig = Any
        SensorReading = Any
        get_moltbot_controller = None
        return False


_load_moltbot_symbols()


class RobotMode(Enum):
    """Robot operation modes."""
    MANUAL = "manual"         # Direct command control
    AUTONOMOUS = "autonomous"  # Self-directed behavior
    FOLLOW = "follow"         # Follow detected object
    PATROL = "patrol"         # Patrol pattern
    IDLE = "idle"             # Standby


@dataclass
class Position:
    """Robot position estimate."""
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0  # Degrees, 0 = forward


@dataclass
class RobotState:
    """Current robot state."""
    connected: bool
    mode: RobotMode
    position: Position
    claw_open: bool
    arm_position: Dict[str, int]  # joint -> angle
    battery_voltage: Optional[float]
    last_distance: Optional[float]


class RobotAgent:
    """Agent for MoltBot robotic control.
    
    Provides high-level robot operations with safety controls.
    """
    
    # Safety thresholds
    MIN_OBSTACLE_DISTANCE = 15.0  # cm
    LOW_BATTERY_THRESHOLD = 6.5   # volts
    
    def __init__(self, auto_connect: bool = False):
        """Initialize robot agent.
        
        Args:
            auto_connect: Connect to robot automatically
        """
        if not MOLTBOT_AVAILABLE:
            logger.warning("[RobotAgent] MoltBot controller not available (optional integration may be archived)")
        
        self._controller: Optional[MoltBotController] = None
        self._mode = RobotMode.IDLE
        self._position = Position()
        self._claw_open = True
        self._arm_position = {
            "base": 90,
            "shoulder": 90,
            "elbow": 90,
            "wrist": 90,
        }
        
        self._autonomous_task: Optional[asyncio.Task] = None
        self._obstacle_callback: Optional[Callable] = None
        
        if auto_connect:
            self.connect()
        
        logger.info("[RobotAgent] Initialized")
    
    @property
    def connected(self) -> bool:
        """Check if connected to robot."""
        return self._controller is not None and self._controller.is_connected
    
    @property
    def state(self) -> RobotState:
        """Get current robot state."""
        return RobotState(
            connected=self.connected,
            mode=self._mode,
            position=self._position,
            claw_open=self._claw_open,
            arm_position=self._arm_position.copy(),
            battery_voltage=None,
            last_distance=None,
        )
    
    def connect(self) -> bool:
        """Connect to MoltBot.
        
        Returns:
            True if connected
        """
        if not MOLTBOT_AVAILABLE:
            return False
        
        self._controller = get_moltbot_controller()
        
        # Register sensor callback
        self._controller.on_sensor(self._on_sensor_reading)
        
        return self._controller.connect()
    
    def disconnect(self):
        """Disconnect from robot."""
        if self._controller:
            self._stop_autonomous()
            self._controller.disconnect()
            self._controller = None
    
    def _on_sensor_reading(self, reading: SensorReading):
        """Handle sensor reading."""
        if reading.sensor_type == "ultrasonic":
            if reading.value < self.MIN_OBSTACLE_DISTANCE:
                logger.warning(f"[RobotAgent] Obstacle detected: {reading.value}cm")
                if self._obstacle_callback:
                    self._obstacle_callback(reading.value)
    
    # ─────────────────────────────────────────────────────────────────
    # Movement
    # ─────────────────────────────────────────────────────────────────
    
    async def move_forward(self, distance_cm: float, check_obstacles: bool = True) -> bool:
        """Move robot forward.
        
        Args:
            distance_cm: Distance in centimeters
            check_obstacles: Check for obstacles first
            
        Returns:
            True if successful
        """
        if not self.connected:
            logger.warning("[RobotAgent] Not connected")
            return False
        
        # Safety check
        if check_obstacles:
            dist = self._controller.read_distance()
            if dist and dist < self.MIN_OBSTACLE_DISTANCE:
                logger.warning(f"[RobotAgent] Obstacle too close: {dist}cm")
                return False
        
        result = self._controller.move_forward(distance_cm)
        
        if result:
            # Update position estimate
            import math
            self._position.x += distance_cm * math.cos(math.radians(self._position.heading))
            self._position.y += distance_cm * math.sin(math.radians(self._position.heading))
        
        return result
    
    async def move_backward(self, distance_cm: float) -> bool:
        """Move robot backward.
        
        Args:
            distance_cm: Distance in centimeters
            
        Returns:
            True if successful
        """
        if not self.connected:
            return False
        
        result = self._controller.move_backward(distance_cm)
        
        if result:
            import math
            self._position.x -= distance_cm * math.cos(math.radians(self._position.heading))
            self._position.y -= distance_cm * math.sin(math.radians(self._position.heading))
        
        return result
    
    async def turn_left(self, degrees: float) -> bool:
        """Turn robot left.
        
        Args:
            degrees: Rotation angle
            
        Returns:
            True if successful
        """
        if not self.connected:
            return False
        
        result = self._controller.turn_left(degrees)
        
        if result:
            self._position.heading = (self._position.heading + degrees) % 360
        
        return result
    
    async def turn_right(self, degrees: float) -> bool:
        """Turn robot right.
        
        Args:
            degrees: Rotation angle
            
        Returns:
            True if successful
        """
        if not self.connected:
            return False
        
        result = self._controller.turn_right(degrees)
        
        if result:
            self._position.heading = (self._position.heading - degrees) % 360
        
        return result
    
    async def stop(self) -> bool:
        """Emergency stop."""
        if not self.connected:
            return False
        
        self._stop_autonomous()
        return self._controller.stop()
    
    # ─────────────────────────────────────────────────────────────────
    # Arm/Claw
    # ─────────────────────────────────────────────────────────────────
    
    async def open_claw(self) -> bool:
        """Open the gripper claw."""
        if not self.connected:
            return False
        
        result = self._controller.open_claw()
        if result:
            self._claw_open = True
        return result
    
    async def close_claw(self) -> bool:
        """Close the gripper claw."""
        if not self.connected:
            return False
        
        result = self._controller.close_claw()
        if result:
            self._claw_open = False
        return result
    
    async def set_arm_position(self, joint: str, angle: int) -> bool:
        """Set arm joint position.
        
        Args:
            joint: Joint name (base, shoulder, elbow, wrist)
            angle: Target angle (0-180)
            
        Returns:
            True if successful
        """
        if not self.connected:
            return False
        
        if joint not in self._arm_position:
            logger.warning(f"[RobotAgent] Unknown joint: {joint}")
            return False
        
        result = self._controller.set_arm_position(joint, angle)
        if result:
            self._arm_position[joint] = angle
        return result
    
    async def arm_home(self) -> bool:
        """Move arm to home position."""
        if not self.connected:
            return False
        
        result = self._controller.arm_home()
        if result:
            self._arm_position = {
                "base": 90,
                "shoulder": 90,
                "elbow": 90,
                "wrist": 90,
            }
        return result
    
    async def pick_up_object(self, height_cm: float = 5.0) -> bool:
        """Execute pick-up sequence.
        
        Args:
            height_cm: Height to lift object
            
        Returns:
            True if successful
        """
        if not self.connected:
            return False
        
        # Open claw
        await self.open_claw()
        await asyncio.sleep(0.5)
        
        # Lower arm
        await self.set_arm_position("shoulder", 45)
        await asyncio.sleep(0.5)
        
        # Close claw
        await self.close_claw()
        await asyncio.sleep(0.5)
        
        # Raise arm
        await self.set_arm_position("shoulder", 90)
        
        return True
    
    async def put_down_object(self) -> bool:
        """Execute put-down sequence."""
        if not self.connected:
            return False
        
        # Lower arm
        await self.set_arm_position("shoulder", 45)
        await asyncio.sleep(0.5)
        
        # Open claw
        await self.open_claw()
        await asyncio.sleep(0.3)
        
        # Raise arm
        await self.set_arm_position("shoulder", 90)
        
        return True
    
    # ─────────────────────────────────────────────────────────────────
    # Sensors
    # ─────────────────────────────────────────────────────────────────
    
    async def read_distance(self) -> Optional[float]:
        """Read ultrasonic distance sensor."""
        if not self.connected:
            return None
        return self._controller.read_distance()
    
    async def read_temperature(self) -> Optional[float]:
        """Read temperature sensor."""
        if not self.connected:
            return None
        return self._controller.read_temperature()
    
    async def read_battery(self) -> Optional[float]:
        """Read battery voltage."""
        if not self.connected:
            return None
        
        voltage = self._controller.get_battery()
        
        if voltage and voltage < self.LOW_BATTERY_THRESHOLD:
            logger.warning(f"[RobotAgent] Low battery: {voltage}V")
        
        return voltage
    
    async def capture_image(self) -> bool:
        """Trigger camera capture."""
        if not self.connected:
            return False
        return self._controller.capture_image()
    
    # ─────────────────────────────────────────────────────────────────
    # Autonomous Behaviors
    # ─────────────────────────────────────────────────────────────────
    
    async def start_patrol(self, pattern: str = "square") -> bool:
        """Start patrol behavior.
        
        Args:
            pattern: Patrol pattern (square, random, line)
            
        Returns:
            True if started
        """
        if not self.connected:
            return False
        
        self._stop_autonomous()
        self._mode = RobotMode.PATROL
        
        if pattern == "square":
            self._autonomous_task = asyncio.create_task(self._patrol_square())
        elif pattern == "random":
            self._autonomous_task = asyncio.create_task(self._patrol_random())
        
        return True
    
    async def _patrol_square(self):
        """Square patrol pattern."""
        try:
            while self._mode == RobotMode.PATROL:
                for _ in range(4):
                    await self.move_forward(50)
                    await asyncio.sleep(0.5)
                    await self.turn_right(90)
                    await asyncio.sleep(0.5)
                    
                    if self._mode != RobotMode.PATROL:
                        break
                        
        except asyncio.CancelledError:
            pass
    
    async def _patrol_random(self):
        """Random patrol pattern."""
        import random
        try:
            while self._mode == RobotMode.PATROL:
                dist = random.randint(20, 100)
                await self.move_forward(dist)
                await asyncio.sleep(0.5)
                
                turn = random.randint(-90, 90)
                if turn > 0:
                    await self.turn_right(turn)
                else:
                    await self.turn_left(-turn)
                    
                await asyncio.sleep(0.5)
                    
        except asyncio.CancelledError:
            pass
    
    def _stop_autonomous(self):
        """Stop autonomous behavior."""
        self._mode = RobotMode.MANUAL
        
        if self._autonomous_task:
            self._autonomous_task.cancel()
            self._autonomous_task = None
    
    async def explore(self, max_distance: float = 200) -> List[Position]:
        """Explore environment, mapping obstacles.
        
        Args:
            max_distance: Maximum exploration distance
            
        Returns:
            List of visited positions
        """
        positions = [Position(self._position.x, self._position.y, self._position.heading)]
        total_distance = 0.0
        
        while total_distance < max_distance and self.connected:
            dist = await self.read_distance()
            
            if dist and dist > 30:
                # Clear ahead, move forward
                move = min(20, max_distance - total_distance)
                await self.move_forward(move)
                total_distance += move
                positions.append(Position(
                    self._position.x,
                    self._position.y,
                    self._position.heading
                ))
            else:
                # Obstacle, turn
                await self.turn_right(45)
            
            await asyncio.sleep(0.2)
        
        return positions
    
    def on_obstacle(self, callback: Callable[[float], None]):
        """Register obstacle detection callback."""
        self._obstacle_callback = callback
    
    # ─────────────────────────────────────────────────────────────────
    # Feedback
    # ─────────────────────────────────────────────────────────────────
    
    async def beep(self, frequency: int = 1000, duration_ms: int = 200) -> bool:
        """Play beep sound."""
        if not self.connected:
            return False
        return self._controller.beep(frequency, duration_ms)
    
    async def set_led(self, color: str = "white") -> bool:
        """Set LED color."""
        if not self.connected:
            return False
        return self._controller.set_led(color)
    
    def __del__(self):
        self.disconnect()


# Singleton
_agent: Optional[RobotAgent] = None


def get_robot_agent(**kwargs) -> RobotAgent:
    """Get or create RobotAgent singleton."""
    global _agent
    if _agent is None:
        _agent = RobotAgent(**kwargs)
    return _agent
