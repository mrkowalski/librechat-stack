#!/usr/bin/env bash
# One-off: create runtime dirs (owned by you, not root) and link secrets into the submodule.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p secrets data/{images,uploads,logs,skill,mongo,meili_v1.35.1,mitm}
[[ -f secrets/.env ]] || { echo "Put your LibreChat .env at secrets/.env first"; exit 1; }
ln -sfn ../secrets/.env librechat/.env
git -C librechat status --short --ignored .env
