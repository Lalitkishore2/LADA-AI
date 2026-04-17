#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${LADA_INSTALL_E2E_IMAGE:-lada-install-e2e:local}"
INSTALL_URL="${LADA_INSTALL_URL:-https://lada.bot/install.sh}"

OPENAI_API_KEY="${OPENAI_API_KEY:-}"
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
ANTHROPIC_API_TOKEN="${ANTHROPIC_API_TOKEN:-}"
LADA_E2E_MODELS="${LADA_E2E_MODELS:-}"

echo "==> Build image: $IMAGE_NAME"
docker build \
  -t "$IMAGE_NAME" \
  -f "$ROOT_DIR/scripts/docker/install-sh-e2e/Dockerfile" \
  "$ROOT_DIR/scripts/docker"

echo "==> Run E2E installer test"
docker run --rm \
  -e LADA_INSTALL_URL="$INSTALL_URL" \
  -e LADA_INSTALL_TAG="${LADA_INSTALL_TAG:-latest}" \
  -e LADA_E2E_MODELS="$LADA_E2E_MODELS" \
  -e LADA_INSTALL_E2E_PREVIOUS="${LADA_INSTALL_E2E_PREVIOUS:-}" \
  -e LADA_INSTALL_E2E_SKIP_PREVIOUS="${LADA_INSTALL_E2E_SKIP_PREVIOUS:-0}" \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e ANTHROPIC_API_TOKEN="$ANTHROPIC_API_TOKEN" \
  "$IMAGE_NAME"

