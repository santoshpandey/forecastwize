#!/bin/sh
set -eu
mkdir -p /app/data/api
if [ "$(id -u)" = "0" ]; then
  chown -R appuser:appuser /app/data/api
  exec gosu appuser "$@"
fi
exec "$@"
