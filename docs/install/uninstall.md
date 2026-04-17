---
summary: "Uninstall LADA completely (CLI, service, state, workspace)"
read_when:
  - You want to remove LADA from a machine
  - The gateway service is still running after uninstall
title: "Uninstall"
---

# Uninstall

Two paths:

- **Easy path** if `lada` is still installed.
- **Manual service removal** if the CLI is gone but the service is still running.

## Easy path (CLI still installed)

Recommended: use the built-in uninstaller:

```bash
lada uninstall
```

Non-interactive (automation / npx):

```bash
lada uninstall --all --yes --non-interactive
npx -y lada uninstall --all --yes --non-interactive
```

Manual steps (same result):

1. Stop the gateway service:

```bash
lada gateway stop
```

2. Uninstall the gateway service (launchd/systemd/schtasks):

```bash
lada gateway uninstall
```

3. Delete state + config:

```bash
rm -rf "${LADA_STATE_DIR:-$HOME/.lada}"
```

If you set `LADA_CONFIG_PATH` to a custom location outside the state dir, delete that file too.

4. Delete your workspace (optional, removes agent files):

```bash
rm -rf ~/.lada/workspace
```

5. Remove the CLI install (pick the one you used):

```bash
npm rm -g lada
pnpm remove -g lada
bun remove -g lada
```

6. If you installed the macOS app:

```bash
rm -rf /Applications/LADA.app
```

Notes:

- If you used profiles (`--profile` / `LADA_PROFILE`), repeat step 3 for each state dir (defaults are `~/.lada-<profile>`).
- In remote mode, the state dir lives on the **gateway host**, so run steps 1-4 there too.

## Manual service removal (CLI not installed)

Use this if the gateway service keeps running but `lada` is missing.

### macOS (launchd)

Default label is `ai.lada.gateway` (or `ai.lada.<profile>`; legacy `com.lada.*` may still exist):

```bash
launchctl bootout gui/$UID/ai.lada.gateway
rm -f ~/Library/LaunchAgents/ai.lada.gateway.plist
```

If you used a profile, replace the label and plist name with `ai.lada.<profile>`. Remove any legacy `com.lada.*` plists if present.

### Linux (systemd user unit)

Default unit name is `lada-gateway.service` (or `lada-gateway-<profile>.service`):

```bash
systemctl --user disable --now lada-gateway.service
rm -f ~/.config/systemd/user/lada-gateway.service
systemctl --user daemon-reload
```

### Windows (Scheduled Task)

Default task name is `LADA Gateway` (or `LADA Gateway (<profile>)`).
The task script lives under your state dir.

```powershell
schtasks /Delete /F /TN "LADA Gateway"
Remove-Item -Force "$env:USERPROFILE\.lada\gateway.cmd"
```

If you used a profile, delete the matching task name and `~\.lada-<profile>\gateway.cmd`.

## Normal install vs source checkout

### Normal install (install.sh / npm / pnpm / bun)

If you used `https://lada.ai/install.sh` or `install.ps1`, the CLI was installed with `npm install -g lada@latest`.
Remove it with `npm rm -g lada` (or `pnpm remove -g` / `bun remove -g` if you installed that way).

### Source checkout (git clone)

If you run from a repo checkout (`git clone` + `lada ...` / `bun run lada ...`):

1. Uninstall the gateway service **before** deleting the repo (use the easy path above or manual service removal).
2. Delete the repo directory.
3. Remove state + workspace as shown above.

