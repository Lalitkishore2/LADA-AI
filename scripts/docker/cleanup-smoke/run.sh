#!/usr/bin/env bash
set -euo pipefail

cd /repo

export LADA_STATE_DIR="/tmp/lada-test"
export LADA_CONFIG_PATH="${LADA_STATE_DIR}/lada.json"

echo "==> Build"
pnpm build

echo "==> Seed state"
mkdir -p "${LADA_STATE_DIR}/credentials"
mkdir -p "${LADA_STATE_DIR}/agents/main/sessions"
echo '{}' >"${LADA_CONFIG_PATH}"
echo 'creds' >"${LADA_STATE_DIR}/credentials/marker.txt"
echo 'session' >"${LADA_STATE_DIR}/agents/main/sessions/sessions.json"

echo "==> Reset (config+creds+sessions)"
pnpm lada reset --scope config+creds+sessions --yes --non-interactive

test ! -f "${LADA_CONFIG_PATH}"
test ! -d "${LADA_STATE_DIR}/credentials"
test ! -d "${LADA_STATE_DIR}/agents/main/sessions"

echo "==> Recreate minimal config"
mkdir -p "${LADA_STATE_DIR}/credentials"
echo '{}' >"${LADA_CONFIG_PATH}"

echo "==> Uninstall (state only)"
pnpm lada uninstall --state --yes --non-interactive

test ! -d "${LADA_STATE_DIR}"

echo "OK"

