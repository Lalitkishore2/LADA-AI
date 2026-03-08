"""
LADA v11.0 - Smart Home Control Framework
Unified smart home device management inspired by OpenClaw's integrations.

Features:
- Multi-backend hub: Philips Hue, Home Assistant, Tuya
- Device discovery, grouping, and scene management
- Natural language command parsing with fuzzy device matching
- Threaded device polling and state caching
- Persistent configuration and device cache
"""

import os
import json
import time
import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Conditional imports -- graceful degradation when libraries are absent
try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False
    logger.warning("requests not installed; smart home backends will be unavailable")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

DEVICE_TYPES = ("light", "thermostat", "plug", "lock", "sensor", "camera", "speaker")


@dataclass
class SmartDevice:
    """Representation of a single smart home device."""
    id: str
    name: str
    device_type: str  # one of DEVICE_TYPES
    room: str = "Unknown"
    manufacturer: str = "Unknown"
    backend: str = "unknown"
    state: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    is_online: bool = True
    last_seen: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SmartDevice":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DeviceGroup:
    """Named group of device IDs (e.g. 'Living Room Lights')."""
    name: str
    device_ids: List[str] = field(default_factory=list)


@dataclass
class Scene:
    """Saved multi-device configuration that can be activated in one call."""
    name: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    # Each action: {"device_id": "...", "action": "...", "params": {...}}
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------

class SmartHomeBackend(ABC):
    """Base class every smart home backend must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique backend identifier string."""
        ...

    @abstractmethod
    def discover(self) -> List[SmartDevice]:
        """Discover all devices reachable through this backend."""
        ...

    @abstractmethod
    def control(self, device_id: str, action: str, **params) -> Dict[str, Any]:
        """Send a control command to a device and return the result dict."""
        ...

    @abstractmethod
    def get_state(self, device_id: str) -> Dict[str, Any]:
        """Return the current state dictionary for *device_id*."""
        ...


# ---------------------------------------------------------------------------
# Philips Hue backend
# ---------------------------------------------------------------------------

