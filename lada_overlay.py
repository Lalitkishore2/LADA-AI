#!/usr/bin/env python3
"""
LADA Desktop Floating Overlay
──────────────────────────────
A draggable, always-on-top, collapsible mini-assistant that connects to
your local LADA server and shows real-time conversation.

Usage:
    python lada_overlay.py [--host localhost] [--port 5000] [--token <your-token>]

Hotkey:  Ctrl+Shift+L  (global, powered by keyboard lib if installed)
"""

import asyncio
import base64
import io
import json
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
import argparse

# ── Optional deps ──────────────────────────────────────────────
try:
    import customtkinter as ctk
    USE_CTK = True
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
except ImportError:
    USE_CTK = False

try:
    import websocket  # websocket-client
    HAS_WS = True
except ImportError:
    HAS_WS = False
    print("[LADA Overlay] websocket-client not found. Run: pip install websocket-client")

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import keyboard
    HAS_KB = True
except ImportError:
    HAS_KB = False

# ── Constants ──────────────────────────────────────────────────
ACCENT = "#10a37f"
BG_DARK = "#0d1117"
SURFACE = "#121923"
SURFACE2 = "#1a2431"
BORDER = "#2a3a4e"
TEXT = "#e2e8f0"
TEXT_DIM = "#9ba8b8"
COLLAPSED_SIZE = (60, 60)
EXPANDED_SIZE = (380, 560)


def parse_args():
    p = argparse.ArgumentParser(description="LADA Desktop Overlay")
    p.add_argument("--host", default=os.getenv("LADA_HOST", "localhost"))
    p.add_argument("--port", type=int, default=int(os.getenv("LADA_PORT", "5000")))
    p.add_argument("--token", default=os.getenv("LADA_TOKEN", ""))
    p.add_argument("--no-hotkey", action="store_true")
    return p.parse_args()


