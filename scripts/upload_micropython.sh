#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-/dev/cu.usbserial-58EF0511901}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FIRMWARE_DIR="${PROJECT_DIR}/firmware/micropython_lilygo_t_sim7000g_panic"
MPREMOTE="/Users/a2.0/Library/Python/3.9/bin/mpremote"

if [[ ! -x "${MPREMOTE}" ]]; then
  echo "mpremote not found at ${MPREMOTE}"
  echo "Install it with: python3 -m pip install --user mpremote"
  exit 1
fi

echo "Uploading VIKELA MicroPython firmware to ${PORT}"
"${MPREMOTE}" connect "${PORT}" fs cp "${FIRMWARE_DIR}/main.py" :main.py
"${MPREMOTE}" connect "${PORT}" reset
echo "Upload complete."
