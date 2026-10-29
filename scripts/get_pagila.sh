#!/usr/bin/env bash
# Download the Pagila sample database into docker/initdb so docker compose loads it on first start.
# Source: https://github.com/devrimgunduz/pagila (check the repo if these URLs move).
set -euo pipefail
cd "$(dirname "$0")/../docker/initdb"
base="https://raw.githubusercontent.com/devrimgunduz/pagila/master"
curl -fsSL "$base/pagila-schema.sql" -o 01-pagila-schema.sql
curl -fsSL "$base/pagila-data.sql"   -o 02-pagila-data.sql
echo "Pagila downloaded. Run: docker compose up -d   (first start loads it; to reload: docker compose down -v)"
