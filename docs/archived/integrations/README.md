# Archived Integrations

This folder contains integration modules that are intentionally removed from active runtime wiring but preserved for recovery and future reactivation.

Archived on 2026-03-30:
- alexa_hybrid.py
- moltbot_controller.py
- moltbot_firmware.ino
- openclaw_gateway.py
- openclaw_skills.py

Why archived:
- Not currently wired into active runtime paths.
- Not used in current deployment profile.
- Kept for historical reference and possible future reactivation.

Reactivation checklist:
1. Move the module back to integrations/.
2. Restore any related TYPE_CHECKING exports in integrations/__init__.py.
3. Re-register required services in core/services.py.
4. Re-wire tool handlers and executor paths if needed.
5. Add or update tests and run regression checks.