class PhilipsHueBackend(SmartHomeBackend):
    """
    Control Philips Hue lights via the Hue Bridge REST API.

    Configuration is loaded from *config/hue_config.json* or can be passed
    directly.  The file should contain::

        {"bridge_ip": "192.168.1.x", "username": "<api-key>"}
    """

    CONFIG_PATH = Path("config/hue_config.json")

    def __init__(self, bridge_ip: Optional[str] = None, username: Optional[str] = None):
        self._bridge_ip = bridge_ip
        self._username = username
        self._load_config()

    # -- config helpers -----------------------------------------------------

    def _load_config(self):
        if self._bridge_ip and self._username:
            return
        if self.CONFIG_PATH.exists():
            try:
                cfg = json.loads(self.CONFIG_PATH.read_text(encoding="utf-8"))
                self._bridge_ip = self._bridge_ip or cfg.get("bridge_ip")
                self._username = self._username or cfg.get("username")
            except Exception as exc:
                logger.error("Failed to read Hue config: %s", exc)

    @property
    def _base_url(self) -> str:
        return f"http://{self._bridge_ip}/api/{self._username}"

    @property
    def name(self) -> str:
        return "philips_hue"

    # -- API helpers --------------------------------------------------------

    def _get(self, path: str) -> Any:
        if not REQUESTS_OK:
            raise RuntimeError("requests library is required for PhilipsHueBackend")
        resp = requests.get(f"{self._base_url}{path}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, data: dict) -> Any:
        if not REQUESTS_OK:
            raise RuntimeError("requests library is required for PhilipsHueBackend")
        resp = requests.put(f"{self._base_url}{path}", json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # -- SmartHomeBackend interface -----------------------------------------

    def discover(self) -> List[SmartDevice]:
        devices: List[SmartDevice] = []
        try:
            lights = self._get("/lights")
            for light_id, info in lights.items():
                state = info.get("state", {})
                capabilities = ["on_off", "brightness"]
                if state.get("colormode") in ("hs", "xy"):
                    capabilities.append("color")
                if "ct" in state:
                    capabilities.append("color_temperature")

                device = SmartDevice(
                    id=f"hue_{light_id}",
                    name=info.get("name", f"Hue Light {light_id}"),
                    device_type="light",
                    room=info.get("room", "Unknown"),
                    manufacturer="Philips",
                    backend=self.name,
                    state={
                        "on": state.get("on", False),
                        "brightness": state.get("bri", 0),
                        "hue": state.get("hue"),
                        "saturation": state.get("sat"),
                        "color_temp": state.get("ct"),
                        "reachable": state.get("reachable", False),
                    },
                    capabilities=capabilities,
                    is_online=state.get("reachable", False),
                    last_seen=datetime.now().isoformat(),
                )
                devices.append(device)
        except Exception as exc:
            logger.error("Hue discovery failed: %s", exc)
        return devices

    def control(self, device_id: str, action: str, **params) -> Dict[str, Any]:
        light_id = device_id.replace("hue_", "")
        body: Dict[str, Any] = {}

        if action in ("on", "turn_on"):
            body["on"] = True
        elif action in ("off", "turn_off"):
            body["on"] = False
        elif action == "toggle":
            current = self.get_state(device_id)
            body["on"] = not current.get("on", False)
        elif action == "set_brightness":
            body["bri"] = max(1, min(254, int(params.get("brightness", 254))))
            body["on"] = True
        elif action == "set_color":
            body["on"] = True
            if "hue" in params:
                body["hue"] = int(params["hue"])
            if "saturation" in params:
                body["sat"] = int(params["saturation"])
            if "brightness" in params:
                body["bri"] = int(params["brightness"])
        elif action == "set_color_temperature":
            body["on"] = True
            body["ct"] = max(153, min(500, int(params.get("color_temp", 300))))
        else:
            return {"error": f"Unknown action '{action}' for Hue light"}

        try:
            result = self._put(f"/lights/{light_id}/state", body)
            return {"success": True, "result": result}
        except Exception as exc:
            logger.error("Hue control error: %s", exc)
            return {"success": False, "error": str(exc)}

    def get_state(self, device_id: str) -> Dict[str, Any]:
        light_id = device_id.replace("hue_", "")
        try:
            info = self._get(f"/lights/{light_id}")
            return info.get("state", {})
        except Exception as exc:
            logger.error("Hue get_state error: %s", exc)
            return {}


# ---------------------------------------------------------------------------
# Home Assistant backend
# ---------------------------------------------------------------------------

class HomeAssistantBackend(SmartHomeBackend):
    """
    Integration with Home Assistant via its REST API.

    Reads *HA_URL* and *HA_TOKEN* from environment variables,
    falling back to *config/smart_home_config.json* section ``home_assistant``.
    """

    HA_TYPE_MAP = {
        "light": "light",
        "switch": "plug",
        "climate": "thermostat",
        "lock": "lock",
        "sensor": "sensor",
        "binary_sensor": "sensor",
        "camera": "camera",
        "media_player": "speaker",
    }

    def __init__(self, url: Optional[str] = None, token: Optional[str] = None):
        self._url = (url or os.getenv("HA_URL", "")).rstrip("/")
        self._token = token or os.getenv("HA_TOKEN", "")

    @property
    def name(self) -> str:
        return "home_assistant"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> Any:
        if not REQUESTS_OK:
            raise RuntimeError("requests library is required for HomeAssistantBackend")
        resp = requests.get(f"{self._url}/api{path}", headers=self._headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict) -> Any:
        if not REQUESTS_OK:
            raise RuntimeError("requests library is required for HomeAssistantBackend")
        resp = requests.post(
            f"{self._url}/api{path}", headers=self._headers(), json=data, timeout=15
        )
        resp.raise_for_status()
        return resp.json() if resp.text else {}

    # -- SmartHomeBackend interface -----------------------------------------

    def discover(self) -> List[SmartDevice]:
        devices: List[SmartDevice] = []
        try:
            states = self._get("/states")
            for entity in states:
                entity_id: str = entity.get("entity_id", "")
                domain = entity_id.split(".")[0] if "." in entity_id else ""
                dtype = self.HA_TYPE_MAP.get(domain)
                if dtype is None:
                    continue

                attrs = entity.get("attributes", {})
                capabilities = self._infer_capabilities(domain, attrs)

                device = SmartDevice(
                    id=f"ha_{entity_id}",
                    name=attrs.get("friendly_name", entity_id),
                    device_type=dtype,
                    room=attrs.get("room", "Unknown"),
                    manufacturer=attrs.get("manufacturer", "Unknown"),
                    backend=self.name,
                    state={"state": entity.get("state"), **attrs},
                    capabilities=capabilities,
                    is_online=entity.get("state") != "unavailable",
                    last_seen=entity.get("last_updated"),
                )
                devices.append(device)
        except Exception as exc:
            logger.error("Home Assistant discovery failed: %s", exc)
        return devices

    @staticmethod
    def _infer_capabilities(domain: str, attrs: dict) -> List[str]:
        caps = ["on_off"]
        if domain == "light":
            if "brightness" in attrs:
                caps.append("brightness")
            if "hs_color" in attrs or "rgb_color" in attrs:
                caps.append("color")
            if "color_temp" in attrs:
                caps.append("color_temperature")
        elif domain == "climate":
            caps.extend(["temperature", "hvac_mode"])
        elif domain == "media_player":
            caps.extend(["volume", "play_pause"])
        return caps

    def control(self, device_id: str, action: str, **params) -> Dict[str, Any]:
        entity_id = device_id.replace("ha_", "", 1)
        domain = entity_id.split(".")[0] if "." in entity_id else ""

        service_data: Dict[str, Any] = {"entity_id": entity_id}
        service_data.update(params)

        service_map = {
            "on": "turn_on",
            "turn_on": "turn_on",
            "off": "turn_off",
            "turn_off": "turn_off",
            "toggle": "toggle",
            "set_brightness": "turn_on",
            "set_color": "turn_on",
            "set_temperature": "set_temperature",
            "set_hvac_mode": "set_hvac_mode",
            "set_value": "set_value",
            "call_service": params.pop("service", "turn_on"),
        }

        service = service_map.get(action)
        if service is None:
            return {"error": f"Unknown action '{action}' for HA entity"}

        if action == "set_brightness" and "brightness" in params:
            service_data["brightness"] = max(0, min(255, int(params["brightness"])))
        elif action == "set_color":
            if "rgb" in params:
                service_data["rgb_color"] = params["rgb"]
            if "hs" in params:
                service_data["hs_color"] = params["hs"]

        try:
            result = self._post(f"/services/{domain}/{service}", service_data)
            return {"success": True, "result": result}
        except Exception as exc:
            logger.error("HA control error: %s", exc)
            return {"success": False, "error": str(exc)}

    def get_state(self, device_id: str) -> Dict[str, Any]:
        entity_id = device_id.replace("ha_", "", 1)
        try:
            data = self._get(f"/states/{entity_id}")
            return {"state": data.get("state"), **data.get("attributes", {})}
        except Exception as exc:
            logger.error("HA get_state error: %s", exc)
            return {}


# ---------------------------------------------------------------------------
# Tuya backend
# ---------------------------------------------------------------------------

class TuyaBackend(SmartHomeBackend):
    """
    Tuya / Smart Life device control via the Tuya Open API.

    Credentials are read from environment variables:
        TUYA_CLIENT_ID, TUYA_SECRET, TUYA_DEVICE_UID, TUYA_REGION (default us)
    """

    REGION_URLS = {
        "us": "https://openapi.tuyaus.com",
        "eu": "https://openapi.tuyaeu.com",
        "cn": "https://openapi.tuyacn.com",
        "in": "https://openapi.tuyain.com",
    }

    TUYA_TYPE_MAP = {
        "dj": "light",       # light (deng-ju)
        "cz": "plug",        # socket (cha-zuo)
        "kg": "plug",        # switch (kai-guan)
        "wk": "thermostat",  # thermostat (wen-kong)
        "ms": "lock",        # door lock (men-suo)
        "sp": "camera",      # camera (she-pin)
    }

    def __init__(
        self,
        client_id: Optional[str] = None,
        secret: Optional[str] = None,
        device_uid: Optional[str] = None,
        region: Optional[str] = None,
    ):
        self._client_id = client_id or os.getenv("TUYA_CLIENT_ID", "")
        self._secret = secret or os.getenv("TUYA_SECRET", "")
        self._device_uid = device_uid or os.getenv("TUYA_DEVICE_UID", "")
        self._region = (region or os.getenv("TUYA_REGION", "us")).lower()
        self._base_url = self.REGION_URLS.get(self._region, self.REGION_URLS["us"])
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0

    @property
    def name(self) -> str:
        return "tuya"

    # -- auth ---------------------------------------------------------------

    def _ensure_token(self):
        if self._access_token and time.time() < self._token_expiry:
            return
        if not REQUESTS_OK:
            raise RuntimeError("requests library is required for TuyaBackend")
        try:
            resp = requests.get(
                f"{self._base_url}/v1.0/token?grant_type=1",
                headers=self._sign_headers("GET", "/v1.0/token?grant_type=1", ""),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("success"):
                result = data["result"]
                self._access_token = result["access_token"]
                self._token_expiry = time.time() + result.get("expire_time", 7200) - 60
        except Exception as exc:
            logger.error("Tuya token refresh failed: %s", exc)

    def _sign_headers(self, method: str, path: str, body: str) -> dict:
        import hashlib
        import hmac
        t = str(int(time.time() * 1000))
        string_to_sign = f"{self._client_id}{t}{method}\n{hashlib.sha256(body.encode()).hexdigest()}\n\n{path}"
        sign = hmac.new(
            self._secret.encode(), string_to_sign.encode(), hashlib.sha256
        ).hexdigest().upper()
        headers: Dict[str, str] = {
            "client_id": self._client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "Content-Type": "application/json",
        }
        if self._access_token:
            headers["access_token"] = self._access_token
        return headers

    # -- API helpers --------------------------------------------------------

    def _api_get(self, path: str) -> Any:
        self._ensure_token()
        if not REQUESTS_OK:
            raise RuntimeError("requests library is required for TuyaBackend")
        resp = requests.get(
            f"{self._base_url}{path}",
            headers=self._sign_headers("GET", path, ""),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _api_post(self, path: str, data: dict) -> Any:
        self._ensure_token()
        if not REQUESTS_OK:
            raise RuntimeError("requests library is required for TuyaBackend")
        body = json.dumps(data)
        resp = requests.post(
            f"{self._base_url}{path}",
            headers=self._sign_headers("POST", path, body),
            data=body,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # -- SmartHomeBackend interface -----------------------------------------

    def discover(self) -> List[SmartDevice]:
        devices: List[SmartDevice] = []
        try:
            result = self._api_get(f"/v1.0/users/{self._device_uid}/devices")
            if not result.get("success"):
                logger.warning("Tuya discovery returned success=false")
                return devices
            for dev in result.get("result", []):
                category = dev.get("category", "")
                dtype = self.TUYA_TYPE_MAP.get(category, "plug")

                capabilities = ["on_off"]
                if dtype == "light":
                    capabilities.extend(["brightness", "color", "color_temperature"])
                elif dtype == "thermostat":
                    capabilities.append("temperature")

                device = SmartDevice(
                    id=f"tuya_{dev['id']}",
                    name=dev.get("name", dev["id"]),
                    device_type=dtype,
                    room=dev.get("room_name", "Unknown"),
                    manufacturer="Tuya",
                    backend=self.name,
                    state={"online": dev.get("online", False)},
                    capabilities=capabilities,
                    is_online=dev.get("online", False),
                    last_seen=datetime.now().isoformat(),
                )
                devices.append(device)
        except Exception as exc:
            logger.error("Tuya discovery failed: %s", exc)
        return devices

    def control(self, device_id: str, action: str, **params) -> Dict[str, Any]:
        real_id = device_id.replace("tuya_", "", 1)
        commands: List[Dict[str, Any]] = []

        if action in ("on", "turn_on"):
            commands.append({"code": "switch_led", "value": True})
        elif action in ("off", "turn_off"):
            commands.append({"code": "switch_led", "value": False})
        elif action == "set_brightness":
            commands.append({"code": "bright_value_v2", "value": int(params.get("brightness", 500))})
        elif action == "set_color":
            commands.append({
                "code": "colour_data_v2",
                "value": {
                    "h": int(params.get("hue", 0)),
                    "s": int(params.get("saturation", 1000)),
                    "v": int(params.get("brightness", 1000)),
                },
            })
        elif action == "set_color_temperature":
            commands.append({"code": "temp_value_v2", "value": int(params.get("color_temp", 500))})
        elif action == "set_temperature":
            commands.append({"code": "temp_set", "value": int(params.get("temperature", 22))})
        else:
            return {"error": f"Unknown action '{action}' for Tuya device"}

        try:
            result = self._api_post(
                f"/v1.0/devices/{real_id}/commands", {"commands": commands}
            )
            return {"success": result.get("success", False), "result": result}
        except Exception as exc:
            logger.error("Tuya control error: %s", exc)
            return {"success": False, "error": str(exc)}

    def get_state(self, device_id: str) -> Dict[str, Any]:
        real_id = device_id.replace("tuya_", "", 1)
        try:
            result = self._api_get(f"/v1.0/devices/{real_id}/status")
            if result.get("success"):
                return {item["code"]: item["value"] for item in result.get("result", [])}
        except Exception as exc:
            logger.error("Tuya get_state error: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Natural-language command helpers
# ---------------------------------------------------------------------------

def _fuzzy_match(query: str, candidates: List[str], threshold: float = 0.55) -> Optional[str]:
    """Return the best fuzzy match from *candidates* or None."""
    query_lower = query.lower()
    best, best_score = None, 0.0
    for c in candidates:
        score = SequenceMatcher(None, query_lower, c.lower()).ratio()
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= threshold else None


# Action keyword mapping used by parse_command
_ACTION_KEYWORDS: Dict[str, str] = {
    "turn on": "turn_on",
    "switch on": "turn_on",
    "enable": "turn_on",
    "turn off": "turn_off",
    "switch off": "turn_off",
    "disable": "turn_off",
    "toggle": "toggle",
    "dim": "set_brightness",
    "brighten": "set_brightness",
    "brightness": "set_brightness",
    "set brightness": "set_brightness",
    "color": "set_color",
    "set color": "set_color",
    "colour": "set_color",
    "temperature": "set_temperature",
    "set temperature": "set_temperature",
    "warm": "set_color_temperature",
    "cool": "set_color_temperature",
    "lock": "lock",
    "unlock": "unlock",
}


def parse_command(
    text: str, device_names: List[str]
) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """
    Parse a natural-language smart home command.

    Returns *(matched_device_name, action, params)*.
    Any of the values may be ``None`` / empty if parsing fails.
    """
    text_lower = text.lower().strip()
    action: Optional[str] = None
    params: Dict[str, Any] = {}

    # Detect action -- try longest keyword phrases first
    for phrase in sorted(_ACTION_KEYWORDS, key=len, reverse=True):
        if phrase in text_lower:
            action = _ACTION_KEYWORDS[phrase]
            text_lower = text_lower.replace(phrase, "").strip()
            break

    # Extract a numeric value if present (e.g. "brightness 75", "to 22 degrees")
    import re
    num_match = re.search(r"(\d+)", text_lower)
    if num_match:
        value = int(num_match.group(1))
        if action == "set_brightness":
            params["brightness"] = value
        elif action in ("set_temperature", "set_color_temperature"):
            params["temperature"] = value
        text_lower = text_lower[:num_match.start()] + text_lower[num_match.end():]

    # Clean up filler words
    for filler in ("the", "my", "a", "an", "please", "to", "in", "set", "degrees", "%"):
        text_lower = text_lower.replace(filler, "")
    remainder = " ".join(text_lower.split()).strip()

    # Fuzzy-match remaining text to a device name
    device_match = _fuzzy_match(remainder, device_names) if remainder else None

    return device_match, action, params


# ---------------------------------------------------------------------------
# Convenience shortcut functions
# ---------------------------------------------------------------------------

def turn_on(hub: "SmartHomeHub", device_id: str) -> Dict[str, Any]:
    return hub.control(device_id, "turn_on")


def turn_off(hub: "SmartHomeHub", device_id: str) -> Dict[str, Any]:
    return hub.control(device_id, "turn_off")


def set_brightness(hub: "SmartHomeHub", device_id: str, level: int) -> Dict[str, Any]:
    return hub.control(device_id, "set_brightness", brightness=level)


def set_temperature(hub: "SmartHomeHub", device_id: str, temp: int) -> Dict[str, Any]:
    return hub.control(device_id, "set_temperature", temperature=temp)


def set_color(hub: "SmartHomeHub", device_id: str, hue: int, saturation: int = 254, brightness: int = 254) -> Dict[str, Any]:
    return hub.control(device_id, "set_color", hue=hue, saturation=saturation, brightness=brightness)


# ---------------------------------------------------------------------------
# SmartHomeHub -- central controller
# ---------------------------------------------------------------------------

class SmartHomeHub:
    """
    Central smart home controller that aggregates multiple backends,
    maintains a device cache, and provides unified control, grouping,
    and scene management.
    """

    CONFIG_PATH = Path("config/smart_home_config.json")

    def __init__(self):
        self._backends: Dict[str, SmartHomeBackend] = {}
        self._devices: Dict[str, SmartDevice] = {}  # device_id -> SmartDevice
        self._groups: Dict[str, DeviceGroup] = {}
        self._scenes: Dict[str, Scene] = {}
        self._lock = threading.Lock()

        self._poll_thread: Optional[threading.Thread] = None
        self._polling = False
        self._poll_interval: int = 60  # seconds

        self._load_config()
        logger.info("SmartHomeHub initialised (%d cached devices)", len(self._devices))

    # -- persistence --------------------------------------------------------

    def _config_data(self) -> dict:
        return {
            "devices": {did: d.to_dict() for did, d in self._devices.items()},
            "groups": {
                g.name: {"name": g.name, "device_ids": g.device_ids}
                for g in self._groups.values()
            },
            "scenes": {
                s.name: {
                    "name": s.name,
                    "actions": s.actions,
                    "created_at": s.created_at,
                }
                for s in self._scenes.values()
            },
            "poll_interval": self._poll_interval,
        }

    def _save_config(self):
        try:
            self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.CONFIG_PATH.write_text(
                json.dumps(self._config_data(), indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.error("Failed to save smart home config: %s", exc)

    def _load_config(self):
        if not self.CONFIG_PATH.exists():
            return
        try:
            data = json.loads(self.CONFIG_PATH.read_text(encoding="utf-8"))
            for did, ddata in data.get("devices", {}).items():
                self._devices[did] = SmartDevice.from_dict(ddata)
            for gdata in data.get("groups", {}).values():
                grp = DeviceGroup(name=gdata["name"], device_ids=gdata.get("device_ids", []))
                self._groups[grp.name] = grp
            for sdata in data.get("scenes", {}).values():
                scene = Scene(
                    name=sdata["name"],
                    actions=sdata.get("actions", []),
                    created_at=sdata.get("created_at", ""),
                )
                self._scenes[scene.name] = scene
            self._poll_interval = data.get("poll_interval", 60)
        except Exception as exc:
            logger.error("Failed to load smart home config: %s", exc)

    # -- backend management -------------------------------------------------

    def register_backend(self, backend: SmartHomeBackend):
        """Register a new smart home backend."""
        with self._lock:
            self._backends[backend.name] = backend
        logger.info("Registered smart home backend: %s", backend.name)

    def list_backends(self) -> List[str]:
        return list(self._backends.keys())

    # -- device discovery & cache -------------------------------------------

    def discover_devices(self) -> List[SmartDevice]:
        """Run discovery across all registered backends and update cache."""
        all_devices: List[SmartDevice] = []
        for bname, backend in self._backends.items():
            try:
                found = backend.discover()
                for dev in found:
                    with self._lock:
                        self._devices[dev.id] = dev
                all_devices.extend(found)
                logger.info("Discovered %d devices from %s", len(found), bname)
            except Exception as exc:
                logger.error("Discovery error for backend %s: %s", bname, exc)
        self._save_config()
        return all_devices

    def get_device(self, device_id: str) -> Optional[SmartDevice]:
        """Return a device by its ID (from cache)."""
        return self._devices.get(device_id)

    def find_device_by_name(self, name: str) -> Optional[SmartDevice]:
        """Fuzzy-find a device by its friendly name."""
        name_map = {d.name: d for d in self._devices.values()}
        match = _fuzzy_match(name, list(name_map.keys()))
        return name_map.get(match) if match else None

    def get_all_devices(self) -> List[SmartDevice]:
        return list(self._devices.values())

    # -- device control -----------------------------------------------------

    def control(self, device_id: str, action: str, **params) -> Dict[str, Any]:
        """Send a control command to a single device."""
        device = self._devices.get(device_id)
        if device is None:
            return {"error": f"Device '{device_id}' not found"}

        backend = self._backends.get(device.backend)
        if backend is None:
            return {"error": f"Backend '{device.backend}' not registered"}

        result = backend.control(device_id, action, **params)

        # Refresh state after control
        try:
            new_state = backend.get_state(device_id)
            with self._lock:
                device.state = new_state
                device.last_seen = datetime.now().isoformat()
            self._save_config()
        except Exception:
            pass

        return result

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Return dict mapping device IDs to their current state dicts."""
        status: Dict[str, Dict[str, Any]] = {}
        for did, dev in self._devices.items():
            status[did] = {
                "name": dev.name,
                "type": dev.device_type,
                "room": dev.room,
                "is_online": dev.is_online,
                "state": dev.state,
                "last_seen": dev.last_seen,
            }
        return status

    # -- device groups ------------------------------------------------------

    def create_group(self, name: str, device_ids: List[str]) -> DeviceGroup:
        """Create or update a named device group."""
        group = DeviceGroup(name=name, device_ids=device_ids)
        with self._lock:
            self._groups[name] = group
        self._save_config()
        logger.info("Created group '%s' with %d devices", name, len(device_ids))
        return group

    def get_group(self, name: str) -> Optional[DeviceGroup]:
        return self._groups.get(name)

    def list_groups(self) -> List[str]:
        return list(self._groups.keys())

    def group_control(self, group_name: str, action: str, **params) -> Dict[str, Any]:
        """Apply *action* to every device in the named group."""
        group = self._groups.get(group_name)
        if group is None:
            return {"error": f"Group '{group_name}' not found"}

        results: Dict[str, Any] = {}
        for did in group.device_ids:
            results[did] = self.control(did, action, **params)
        return results

    # -- scenes -------------------------------------------------------------

    def create_scene(self, name: str, actions: List[Dict[str, Any]]) -> Scene:
        """
        Create (or overwrite) a scene.

        *actions* is a list of dicts, each with keys:
            device_id, action, params (optional dict)
        """
        scene = Scene(name=name, actions=actions)
        with self._lock:
            self._scenes[name] = scene
        self._save_config()
        logger.info("Created scene '%s' with %d actions", name, len(actions))
        return scene

    def activate_scene(self, name: str) -> Dict[str, Any]:
        """Activate all actions in the named scene."""
        scene = self._scenes.get(name)
        if scene is None:
            return {"error": f"Scene '{name}' not found"}

        results: Dict[str, Any] = {}
        for act in scene.actions:
            did = act.get("device_id", "")
            action = act.get("action", "")
            params = act.get("params", {})
            results[did] = self.control(did, action, **params)
        logger.info("Activated scene '%s'", name)
        return results

    def list_scenes(self) -> List[str]:
        return list(self._scenes.keys())

    def delete_scene(self, name: str) -> bool:
        with self._lock:
            removed = self._scenes.pop(name, None) is not None
        if removed:
            self._save_config()
        return removed

    # -- natural language ---------------------------------------------------

    def process_command(self, text: str) -> Dict[str, Any]:
        """
        Parse a natural-language command and execute it.

        Returns a result dict with keys *device*, *action*, *params*, *result*.
        """
        device_names = [d.name for d in self._devices.values()]
        matched_name, action, params = parse_command(text, device_names)

        if matched_name is None:
            return {"error": "Could not identify a device in your command"}
        if action is None:
            return {"error": "Could not determine what action to perform"}

        device = self.find_device_by_name(matched_name)
        if device is None:
            return {"error": f"Device '{matched_name}' not found"}

        result = self.control(device.id, action, **params)
        return {
            "device": device.name,
            "device_id": device.id,
            "action": action,
            "params": params,
            "result": result,
        }

    # -- background polling -------------------------------------------------

    def start_polling(self, interval: Optional[int] = None):
        """Start a background thread that periodically refreshes device states."""
        if self._polling:
            return
        if interval is not None:
            self._poll_interval = interval
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("Started device polling every %ds", self._poll_interval)

    def stop_polling(self):
        self._polling = False
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
            self._poll_thread = None
        logger.info("Stopped device polling")

    def _poll_loop(self):
        while self._polling:
            for did, dev in list(self._devices.items()):
                if not self._polling:
                    break
                backend = self._backends.get(dev.backend)
                if backend is None:
                    continue
                try:
                    new_state = backend.get_state(did)
                    with self._lock:
                        dev.state = new_state
                        dev.is_online = bool(new_state)
                        dev.last_seen = datetime.now().isoformat()
                except Exception:
                    with self._lock:
                        dev.is_online = False
            self._save_config()
            # Sleep in small increments so we can stop quickly
            for _ in range(self._poll_interval * 10):
                if not self._polling:
                    break
                time.sleep(0.1)

    # -- summary / LADA integration -----------------------------------------

    def summary(self) -> str:
        """Human-readable summary for LADA voice output."""
        total = len(self._devices)
        online = sum(1 for d in self._devices.values() if d.is_online)
        by_type: Dict[str, int] = {}
        for d in self._devices.values():
            by_type[d.device_type] = by_type.get(d.device_type, 0) + 1

        lines = [f"Smart home: {total} devices, {online} online."]
        for dtype, count in sorted(by_type.items()):
            lines.append(f"  {dtype}: {count}")
        lines.append(f"Groups: {len(self._groups)}  Scenes: {len(self._scenes)}")
        return "\n".join(lines)
