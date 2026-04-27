"""
LADA WebUI Launcher — FastAPI + Browser

Starts LADA's API server in a background thread and opens the
browser-based LADA app at http://localhost:5000/app.

Password-protected. Accessible from any device on your local network.

Usage:
    python lada_webui.py
    python lada_webui.py --no-browser
    python main.py webui
    Double-click LADA-WebUI.bat
"""

import os
import sys
import time
import asyncio
import socket
import threading
import webbrowser
import logging
import subprocess
import re
import argparse
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

# Add project root to path
PROJECT_ROOT = str(Path(__file__).parent)
sys.path.insert(0, PROJECT_ROOT)

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure output is visible immediately when run from .bat on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

logger = logging.getLogger(__name__)

# Configuration from .env
LADA_API_HOST = "0.0.0.0"
LADA_API_PORT = int(os.getenv("LADA_API_PORT", os.getenv("PORT", "5000")))

# Global reference for graceful shutdown
_uvicorn_server = None


def start_api_server():
    """Start LADA API server in a background thread.

    Returns the uvicorn.Server instance for graceful shutdown.
    """
    global _uvicorn_server

    try:
        import uvicorn
        from modules.api_server import LADAAPIServer
    except ImportError as e:
        print(f"\n[LADA] Missing dependency: {e}")
        print("[LADA] Run: pip install fastapi uvicorn")
        sys.exit(1)

    api = LADAAPIServer(host=LADA_API_HOST, port=LADA_API_PORT)

    config = uvicorn.Config(
        api.app,
        host=LADA_API_HOST,
        port=LADA_API_PORT,
        log_level="warning"
    )
    server = uvicorn.Server(config)
    _uvicorn_server = server

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return server


def wait_for_api(timeout=120):
    """Poll LADA API until it responds."""
    url = f"http://localhost:{LADA_API_PORT}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urlopen(url, timeout=2)
            if resp.status == 200:
                return True
        except (URLError, OSError):
            pass
        time.sleep(0.5)
    print(f"\n[LADA] API server did not start within {timeout}s")
    return False


