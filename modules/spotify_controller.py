"""
LADA v9.0 - Spotify Full Control
Complete Spotify integration for JARVIS-level music automation.

Features:
- OAuth2 PKCE authentication (client-side, no server required)
- Playback control (play, pause, skip, volume, seek, shuffle, repeat)
- Search and browse (tracks, albums, artists, playlists)
- Queue management
- Device management and playback transfer
- Playlist creation and editing
- Natural language helpers for voice commands
- Token persistence and automatic refresh
"""

import os
import json
import time
import base64
import hashlib
import secrets
import logging
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, List, Any, Optional
from threading import Thread

logger = logging.getLogger(__name__)

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False
    logger.warning("[!] requests library not available - pip install requests")


# ---------------------------------------------------------------------------
# Spotify API constants
# ---------------------------------------------------------------------------
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

SCOPES = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-read-recently-played",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read",
    "user-library-modify",
    "user-top-read",
    "streaming",
])

LOCAL_REDIRECT_PORT = 8891
REDIRECT_URI = f"http://localhost:{LOCAL_REDIRECT_PORT}/callback"


# ---------------------------------------------------------------------------
# Tiny callback server for the PKCE redirect
# ---------------------------------------------------------------------------
class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Captures the authorization code from Spotify's redirect."""

    auth_code: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        if "code" in params:
            _OAuthCallbackHandler.auth_code = params["code"][0]
            body = (
                "<html><body><h2>Spotify connected to LADA!</h2>"
                "<p>You can close this tab and return to LADA.</p></body></html>"
            )
        else:
            _OAuthCallbackHandler.error = params.get("error", ["unknown"])[0]
            body = (
                f"<html><body><h2>Authorization failed</h2>"
                f"<p>{_OAuthCallbackHandler.error}</p></body></html>"
            )

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    # Silence request logs
    def log_message(self, format, *args):
        pass


