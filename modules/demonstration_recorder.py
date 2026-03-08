"""
LADA - Demonstration Recording & Learning
Records user mouse/keyboard actions with screenshots, replays them,
and generalizes recordings into reusable workflows.

Features:
- Record mouse clicks, keyboard input, and screenshots
- Replay recorded demonstrations via GUIAutomator
- AI-powered generalization into parameterized WorkflowEngine workflows
- Persistent storage of demonstrations
"""

import os
import json
import time
import logging
import threading
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Conditional imports
try:
    from pynput import mouse, keyboard
    PYNPUT_OK = True
except ImportError:
    PYNPUT_OK = False

try:
    from PIL import ImageGrab
    PIL_OK = True
except ImportError:
    PIL_OK = False


@dataclass
class RecordedEvent:
    """A single recorded user interaction event."""
    timestamp: float
    event_type: str  # "click", "type", "key", "scroll"
    data: Dict[str, Any] = field(default_factory=dict)
    screenshot_path: str = ""


@dataclass
class Demonstration:
    """A complete recorded demonstration session."""
    id: str
    name: str
    description: str = ""
    events: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    duration: float = 0.0
    screenshot_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Demonstration':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DemonstrationRecorder:
    """
    Records mouse and keyboard actions with periodic screenshots.

    Usage:
        recorder = DemonstrationRecorder()
        recorder.start_recording("my_task")
        # ... user performs actions ...
        demo = recorder.stop_recording()
    """

    SCREENSHOT_INTERVAL = 2.0  # Seconds between periodic screenshots

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(os.path.dirname(os.path.dirname(__file__))) / 'data' / 'demonstrations'

        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._recording = False
        self._events: List[RecordedEvent] = []
        self._start_time: float = 0.0
        self._current_demo_id: str = ""
        self._screenshot_dir: Optional[Path] = None
        self._screenshot_count = 0

        # Listener references
        self._mouse_listener = None
        self._keyboard_listener = None
        self._screenshot_thread = None
        self._typed_buffer: List[str] = []

    def start_recording(self, name: str, description: str = "") -> bool:
        """Begin recording user actions."""
        if not PYNPUT_OK:
            logger.error("[DemoRecord] pynput not available")
            return False

        if self._recording:
            logger.warning("[DemoRecord] Already recording")
            return False

        self._current_demo_id = f"demo_{int(time.time())}_{name.lower().replace(' ', '_')[:20]}"
        self._screenshot_dir = self.data_dir / self._current_demo_id / 'screenshots'
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

        self._events = []
        self._start_time = time.time()
        self._screenshot_count = 0
        self._typed_buffer = []
        self._recording = True

        # Start mouse listener
        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._mouse_listener.start()

        # Start keyboard listener
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._keyboard_listener.start()

        # Start periodic screenshot thread
        self._screenshot_thread = threading.Thread(
            target=self._screenshot_loop, daemon=True
        )
        self._screenshot_thread.start()

        logger.info(f"[DemoRecord] Recording started: {name}")
        return True

    def stop_recording(self) -> Optional[Demonstration]:
        """Stop recording and save the demonstration."""
        if not self._recording:
            return None

        self._recording = False
        duration = time.time() - self._start_time

        # Stop listeners
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()

        # Flush typed buffer
        self._flush_typed_buffer()

        # Build demonstration
        demo = Demonstration(
            id=self._current_demo_id,
            name=self._current_demo_id,
            events=[asdict(e) for e in self._events],
            duration=duration,
            screenshot_count=self._screenshot_count,
        )

        # Save to disk
        self._save_demonstration(demo)

        logger.info(
            f"[DemoRecord] Recording stopped: {len(self._events)} events, "
            f"{duration:.1f}s, {self._screenshot_count} screenshots"
        )
        return demo

    def _on_click(self, x, y, button, pressed):
        """Record mouse click events."""
        if not self._recording or not pressed:
            return

        self._flush_typed_buffer()
        screenshot_path = self._take_screenshot("click")

        self._events.append(RecordedEvent(
            timestamp=time.time() - self._start_time,
            event_type="click",
            data={
                "x": x,
                "y": y,
                "button": str(button),
            },
            screenshot_path=screenshot_path,
        ))

    def _on_scroll(self, x, y, dx, dy):
        """Record scroll events."""
        if not self._recording:
            return

        self._events.append(RecordedEvent(
            timestamp=time.time() - self._start_time,
            event_type="scroll",
            data={
                "x": x,
                "y": y,
                "dx": dx,
                "dy": dy,
            },
        ))

    def _on_key_press(self, key):
        """Record keyboard events."""
        if not self._recording:
            return

        try:
            # Regular character key
            char = key.char
            if char:
                self._typed_buffer.append(char)
                return
        except AttributeError:
            pass

        # Special key
        self._flush_typed_buffer()
        key_name = str(key).replace('Key.', '')

        self._events.append(RecordedEvent(
            timestamp=time.time() - self._start_time,
            event_type="key",
            data={"key": key_name},
        ))

    def _on_key_release(self, key):
        """Handle key release (unused but required by pynput)."""
        pass

    def _flush_typed_buffer(self):
        """Flush buffered character keys into a single 'type' event."""
        if self._typed_buffer:
            text = ''.join(self._typed_buffer)
            self._events.append(RecordedEvent(
                timestamp=time.time() - self._start_time,
                event_type="type",
                data={"text": text},
            ))
            self._typed_buffer = []

    def _take_screenshot(self, context: str = "") -> str:
        """Take a screenshot and return the file path."""
        if not PIL_OK or not self._screenshot_dir:
            return ""
        try:
            img = ImageGrab.grab()
            filename = f"ss_{self._screenshot_count:04d}_{context}.png"
            path = self._screenshot_dir / filename
            img.save(str(path))
            self._screenshot_count += 1
            return str(path)
        except Exception as e:
            logger.error(f"[DemoRecord] Screenshot failed: {e}")
            return ""

    def _screenshot_loop(self):
        """Periodic screenshot capture during recording."""
        while self._recording:
            self._take_screenshot("periodic")
            time.sleep(self.SCREENSHOT_INTERVAL)

    def _save_demonstration(self, demo: Demonstration):
        """Save demonstration to JSON file."""
        demo_dir = self.data_dir / demo.id
        demo_dir.mkdir(parents=True, exist_ok=True)
        with open(demo_dir / 'demo.json', 'w', encoding='utf-8') as f:
            json.dump(demo.to_dict(), f, indent=2)

    def load_demonstration(self, demo_id: str) -> Optional[Demonstration]:
        """Load a saved demonstration."""
        demo_file = self.data_dir / demo_id / 'demo.json'
        if not demo_file.exists():
            return None
        try:
            with open(demo_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return Demonstration.from_dict(data)
        except Exception as e:
            logger.error(f"[DemoRecord] Load failed: {e}")
            return None

    def list_demonstrations(self) -> List[Dict[str, Any]]:
        """List all saved demonstrations."""
        demos = []
        for demo_dir in self.data_dir.iterdir():
            if demo_dir.is_dir():
                demo_file = demo_dir / 'demo.json'
                if demo_file.exists():
                    try:
                        with open(demo_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        demos.append({
                            'id': data.get('id', demo_dir.name),
                            'name': data.get('name', ''),
                            'description': data.get('description', ''),
                            'duration': data.get('duration', 0),
                            'events': len(data.get('events', [])),
                            'created_at': data.get('created_at', ''),
                        })
                    except Exception:
                        pass
        return sorted(demos, key=lambda d: d.get('created_at', ''), reverse=True)

    def delete_demonstration(self, demo_id: str) -> bool:
        """Delete a saved demonstration."""
        demo_dir = self.data_dir / demo_id
        if demo_dir.exists():
            import shutil
            shutil.rmtree(demo_dir, ignore_errors=True)
            return True
        return False


class DemonstrationPlayer:
    """
    Replays recorded demonstrations using GUIAutomator.
    """

    def __init__(self, gui_automator=None):
        self.gui = gui_automator

    def replay(self, demo: Demonstration, speed: float = 1.0) -> bool:
        """
        Replay a recorded demonstration.

        Args:
            demo: The demonstration to replay
            speed: Playback speed multiplier (1.0 = original speed)
        """
        if not self.gui:
            logger.error("[DemoPlayer] No GUI automator available")
            return False

        events = demo.events
        if not events:
            return False

        logger.info(f"[DemoPlayer] Replaying {len(events)} events at {speed}x speed")

        prev_timestamp = 0.0

        for event in events:
            ts = event.get('timestamp', 0)
            event_type = event.get('event_type', '')
            data = event.get('data', {})

            # Wait for timing (adjusted by speed)
            delay = (ts - prev_timestamp) / speed
            if delay > 0:
                time.sleep(delay)
            prev_timestamp = ts

            try:
                if event_type == 'click':
                    self.gui.click(data.get('x', 0), data.get('y', 0))

                elif event_type == 'type':
                    self.gui.type_text(data.get('text', ''))

                elif event_type == 'key':
                    self.gui.press_key(data.get('key', ''))

                elif event_type == 'scroll':
                    direction = 'down' if data.get('dy', 0) < 0 else 'up'
                    self.gui.scroll(direction)

            except Exception as e:
                logger.error(f"[DemoPlayer] Replay action failed: {e}")

        logger.info("[DemoPlayer] Replay complete")
        return True


class DemonstrationGeneralizer:
    """
    Uses AI to generalize recorded demonstrations into reusable workflows.
    """

    def __init__(self, ai_router=None):
        self.ai_router = ai_router

    def generalize(self, demo: Demonstration) -> Optional[Dict[str, Any]]:
        """
        Convert a recorded demonstration into a WorkflowEngine-compatible
        workflow definition with parameterized steps.

        Returns:
            Dict with 'name', 'steps' (list of workflow step dicts), or None
        """
        if not self.ai_router:
            return self._heuristic_generalize(demo)

        # Build a description of the demonstration for the AI
        event_descriptions = []
        for event in demo.events[:50]:  # Limit to first 50 events
            et = event.get('event_type', '')
            data = event.get('data', {})
            ts = event.get('timestamp', 0)

            if et == 'click':
                event_descriptions.append(
                    f"[{ts:.1f}s] Click at ({data.get('x')}, {data.get('y')})"
                )
            elif et == 'type':
                event_descriptions.append(
                    f"[{ts:.1f}s] Type: \"{data.get('text', '')[:50]}\""
                )
            elif et == 'key':
                event_descriptions.append(
                    f"[{ts:.1f}s] Press key: {data.get('key', '')}"
                )
            elif et == 'scroll':
                direction = 'down' if data.get('dy', 0) < 0 else 'up'
                event_descriptions.append(f"[{ts:.1f}s] Scroll {direction}")

        events_text = '\n'.join(event_descriptions)

        prompt = (
            f"Analyze this recorded user demonstration and convert it into "
            f"a reusable workflow with parameterized steps.\n\n"
            f"Recorded events:\n{events_text}\n\n"
            f"Convert this into a JSON workflow definition with this format:\n"
            f'{{"name": "workflow_name", "description": "...", '
            f'"steps": [{{"action": "click|type|key|scroll|wait|open_url", '
            f'"params": {{}}, "description": "..."}}]}}\n\n'
            f"Identify which values should be parameters (like URLs, search "
            f"terms, or names) and mark them as {{param_name}}.\n"
            f"Return ONLY valid JSON."
        )

        try:
            response = self.ai_router.query(prompt)
            if response:
                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"[DemoGen] AI generalization failed: {e}")

        return self._heuristic_generalize(demo)

    def _heuristic_generalize(self, demo: Demonstration) -> Dict[str, Any]:
        """Fallback: convert events directly into workflow steps."""
        steps = []
        for event in demo.events:
            et = event.get('event_type', '')
            data = event.get('data', {})

            if et == 'click':
                steps.append({
                    'action': 'gui_click',
                    'params': {'x': data.get('x', 0), 'y': data.get('y', 0)},
                    'description': f"Click at ({data.get('x')}, {data.get('y')})",
                })
            elif et == 'type':
                text = data.get('text', '')
                steps.append({
                    'action': 'gui_type',
                    'params': {'text': text},
                    'description': f"Type: {text[:30]}",
                })
            elif et == 'key':
                steps.append({
                    'action': 'gui_key',
                    'params': {'key': data.get('key', '')},
                    'description': f"Press {data.get('key', '')}",
                })
            elif et == 'scroll':
                direction = 'down' if data.get('dy', 0) < 0 else 'up'
                steps.append({
                    'action': 'gui_scroll',
                    'params': {'direction': direction},
                    'description': f"Scroll {direction}",
                })

        return {
            'name': demo.name,
            'description': demo.description or f"Replayed demonstration: {demo.name}",
            'steps': steps,
        }


# Singleton
_recorder = None


def get_demonstration_recorder(data_dir: Optional[str] = None) -> DemonstrationRecorder:
    """Get or create recorder instance."""
    global _recorder
    if _recorder is None:
        _recorder = DemonstrationRecorder(data_dir=data_dir)
    return _recorder
