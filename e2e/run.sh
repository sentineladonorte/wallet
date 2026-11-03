#!/bin/sh
# Roda os testes de navegador em ambiente isolado. Argumentos vão para o pytest:
#   e2e/run.sh -k proventos
set -eu
cd "$(dirname "$0")"

if docker compose version >/dev/null 2>&1; then
  compose="docker compose"
else
  compose="docker-compose"
  # O docker-compose antigo pede uma versão de API que daemons novos recusam.
  if [ -z "${DOCKER_API_VERSION:-}" ]; then
    DOCKER_API_VERSION="$(docker version --format '{{.Server.MinAPIVersion}}')"
    export DOCKER_API_VERSION
  fi
fi

mkdir -p .certs artifacts
if [ ! -f .certs/localhost.crt ]; then
  openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout .certs/localhost.key -out .certs/localhost.crt -subj "/CN=localhost" 2>/dev/null
  chmod 644 .certs/localhost.key
fi

# Mantém argumentos com espaço, como -k "a or b", ao passarem pelo shell do contêiner.
PYTEST_ARGS=""
for arg in "$@"; do
  PYTEST_ARGS="$PYTEST_ARGS '$(printf '%s' "$arg" | sed "s/'/'\\\\''/g")'"
done
export PYTEST_ARGS

status=0
$compose up --build --attach runner --abort-on-container-exit --exit-code-from runner || status=$?
$compose down --remove-orphans >/dev/null 2>&1 || true
exit "$status"