# ── LADA Overlay Application ────────────────────────────────────
class LADAOverlay:
    def __init__(self, host="localhost", port=5000, token=""):
        self.host = host
        self.port = port
        self.token = token
        self.ws = None
        self.ws_thread = None
        self.expanded = True
        self._drag_x = 0
        self._drag_y = 0
        self.messages = []  # (role, text)

        self._build_window()
        self._build_ui()
        self._connect_ws()

    # ── Window ─────────────────────────────────────────────────
    def _build_window(self):
        self.root = tk.Tk()
        self.root.title("LADA")
        self.root.overrideredirect(True)   # borderless
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)
        self.root.configure(bg=BG_DARK)

        # Position bottom-right
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = EXPANDED_SIZE
        x = sw - w - 30
        y = sh - h - 60
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # Drag support
        self.root.bind("<ButtonPress-1>",   self._on_drag_start)
        self.root.bind("<B1-Motion>",       self._on_drag_move)

    def _on_drag_start(self, e):
        self._drag_x = e.x
        self._drag_y = e.y

    def _on_drag_move(self, e):
        dx = e.x - self._drag_x
        dy = e.y - self._drag_y
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    # ── UI ─────────────────────────────────────────────────────
    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=1)

        # ── Header bar ────────────────────────────────────────
        hdr = tk.Frame(root, bg=SURFACE, height=48, padx=12)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        # Logo
        logo_lbl = tk.Label(hdr, text="⬡ LADA", fg=ACCENT, bg=SURFACE,
                            font=("Helvetica", 13, "bold"), cursor="fleur")
        logo_lbl.grid(row=0, column=0, padx=(0, 8), pady=10, sticky="w")
        logo_lbl.bind("<ButtonPress-1>",   self._on_drag_start)
        logo_lbl.bind("<B1-Motion>",       self._on_drag_move)

        # WS status dot
        self.ws_dot = tk.Canvas(hdr, width=8, height=8, bg=SURFACE, highlightthickness=0)
        self.ws_dot.grid(row=0, column=1, pady=10, sticky="w")
        self._draw_dot("#ef4444")

        # Screenshot btn
        ss_btn = tk.Button(hdr, text="📷", bg=SURFACE, fg=TEXT_DIM, relief="flat",
                           font=("Helvetica", 13), cursor="hand2",
                           command=self._take_screenshot_send)
        ss_btn.grid(row=0, column=2, padx=2, pady=8)

        # Collapse btn
        self.col_btn = tk.Button(hdr, text="⌄", bg=SURFACE, fg=TEXT_DIM, relief="flat",
                                  font=("Helvetica", 14, "bold"), cursor="hand2",
                                  command=self.toggle_expand)
        self.col_btn.grid(row=0, column=3, padx=2, pady=8)

        # Close
        close_btn = tk.Button(hdr, text="✕", bg=SURFACE, fg=TEXT_DIM, relief="flat",
                               font=("Helvetica", 12), cursor="hand2",
                               command=self.root.destroy)
        close_btn.grid(row=0, column=4, padx=(2, 0), pady=8)

        # ── Messages area ─────────────────────────────────────
        self.msg_frame = tk.Frame(root, bg=BG_DARK)
        self.msg_frame.grid(row=1, column=0, sticky="nsew", padx=1, pady=(0, 1))
        self.msg_frame.grid_rowconfigure(0, weight=1)
        self.msg_frame.grid_columnconfigure(0, weight=1)

        self.msg_text = tk.Text(
            self.msg_frame, bg=SURFACE, fg=TEXT, font=("Helvetica", 12),
            relief="flat", wrap="word", state="disabled",
            selectbackground=ACCENT, padx=12, pady=10,
            insertbackground=TEXT, highlightthickness=0,
        )
        self.msg_text.grid(row=0, column=0, sticky="nsew")

        sb = tk.Scrollbar(self.msg_frame, command=self.msg_text.yview, bg=SURFACE2, troughcolor=SURFACE2, width=6)
        sb.grid(row=0, column=1, sticky="ns")
        self.msg_text.config(yscrollcommand=sb.set)

        # Configure tags
        self.msg_text.tag_configure("user",      foreground=ACCENT,   font=("Helvetica", 12, "bold"))
        self.msg_text.tag_configure("assistant", foreground=TEXT,      font=("Helvetica", 12))
        self.msg_text.tag_configure("system",    foreground=TEXT_DIM,  font=("Helvetica", 11, "italic"))
        self.msg_text.tag_configure("ts",        foreground=BORDER,    font=("Helvetica", 10))

        # ── Input area ────────────────────────────────────────
        inp_frame = tk.Frame(root, bg=SURFACE2, padx=10, pady=8)
        inp_frame.grid(row=2, column=0, sticky="ew")
        inp_frame.grid_columnconfigure(0, weight=1)

        self.inp = tk.Text(inp_frame, height=2, bg=SURFACE, fg=TEXT,
                           font=("Helvetica", 12), relief="flat", wrap="word",
                           insertbackground=TEXT, highlightthickness=1,
                           highlightcolor=ACCENT, highlightbackground=BORDER,
                           padx=8, pady=6)
        self.inp.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.inp.bind("<Return>",       self._on_return)
        self.inp.bind("<Shift-Return>", lambda e: None)  # allow newline

        send_btn = tk.Button(inp_frame, text="▶", bg=ACCENT, fg="white", relief="flat",
                              font=("Helvetica", 14, "bold"), cursor="hand2",
                              width=3, command=self.send_message)
        send_btn.grid(row=0, column=1)

        # Initial greeting
        self._add_message("system", "🤖 LADA Overlay ready. Connecting...")

    # ── Helpers ────────────────────────────────────────────────
    def _draw_dot(self, color):
        self.ws_dot.delete("all")
        self.ws_dot.create_oval(0, 0, 8, 8, fill=color, outline="")

    def toggle_expand(self):
        self.expanded = not self.expanded
        if self.expanded:
            w, h = EXPANDED_SIZE
            self.col_btn.config(text="⌄")
            self.msg_frame.grid()
        else:
            w, h = COLLAPSED_SIZE
            self.col_btn.config(text="⌃")
            self.msg_frame.grid_remove()

        # Keep same top-right anchor
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _add_message(self, role, text):
        self.msg_text.config(state="normal")
        ts = time.strftime("%H:%M")
        prefix = {"user": "You", "assistant": "LADA", "system": "•"}.get(role, role)
        self.msg_text.insert("end", f"\n[{ts}] {prefix}\n", (role, "ts"))
        self.msg_text.insert("end", text + "\n", role)
        self.msg_text.see("end")
        self.msg_text.config(state="disabled")
        self.messages.append((role, text))

    def _on_return(self, e):
        if not e.state & 1:  # Shift not held
            self.send_message()
            return "break"

    def send_message(self):
        text = self.inp.get("1.0", "end").strip()
        if not text:
            return
        self.inp.delete("1.0", "end")
        self._add_message("user", text)
        self._ws_send({"type": "chat", "id": self._uid(),
                       "data": {"message": text}})

    def _uid(self):
        import uuid
        return str(uuid.uuid4())[:8]

    # ── Screenshot ─────────────────────────────────────────────
    def _take_screenshot_send(self):
        if not HAS_MSS:
            self._add_message("system", "⚠️ mss not installed (pip install mss)")
            return
        if not HAS_PIL:
            self._add_message("system", "⚠️ Pillow not installed (pip install Pillow)")
            return
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                shot = sct.grab(monitor)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                b64 = base64.b64encode(buf.getvalue()).decode()
            self._add_message("system", "📸 Screenshot captured — send your question to analyze it.")
            self._pending_screenshot = b64
        except Exception as e:
            self._add_message("system", f"⚠️ Screenshot error: {e}")

    # ── WebSocket ──────────────────────────────────────────────
    def _connect_ws(self):
        if not HAS_WS:
            self._add_message("system", "⚠️ websocket-client not installed")
            return
        self.ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self.ws_thread.start()

    def _ws_loop(self):
        url = f"ws://{self.host}:{self.port}/ws"
        if self.token:
            url += f"?token={self.token}"
        retry = 0
        while True:
            try:
                self.root.after(0, lambda: self._draw_dot("#f59e0b"))
                ws = websocket.WebSocketApp(
                    url,
                    on_open=self._ws_on_open,
                    on_message=self._ws_on_message,
                    on_error=self._ws_on_error,
                    on_close=self._ws_on_close,
                )
                self.ws = ws
                ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                pass
            retry += 1
            wait = min(30, 2 ** min(retry, 5))
            self.root.after(0, lambda: self._draw_dot("#ef4444"))
            time.sleep(wait)

    def _ws_on_open(self, ws):
        self.root.after(0, lambda: self._draw_dot("#10b981"))
        self.root.after(0, lambda: self._add_message("system", "✓ Connected to LADA server"))
        if self.token:
            ws.send(json.dumps({"type": "auth", "token": self.token}))

    def _ws_on_message(self, ws, msg_str):
        try:
            msg = json.loads(msg_str)
        except Exception:
            return
        mtype = msg.get("type", "")
        if mtype == "stream_chunk":
            delta = (msg.get("data") or {}).get("delta", "")
            if delta:
                self.root.after(0, lambda d=delta: self._stream_delta(d))
        elif mtype == "stream_end":
            self.root.after(0, self._stream_finalize)
        elif mtype in {"error", "auth_error"}:
            err = (msg.get("data") or {}).get("message", "error")
            self.root.after(0, lambda e=err: self._add_message("system", f"⚠️ {e}"))
        elif mtype == "computer_control_log":
            # Show live computer agent status
            data = msg.get("data", {})
            text = data.get("message", "")
            img_b64 = data.get("screenshot_b64", "")
            if text:
                self.root.after(0, lambda t=text: self._add_message("system", f"⚙️ {t}"))
            if img_b64 and HAS_PIL:
                # Optionally render the image inline if tkinter supports it, or just a notification
                self.root.after(0, lambda: self._add_message("system", "[Live Screenshot Received]"))

    def _ws_on_error(self, ws, error):
        self.root.after(0, lambda: self._draw_dot("#ef4444"))

    def _ws_on_close(self, ws, code, msg):
        self.root.after(0, lambda: self._draw_dot("#ef4444"))
        self.root.after(0, lambda: self._add_message("system", "⚡ Disconnected — reconnecting…"))

    def _stream_delta(self, delta):
        self.msg_text.config(state="normal")
        # Check if last line is a streaming placeholder
        last_char = self.msg_text.index("end-1c")
        tags_here = self.msg_text.tag_names(last_char)
        if "streaming" not in self.msg_text.tag_names():
            # Start new assistant message
            ts = time.strftime("%H:%M")
            self.msg_text.insert("end", f"\n[{ts}] LADA\n", ("assistant", "ts"))
            self.msg_text.insert("end", "", "assistant")
            self.msg_text.tag_add("streaming", "end-1c")
        self.msg_text.insert("end", delta, "assistant")
        self.msg_text.see("end")
        self.msg_text.config(state="disabled")

    def _stream_finalize(self):
        # Remove streaming marker — nothing needed since we insert inline
        pass

    def _ws_send(self, payload):
        if self.ws and self.ws.sock and self.ws.sock.connected:
            try:
                self.ws.send(json.dumps(payload))
            except Exception:
                pass

    # ── Run ────────────────────────────────────────────────────
    def run(self):
        self.root.mainloop()


# ── Global hotkey ──────────────────────────────────────────────
def register_hotkey(overlay):
    if not HAS_KB:
        return
    try:
        keyboard.add_hotkey("ctrl+shift+l", lambda: overlay.root.after(0, overlay.toggle_expand))
        print("[LADA Overlay] Hotkey Ctrl+Shift+L registered")
    except Exception as e:
        print(f"[LADA Overlay] Hotkey registration failed: {e}")


# ── Entry point ────────────────────────────────────────────────
if __name__ == "__main__":
    args = parse_args()
    print(f"[LADA Overlay] Connecting to {args.host}:{args.port}")
    overlay = LADAOverlay(host=args.host, port=args.port, token=args.token)
    if not args.no_hotkey:
        register_hotkey(overlay)
    overlay.run()
