#!/usr/bin/env bash
set -euo pipefail

API_URL="${1:-http://localhost:8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/apps/web/build"

mkdir -p "$BUILD"
cp "$ROOT/apps/web/index.html" "$BUILD/index.html"
cat > "$BUILD/config.js" <<EOF
window.__TRAVELAI__ = {
  apiBase: "${API_URL%/}/api/v1",
};
EOF

echo "Frontend built → $BUILD"
echo "API base: ${API_URL%/}/api/v1"