# ---------------------------------------------------------------------------
# SpotifyController
# ---------------------------------------------------------------------------
class SpotifyController:
    """
    Spotify Web API integration for LADA.

    Setup:
        1. Go to https://developer.spotify.com/dashboard
        2. Create an app (set redirect URI to http://localhost:8891/callback)
        3. Copy the Client ID
        4. Set the environment variable SPOTIFY_CLIENT_ID  -or-
           add "client_id" to config/spotify_auth.json
    """

    def __init__(self, auth_path: str = "config/spotify_auth.json"):
        self.auth_path = Path(auth_path)
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: float = 0.0
        self.client_id: Optional[str] = None
        self.initialized = False

        if not REQUESTS_OK:
            logger.warning("[!] requests not installed - Spotify features disabled")
            return

        self._load_auth()

    # ------------------------------------------------------------------
    # Authentication helpers
    # ------------------------------------------------------------------
    def _load_auth(self):
        """Load persisted tokens and client_id from disk / env."""
        self.client_id = os.environ.get("SPOTIFY_CLIENT_ID")

        if self.auth_path.exists():
            try:
                data = json.loads(self.auth_path.read_text(encoding="utf-8"))
                self.client_id = self.client_id or data.get("client_id")
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                self.token_expiry = data.get("token_expiry", 0.0)
                logger.info("[Spotify] Auth data loaded from %s", self.auth_path)
            except Exception as exc:
                logger.error("[Spotify] Failed to read auth file: %s", exc)

        if self.access_token and self.refresh_token:
            self.initialized = True

    def _save_auth(self):
        """Persist tokens to disk."""
        self.auth_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "client_id": self.client_id,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_expiry": self.token_expiry,
        }
        self.auth_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("[Spotify] Auth data saved to %s", self.auth_path)

    @staticmethod
    def _generate_pkce_pair() -> tuple:
        """Return (code_verifier, code_challenge) for PKCE."""
        verifier = secrets.token_urlsafe(64)[:128]
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return verifier, challenge

    def authenticate(self, timeout: int = 120) -> bool:
        """
        Run the full OAuth2 PKCE flow.

        Opens the user's browser, spins up a tiny local server to capture the
        redirect, exchanges the code for tokens, and persists them.

        Args:
            timeout: Seconds to wait for the user to authorize.

        Returns:
            True if authentication succeeded.
        """
        if not self.client_id:
            logger.error(
                "[Spotify] No client_id. Set SPOTIFY_CLIENT_ID env var or add it "
                "to %s", self.auth_path
            )
            return False

        verifier, challenge = self._generate_pkce_pair()
        state = secrets.token_urlsafe(16)

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }
        auth_url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"

        # Reset handler state
        _OAuthCallbackHandler.auth_code = None
        _OAuthCallbackHandler.error = None

        server = HTTPServer(("127.0.0.1", LOCAL_REDIRECT_PORT), _OAuthCallbackHandler)
        server.timeout = timeout

        logger.info("[Spotify] Opening browser for authorization...")
        webbrowser.open(auth_url)

        # Serve a single request (the redirect)
        server_thread = Thread(target=server.handle_request, daemon=True)
        server_thread.start()
        server_thread.join(timeout=timeout)
        server.server_close()

        if _OAuthCallbackHandler.error:
            logger.error("[Spotify] Auth error: %s", _OAuthCallbackHandler.error)
            return False

        code = _OAuthCallbackHandler.auth_code
        if not code:
            logger.error("[Spotify] No authorization code received (timed out?).")
            return False

        # Exchange code for tokens
        return self._exchange_code(code, verifier)

    def _exchange_code(self, code: str, verifier: str) -> bool:
        """Exchange an authorization code for access & refresh tokens."""
        payload = {
            "client_id": self.client_id,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        }
        try:
            resp = requests.post(SPOTIFY_TOKEN_URL, data=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access_token"]
            self.refresh_token = data.get("refresh_token")
            self.token_expiry = time.time() + data.get("expires_in", 3600) - 60
            self.initialized = True
            self._save_auth()
            logger.info("[Spotify] Authenticated successfully.")
            return True
        except Exception as exc:
            logger.error("[Spotify] Token exchange failed: %s", exc)
            return False

    def _refresh_access_token(self) -> bool:
        """Use the refresh token to obtain a new access token."""
        if not self.refresh_token or not self.client_id:
            return False

        payload = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        try:
            resp = requests.post(SPOTIFY_TOKEN_URL, data=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access_token"]
            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]
            self.token_expiry = time.time() + data.get("expires_in", 3600) - 60
            self._save_auth()
            logger.info("[Spotify] Token refreshed.")
            return True
        except Exception as exc:
            logger.error("[Spotify] Token refresh failed: %s", exc)
            return False

    def _ensure_token(self) -> bool:
        """Ensure a valid access token is available, refreshing if needed."""
        if not self.initialized:
            return False
        if time.time() >= self.token_expiry:
            return self._refresh_access_token()
        return True

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        if not self._ensure_token():
            return None
        url = f"{SPOTIFY_API_BASE}{endpoint}"
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
            if resp.status_code == 204:
                return {}
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            logger.error("[Spotify] GET %s -> %s", endpoint, exc)
            return None
        except Exception as exc:
            logger.error("[Spotify] GET %s error: %s", endpoint, exc)
            return None

    def _put(self, endpoint: str, payload: Optional[Dict] = None) -> bool:
        if not self._ensure_token():
            return False
        url = f"{SPOTIFY_API_BASE}{endpoint}"
        try:
            resp = requests.put(
                url, headers=self._headers(),
                json=payload if payload else None, timeout=10,
            )
            if resp.status_code in (200, 202, 204):
                return True
            resp.raise_for_status()
            return True
        except requests.HTTPError as exc:
            logger.error("[Spotify] PUT %s -> %s", endpoint, exc)
            return False
        except Exception as exc:
            logger.error("[Spotify] PUT %s error: %s", endpoint, exc)
            return False

    def _post(self, endpoint: str, payload: Optional[Dict] = None,
              params: Optional[Dict] = None) -> Optional[Dict]:
        if not self._ensure_token():
            return None
        url = f"{SPOTIFY_API_BASE}{endpoint}"
        try:
            resp = requests.post(
                url, headers=self._headers(),
                json=payload, params=params, timeout=10,
            )
            if resp.status_code == 204:
                return {}
            resp.raise_for_status()
            try:
                return resp.json()
            except ValueError:
                return {}
        except requests.HTTPError as exc:
            logger.error("[Spotify] POST %s -> %s", endpoint, exc)
            return None
        except Exception as exc:
            logger.error("[Spotify] POST %s error: %s", endpoint, exc)
            return None

    def _delete(self, endpoint: str, payload: Optional[Dict] = None) -> bool:
        if not self._ensure_token():
            return False
        url = f"{SPOTIFY_API_BASE}{endpoint}"
        try:
            resp = requests.delete(
                url, headers=self._headers(),
                json=payload, timeout=10,
            )
            if resp.status_code in (200, 202, 204):
                return True
            resp.raise_for_status()
            return True
        except requests.HTTPError as exc:
            logger.error("[Spotify] DELETE %s -> %s", endpoint, exc)
            return False
        except Exception as exc:
            logger.error("[Spotify] DELETE %s error: %s", endpoint, exc)
            return False

    def _not_connected(self, action: str = "do that") -> str:
        """Return a helpful fallback message when not authenticated."""
        return (
            f"I can't {action} because Spotify isn't connected yet. "
            "Say 'connect Spotify' and I'll walk you through the setup."
        )

    # ------------------------------------------------------------------
    # Playback control
    # ------------------------------------------------------------------
    def play(self, uri: Optional[str] = None, device_id: Optional[str] = None) -> str:
        """
        Resume playback or start playing a specific Spotify URI.

        Args:
            uri: A Spotify URI (track, album, playlist, artist).
                 e.g. 'spotify:track:6rqhFgbbKwnb9MLmUQDhG6'
            device_id: Target device. Uses active device if omitted.

        Returns:
            Human-readable status string.
        """
        if not self.initialized:
            return self._not_connected("play music")

        params = {}
        if device_id:
            params["device_id"] = device_id

        payload = None
        if uri:
            if ":track:" in uri:
                payload = {"uris": [uri]}
            else:
                # Albums, playlists, artists use context_uri
                payload = {"context_uri": uri}

        endpoint = "/me/player/play"
        if params:
            endpoint += "?" + urllib.parse.urlencode(params)

        if self._put(endpoint, payload):
            return "Playback started." if uri else "Resumed playback."
        return "Failed to start playback. Make sure Spotify is open on a device."

    def pause(self) -> str:
        """Pause the current playback."""
        if not self.initialized:
            return self._not_connected("pause music")
        if self._put("/me/player/pause"):
            return "Playback paused."
        return "Failed to pause playback."

    def next_track(self) -> str:
        """Skip to the next track."""
        if not self.initialized:
            return self._not_connected("skip tracks")
        if self._post("/me/player/next") is not None:
            return "Skipped to next track."
        return "Failed to skip track."

    def previous_track(self) -> str:
        """Go back to the previous track."""
        if not self.initialized:
            return self._not_connected("go back a track")
        if self._post("/me/player/previous") is not None:
            return "Went back to the previous track."
        return "Failed to go to previous track."

    def set_volume(self, level: int) -> str:
        """
        Set playback volume.

        Args:
            level: Volume percentage, 0-100.
        """
        if not self.initialized:
            return self._not_connected("change the volume")
        level = max(0, min(100, level))
        if self._put(f"/me/player/volume?volume_percent={level}"):
            return f"Volume set to {level}%."
        return "Failed to set volume."

    def seek(self, position_ms: int) -> str:
        """
        Seek to a position in the current track.

        Args:
            position_ms: Position in milliseconds.
        """
        if not self.initialized:
            return self._not_connected("seek in the track")
        position_ms = max(0, position_ms)
        if self._put(f"/me/player/seek?position_ms={position_ms}"):
            secs = position_ms // 1000
            minutes, seconds = divmod(secs, 60)
            return f"Seeked to {minutes}:{seconds:02d}."
        return "Failed to seek."

    def shuffle(self, state: bool) -> str:
        """Toggle shuffle mode."""
        if not self.initialized:
            return self._not_connected("toggle shuffle")
        val = "true" if state else "false"
        if self._put(f"/me/player/shuffle?state={val}"):
            return f"Shuffle {'enabled' if state else 'disabled'}."
        return "Failed to set shuffle."

    def repeat(self, state: str = "off") -> str:
        """
        Set repeat mode.

        Args:
            state: 'off', 'track', or 'context' (repeat playlist/album).
        """
        if not self.initialized:
            return self._not_connected("set repeat mode")
        if state not in ("off", "track", "context"):
            return "Repeat state must be 'off', 'track', or 'context'."
        if self._put(f"/me/player/repeat?state={state}"):
            labels = {"off": "off", "track": "current track", "context": "playlist/album"}
            return f"Repeat set to {labels[state]}."
        return "Failed to set repeat mode."

    def get_now_playing(self) -> Optional[Dict[str, Any]]:
        """
        Get details about the currently playing track.

        Returns:
            Dict with keys: track, artist, album, progress_ms, duration_ms,
            album_art_url, is_playing, uri  --  or None if nothing is playing.
        """
        if not self.initialized:
            return None
        data = self._get("/me/player/currently-playing")
        if not data or "item" not in data:
            return None

        item = data["item"]
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        images = item.get("album", {}).get("images", [])
        art_url = images[0]["url"] if images else None

        return {
            "track": item.get("name", "Unknown"),
            "artist": artists or "Unknown",
            "album": item.get("album", {}).get("name", "Unknown"),
            "progress_ms": data.get("progress_ms", 0),
            "duration_ms": item.get("duration_ms", 0),
            "album_art_url": art_url,
            "is_playing": data.get("is_playing", False),
            "uri": item.get("uri", ""),
        }

    # ------------------------------------------------------------------
    # Search and browse
    # ------------------------------------------------------------------
    def search(self, query: str, search_type: str = "track",
               limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search the Spotify catalogue.

        Args:
            query:       Search query string.
            search_type: Comma-separated types: track, album, artist, playlist.
            limit:       Max results per type (1-50).

        Returns:
            List of result dicts with id, name, type, uri, and extra metadata.
        """
        if not self.initialized:
            return []
        limit = max(1, min(50, limit))
        data = self._get("/search", params={
            "q": query,
            "type": search_type,
            "limit": limit,
        })
        if not data:
            return []

        results: List[Dict[str, Any]] = []
        for kind in search_type.split(","):
            kind = kind.strip()
            key = f"{kind}s"  # tracks, albums, artists, playlists
            items = data.get(key, {}).get("items", [])
            for item in items:
                entry: Dict[str, Any] = {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": kind,
                    "uri": item.get("uri"),
                }
                if kind == "track":
                    entry["artist"] = ", ".join(
                        a["name"] for a in item.get("artists", [])
                    )
                    entry["album"] = item.get("album", {}).get("name")
                    entry["duration_ms"] = item.get("duration_ms")
                elif kind == "album":
                    entry["artist"] = ", ".join(
                        a["name"] for a in item.get("artists", [])
                    )
                    entry["total_tracks"] = item.get("total_tracks")
                elif kind == "artist":
                    entry["genres"] = item.get("genres", [])
                    entry["followers"] = (
                        item.get("followers", {}).get("total", 0)
                    )
                elif kind == "playlist":
                    entry["owner"] = item.get("owner", {}).get("display_name")
                    entry["total_tracks"] = item.get("tracks", {}).get("total")
                results.append(entry)
        return results

    def get_playlists(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the authenticated user's playlists."""
        if not self.initialized:
            return []
        data = self._get("/me/playlists", params={"limit": min(50, limit)})
        if not data:
            return []
        playlists = []
        for item in data.get("items", []):
            playlists.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "uri": item.get("uri"),
                "total_tracks": item.get("tracks", {}).get("total", 0),
                "public": item.get("public"),
                "description": item.get("description", ""),
            })
        return playlists

    def get_playlist_tracks(self, playlist_id: str,
                            limit: int = 100) -> List[Dict[str, Any]]:
        """
        Return the tracks in a playlist.

        Args:
            playlist_id: Spotify playlist ID.
            limit:       Max tracks to return (1-100).
        """
        if not self.initialized:
            return []
        data = self._get(
            f"/playlists/{playlist_id}/tracks",
            params={"limit": min(100, limit)},
        )
        if not data:
            return []
        tracks = []
        for entry in data.get("items", []):
            t = entry.get("track")
            if not t:
                continue
            tracks.append({
                "id": t.get("id"),
                "name": t.get("name"),
                "artist": ", ".join(a["name"] for a in t.get("artists", [])),
                "album": t.get("album", {}).get("name"),
                "duration_ms": t.get("duration_ms"),
                "uri": t.get("uri"),
            })
        return tracks

    def get_recommendations(
        self,
        seed_tracks: Optional[List[str]] = None,
        seed_artists: Optional[List[str]] = None,
        seed_genres: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get track recommendations based on seeds.

        Spotify requires at least one seed and at most 5 total seeds across
        all three categories combined.
        """
        if not self.initialized:
            return []
        params: Dict[str, Any] = {"limit": min(100, limit)}
        if seed_tracks:
            params["seed_tracks"] = ",".join(seed_tracks[:5])
        if seed_artists:
            params["seed_artists"] = ",".join(seed_artists[:5])
        if seed_genres:
            params["seed_genres"] = ",".join(seed_genres[:5])
        if not any(k.startswith("seed_") for k in params):
            return []

        data = self._get("/recommendations", params=params)
        if not data:
            return []

        results = []
        for t in data.get("tracks", []):
            results.append({
                "id": t.get("id"),
                "name": t.get("name"),
                "artist": ", ".join(a["name"] for a in t.get("artists", [])),
                "album": t.get("album", {}).get("name"),
                "uri": t.get("uri"),
                "duration_ms": t.get("duration_ms"),
            })
        return results

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------
    def add_to_queue(self, uri: str) -> str:
        """
        Add a track to the playback queue.

        Args:
            uri: Spotify track URI.
        """
        if not self.initialized:
            return self._not_connected("add to queue")
        result = self._post("/me/player/queue", params={"uri": uri})
        if result is not None:
            return "Track added to queue."
        return "Failed to add track to queue."

    def get_queue(self) -> Optional[Dict[str, Any]]:
        """
        Get the current playback queue.

        Returns:
            Dict with 'currently_playing' and 'queue' (list of upcoming tracks).
        """
        if not self.initialized:
            return None
        data = self._get("/me/player/queue")
        if not data:
            return None

        def _summarize_track(t: Dict) -> Dict[str, Any]:
            return {
                "name": t.get("name", "Unknown"),
                "artist": ", ".join(a["name"] for a in t.get("artists", [])),
                "uri": t.get("uri", ""),
                "duration_ms": t.get("duration_ms", 0),
            }

        current = data.get("currently_playing")
        return {
            "currently_playing": _summarize_track(current) if current else None,
            "queue": [_summarize_track(t) for t in data.get("queue", [])],
        }

    # ------------------------------------------------------------------
    # Device management
    # ------------------------------------------------------------------
    def get_devices(self) -> List[Dict[str, Any]]:
        """Return available Spotify Connect devices."""
        if not self.initialized:
            return []
        data = self._get("/me/player/devices")
        if not data:
            return []
        devices = []
        for d in data.get("devices", []):
            devices.append({
                "id": d.get("id"),
                "name": d.get("name"),
                "type": d.get("type"),
                "is_active": d.get("is_active", False),
                "volume_percent": d.get("volume_percent"),
            })
        return devices

    def transfer_playback(self, device_id: str, start_playing: bool = True) -> str:
        """
        Transfer playback to a different device.

        Args:
            device_id:     Target device ID (from get_devices).
            start_playing: Whether to immediately start playback on the target.
        """
        if not self.initialized:
            return self._not_connected("switch devices")
        payload = {"device_ids": [device_id], "play": start_playing}
        if self._put("/me/player", payload):
            return "Playback transferred."
        return "Failed to transfer playback."

    # ------------------------------------------------------------------
    # Playlist management
    # ------------------------------------------------------------------
    def _get_user_id(self) -> Optional[str]:
        """Get the current user's Spotify ID."""
        data = self._get("/me")
        if data:
            return data.get("id")
        return None

    def create_playlist(self, name: str, description: str = "",
                        public: bool = False) -> Optional[Dict[str, Any]]:
        """
        Create a new playlist on the user's account.

        Args:
            name:        Playlist name.
            description: Optional description.
            public:      Whether the playlist is public.

        Returns:
            Dict with playlist id, name, and uri -- or None on failure.
        """
        if not self.initialized:
            return None
        user_id = self._get_user_id()
        if not user_id:
            logger.error("[Spotify] Could not determine user ID.")
            return None

        payload = {
            "name": name,
            "description": description,
            "public": public,
        }
        data = self._post(f"/users/{user_id}/playlists", payload)
        if data:
            return {
                "id": data.get("id"),
                "name": data.get("name"),
                "uri": data.get("uri"),
            }
        return None

    def add_to_playlist(self, playlist_id: str,
                        uris: List[str]) -> str:
        """
        Add tracks to a playlist.

        Args:
            playlist_id: Target playlist ID.
            uris:        List of Spotify track URIs to add.
        """
        if not self.initialized:
            return self._not_connected("modify playlists")
        if not uris:
            return "No tracks provided."
        # Spotify allows max 100 URIs per request
        for i in range(0, len(uris), 100):
            batch = uris[i : i + 100]
            result = self._post(
                f"/playlists/{playlist_id}/tracks",
                payload={"uris": batch},
            )
            if result is None:
                return f"Failed to add tracks (batch starting at index {i})."
        count = len(uris)
        return f"Added {count} track{'s' if count != 1 else ''} to the playlist."

    # ------------------------------------------------------------------
    # Natural language helpers (for voice / chat commands)
    # ------------------------------------------------------------------
    def play_by_name(self, query: str) -> str:
        """
        Search for a track by name and immediately play the best match.

        Handles queries like:
          - "play Bohemian Rhapsody"
          - "play something by The Weeknd"
          - "play the album Thriller"

        Args:
            query: Natural-language music query.

        Returns:
            Human-readable result string.
        """
        if not self.initialized:
            return self._not_connected("play music")

        # Determine search type from context clues
        lower = query.lower()
        if any(kw in lower for kw in ("album", "the album")):
            search_type = "album"
            query = lower.replace("the album", "").replace("album", "").strip()
        elif any(kw in lower for kw in ("playlist", "the playlist")):
            search_type = "playlist"
            query = lower.replace("the playlist", "").replace("playlist", "").strip()
        elif any(kw in lower for kw in ("artist", "by", "something by", "music by")):
            search_type = "artist"
            for prefix in ("something by", "music by", "songs by", "artist"):
                query = lower.replace(prefix, "").strip()
        else:
            search_type = "track"

        results = self.search(query, search_type=search_type, limit=1)
        if not results:
            return f"I couldn't find anything matching '{query}' on Spotify."

        best = results[0]
        uri = best["uri"]

        if search_type == "track":
            msg = self.play(uri)
            return f"Playing '{best['name']}' by {best.get('artist', 'Unknown')}. {msg}"
        elif search_type == "album":
            msg = self.play(uri)
            return f"Playing album '{best['name']}' by {best.get('artist', 'Unknown')}. {msg}"
        elif search_type == "playlist":
            msg = self.play(uri)
            return f"Playing playlist '{best['name']}'. {msg}"
        elif search_type == "artist":
            msg = self.play(uri)
            return f"Playing music by {best['name']}. {msg}"

        return "Something went wrong."

    def what_is_playing(self) -> str:
        """
        Return a natural-language summary of the current playback.

        Example output:
            "Now playing 'Blinding Lights' by The Weeknd from the album
             'After Hours' -- 1:23 / 3:20"
        """
        info = self.get_now_playing()
        if not info:
            if not self.initialized:
                return self._not_connected("check what's playing")
            return "Nothing is playing right now."

        track = info["track"]
        artist = info["artist"]
        album = info["album"]
        progress = info["progress_ms"] // 1000
        duration = info["duration_ms"] // 1000
        state = "Now playing" if info["is_playing"] else "Paused on"

        p_min, p_sec = divmod(progress, 60)
        d_min, d_sec = divmod(duration, 60)

        return (
            f"{state} '{track}' by {artist} from the album '{album}' "
            f"-- {p_min}:{p_sec:02d} / {d_min}:{d_sec:02d}"
        )

    # ------------------------------------------------------------------
    # Utility: formatted device list for voice
    # ------------------------------------------------------------------
    def list_devices_spoken(self) -> str:
        """Return a spoken-friendly device list."""
        devices = self.get_devices()
        if not devices:
            if not self.initialized:
                return self._not_connected("list devices")
            return "No Spotify devices found. Open Spotify on a device first."

        lines = []
        for i, d in enumerate(devices, 1):
            active = " (active)" if d["is_active"] else ""
            lines.append(f"{i}. {d['name']} ({d['type']}){active}")
        return "Available Spotify devices:\n" + "\n".join(lines)

    def list_playlists_spoken(self) -> str:
        """Return a spoken-friendly playlist list."""
        playlists = self.get_playlists()
        if not playlists:
            if not self.initialized:
                return self._not_connected("list playlists")
            return "You don't have any playlists yet."

        lines = []
        for i, p in enumerate(playlists, 1):
            lines.append(f"{i}. {p['name']} ({p['total_tracks']} tracks)")
        return "Your playlists:\n" + "\n".join(lines)
