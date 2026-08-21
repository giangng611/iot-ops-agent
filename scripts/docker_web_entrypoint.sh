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

load_dotenv_file /app/.env

rewrite_local_url_env MYSQL_DB_URL
rewrite_local_url_env MONGODB_URI
rewrite_local_url_env MONGODB_ADMIN_URI
rewrite_local_url_env N8N_WEBHOOK_URL
rewrite_local_url_env N8N_V3_WEBHOOK_URL
rewrite_local_url_env DIFY_API_URL

if [ "${APPLY_MYSQL_SCHEMA_ON_START:-true}" = "true" ]; then
  python scripts/apply_mysql_schema.py
fi

exec python app.py
