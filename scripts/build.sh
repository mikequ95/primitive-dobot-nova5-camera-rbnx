#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
: "${NOVA5_SUPPORT_SOURCE:?Set NOVA5_SUPPORT_SOURCE to a nova5-support checkout or a pinned pip VCS URL}"
: "${NOVA5_HARDWARE_SOURCE:?Set NOVA5_HARDWARE_SOURCE to a nova5-hardware checkout or a pinned pip VCS URL}"
API_SOURCE="$(rbnx path robonix-api)"
"${NOVA5_PYTHON:-python3.12}" -m venv "$PKG/rbnx-build/venv"
PYTHON="$PKG/rbnx-build/venv/bin/python"
"$PYTHON" -m pip install "$API_SOURCE[codegen]" "$NOVA5_SUPPORT_SOURCE" "$NOVA5_HARDWARE_SOURCE" "$PKG"
"$PYTHON" -m nova5_hardware.codegen "$PKG" --mcp
