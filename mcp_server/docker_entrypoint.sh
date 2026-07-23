#!/usr/bin/env sh
set -eu

load_dotenv_file() {
  path="$1"

  if [ ! -f "$path" ]; then
    return 0
  fi

  eval "$(python - "$path" <<'PY'
import os
import re
import shlex
import sys

from dotenv import dotenv_values

path = sys.argv[1]

for key, value in dotenv_values(path).items():
    if value is None or key in os.environ:
        continue

    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        continue

    print(f"export {key}={shlex.quote(value)}")
PY
  )"
}

rewrite_local_url_env() {
  name="$1"
  eval "value=\${$name:-}"

  if [ -z "$value" ]; then
    return 0
  fi

  value=$(printf '%s' "$value" \
    | sed 's#://127\.0\.0\.1:#://host.docker.internal:#g' \
    | sed 's#://localhost:#://host.docker.internal:#g' \
    | sed 's#@127\.0\.0\.1:#@host.docker.internal:#g' \
    | sed 's#@localhost:#@host.docker.internal:#g')

  export "$name=$value"
}

load_dotenv_file /app/mcp_server/.env

rewrite_local_url_env COMPANY_MONGODB_URI
rewrite_local_url_env GRAFANA_URL
rewrite_local_url_env LOKI_URL
rewrite_local_url_env PROMETHEUS_URL

exec python mcp_server/server.py
