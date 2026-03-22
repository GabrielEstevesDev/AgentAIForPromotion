#!/bin/sh
# Seed the persistent volume with dev.db on first run
if [ ! -f /app/data/dev.db ] && [ -f /app/dev.db ]; then
  cp /app/dev.db /app/data/dev.db
fi

exec "$@"
