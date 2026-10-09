#!/usr/bin/env bash
# Deploy ban SACH (chi file da commit) len Vercel production.
# Ly do: thu muc lam viec co the chua file tam bi khoa quyen / thay doi chua commit.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${DEPLOY_DIR:-$ROOT/../deploy/invest-system}"
mkdir -p "$OUT"
git -C "$ROOT" archive HEAD | tar -x -C "$OUT"
cd "$OUT" && vercel deploy --prod --yes