def _get_lan_ip():
    """Get the LAN IP address for remote access."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


_funnel_process = None


def _start_tailscale_funnel(local_port: int) -> str:
    """Start Tailscale Funnel for a free permanent public URL.

    Enabled when LADA_TAILSCALE_FUNNEL=true in .env and Tailscale is installed + logged in.
    Gives a permanent URL like https://machine-name.tailnet.ts.net/app (free, no domain needed).
    """
    global _funnel_process

    if os.getenv("LADA_TAILSCALE_FUNNEL", "false").lower() not in ("1", "true", "yes", "on"):
        return ""

    try:
        # Find tailscale binary
        tailscale_cmd = "tailscale"
        for candidate in [
            os.path.join(os.environ.get("ProgramFiles", ""), "Tailscale", "tailscale.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Tailscale", "tailscale.exe"),
        ]:
            if candidate and os.path.isfile(candidate):
                tailscale_cmd = candidate
                break

        # Get the Tailscale DNS name for this machine
        try:
            result = subprocess.run(
                [tailscale_cmd, "status", "--json"],
                capture_output=True, text=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                import json as _json
                status = _json.loads(result.stdout)
                dns_name = status.get("Self", {}).get("DNSName", "").rstrip(".")
            else:
                print("[LADA] Tailscale is not logged in. Run: tailscale login")
                return ""
        except Exception:
            dns_name = ""

        # Start funnel in background mode
        cmd = [tailscale_cmd, "funnel", "--bg", str(local_port)]
        _funnel_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        # Wait for funnel to start
        time.sleep(3)
        output = ""
        if _funnel_process.stdout:
            # Non-blocking read of available output
            import select
            try:
                output = _funnel_process.stdout.read()
            except Exception:
                pass

        if _funnel_process.poll() is not None and _funnel_process.returncode != 0:
            print("[LADA] Tailscale Funnel failed to start.")
            if output:
                for line in output.strip().splitlines()[-5:]:
                    print(f"[LADA]   {line}")
            print("[LADA] Enable Funnel at: https://login.tailscale.com/admin/machines")
            return ""

        # Build URL from DNS name
        if dns_name:
            public_url = f"https://{dns_name}/app"
        else:
            # Try to extract from funnel output
            url_match = re.search(r"https://[a-zA-Z0-9\.\-]+\.ts\.net", output or "")
            if url_match:
                public_url = url_match.group(0) + "/app"
            else:
                # Fallback: query funnel status
                try:
                    stat = subprocess.run(
                        [tailscale_cmd, "funnel", "status"],
                        capture_output=True, text=True, timeout=5,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    url_match = re.search(r"https://[a-zA-Z0-9\.\-]+\.ts\.net", stat.stdout or "")
                    public_url = url_match.group(0) + "/app" if url_match else ""
                except Exception:
                    public_url = ""

        if not public_url:
            print("[LADA] Tailscale Funnel started but could not determine public URL.")
            print("[LADA] Run 'tailscale funnel status' to check.")
        return public_url

    except FileNotFoundError:
        print("[LADA] Tailscale Funnel requested, but 'tailscale' is not installed.")
        print("[LADA] Install from: winget install tailscale.tailscale")
        return ""
    except Exception as e:
        print(f"[LADA] Tailscale Funnel start error: {e}")
        return ""


def main():
    """Launch LADA web app in the browser."""
    parser = argparse.ArgumentParser(description="LADA WebUI Launcher")
    parser.add_argument('--no-browser', action='store_true',
                        help='Start server without opening browser (for auto-start/headless)')
    args = parser.parse_args()

    # Configure basic logging
    logging.basicConfig(
        level=logging.WARNING,
        format='[%(levelname)s] %(message)s'
    )

    print("=" * 50)
    print("   LADA Web UI")
    print("=" * 50)

    # Step 1: Start LADA API server
    print(f"\n[1/3] Starting LADA API server on port {LADA_API_PORT}...")
    start_api_server()

    # Step 2: Wait for API to be ready
    print("[2/3] Waiting for API to be ready...")
    if not wait_for_api():
        print("[LADA] Server did not respond in time. Aborting.")
        sys.exit(1)

    app_url = f"http://localhost:{LADA_API_PORT}/app"
    lan_ip = _get_lan_ip()
    lan_url = f"http://{lan_ip}:{LADA_API_PORT}/app"

    public_url = _start_tailscale_funnel(LADA_API_PORT)

    # Step 3: Open browser (unless --no-browser)
    if not args.no_browser:
        print(f"[3/3] Opening browser at {app_url}")
        webbrowser.open(app_url)
    else:
        print("[3/3] Server ready (--no-browser mode, skipping browser)")

    print("\n" + "=" * 50)
    print("  LADA is running!")
    print(f"  Local:   {app_url}")
    print(f"  Network: {lan_url}")
    if public_url:
        print(f"  Public:  {public_url}")
    print(f"  API:     http://localhost:{LADA_API_PORT}")
    print(f"  Docs:    http://localhost:{LADA_API_PORT}/docs")
    print("=" * 50)
    print("\n  Password: configured via LADA_WEB_PASSWORD in .env")
    print("  Access from any device on your network using the Network URL.")
    if public_url:
        print("  Public URL is permanent (Tailscale Funnel, free). Accessible from anywhere.")
    else:
        print("  For a free permanent URL: set LADA_TAILSCALE_FUNNEL=true (see SETUP.md).")
    print("\n  Press Ctrl+C to stop.\n")

    # Wait for shutdown signal
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    print("\n[LADA] Shutting down...")
    if _funnel_process:
        try:
            _funnel_process.terminate()
        except Exception:
            pass
    if _uvicorn_server:
        _uvicorn_server.should_exit = True
    print("[LADA] Goodbye!")


if __name__ == "__main__":
    main()
