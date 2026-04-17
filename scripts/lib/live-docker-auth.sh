#!/usr/bin/env bash

LADA_DOCKER_LIVE_AUTH_ALL=(.gemini .minimax)
LADA_DOCKER_LIVE_AUTH_FILES_ALL=(
  .codex/auth.json
  .codex/config.toml
  .lada.json
  .lada/.credentials.json
  .lada/settings.json
  .lada/settings.local.json
  .gemini/settings.json
)

lada_live_trim() {
  local value="${1:-}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

lada_live_normalize_auth_dir() {
  local value
  value="$(lada_live_trim "${1:-}")"
  [[ -n "$value" ]] || return 1
  value="${value#.}"
  printf '.%s' "$value"
}

lada_live_should_include_auth_dir_for_provider() {
  local provider
  provider="$(lada_live_trim "${1:-}")"
  case "$provider" in
    gemini | gemini-cli | google-gemini-cli)
      printf '%s\n' ".gemini"
      ;;
    minimax | minimax-portal)
      printf '%s\n' ".minimax"
      ;;
  esac
}

lada_live_should_include_auth_file_for_provider() {
  local provider
  provider="$(lada_live_trim "${1:-}")"
  case "$provider" in
    codex-cli | openai-codex)
      printf '%s\n' ".codex/auth.json"
      printf '%s\n' ".codex/config.toml"
      ;;
    anthropic | lada-cli)
      printf '%s\n' ".lada.json"
      printf '%s\n' ".lada/.credentials.json"
      printf '%s\n' ".lada/settings.json"
      printf '%s\n' ".lada/settings.local.json"
      ;;
  esac
}

lada_live_collect_auth_dirs_from_csv() {
  local raw="${1:-}"
  local token normalized
  [[ -n "$(lada_live_trim "$raw")" ]] || return 0
  IFS=',' read -r -a tokens <<<"$raw"
  for token in "${tokens[@]}"; do
    while IFS= read -r normalized; do
      printf '%s\n' "$normalized"
    done < <(lada_live_should_include_auth_dir_for_provider "$token")
  done | awk 'NF && !seen[$0]++'
}

lada_live_collect_auth_dirs_from_override() {
  local raw token normalized
  raw="$(lada_live_trim "${LADA_DOCKER_AUTH_DIRS:-}")"
  [[ -n "$raw" ]] || return 1
  case "$raw" in
    all)
      printf '%s\n' "${LADA_DOCKER_LIVE_AUTH_ALL[@]}"
      return 0
      ;;
    none)
      return 0
      ;;
  esac
  IFS=',' read -r -a tokens <<<"$raw"
  for token in "${tokens[@]}"; do
    normalized="$(lada_live_normalize_auth_dir "$token")" || continue
    printf '%s\n' "$normalized"
  done | awk '!seen[$0]++'
  return 0
}

lada_live_collect_auth_dirs() {
  if lada_live_collect_auth_dirs_from_override; then
    return 0
  fi
  printf '%s\n' "${LADA_DOCKER_LIVE_AUTH_ALL[@]}"
}

lada_live_collect_auth_files_from_csv() {
  local raw="${1:-}"
  local token normalized
  [[ -n "$(lada_live_trim "$raw")" ]] || return 0
  IFS=',' read -r -a tokens <<<"$raw"
  for token in "${tokens[@]}"; do
    while IFS= read -r normalized; do
      printf '%s\n' "$normalized"
    done < <(lada_live_should_include_auth_file_for_provider "$token")
  done | awk 'NF && !seen[$0]++'
}

lada_live_collect_auth_files_from_override() {
  local raw
  raw="$(lada_live_trim "${LADA_DOCKER_AUTH_DIRS:-}")"
  [[ -n "$raw" ]] || return 1
  case "$raw" in
    all)
      printf '%s\n' "${LADA_DOCKER_LIVE_AUTH_FILES_ALL[@]}"
      return 0
      ;;
    none)
      return 0
      ;;
  esac
  return 0
}

lada_live_collect_auth_files() {
  if lada_live_collect_auth_files_from_override; then
    return 0
  fi
  printf '%s\n' "${LADA_DOCKER_LIVE_AUTH_FILES_ALL[@]}"
}

lada_live_join_csv() {
  local first=1 value
  for value in "$@"; do
    [[ -n "$value" ]] || continue
    if (( first )); then
      printf '%s' "$value"
      first=0
    else
      printf ',%s' "$value"
    fi
  done
}

