#!/bin/bash
# Run once on DB first initialization to allow trust auth from Docker network.
# This enables the backend to auto-reset the DB password if it drifts.
set -e
PG_HBA="$PGDATA/pg_hba.conf"
# Allow trust from the entire Docker bridge network
echo "" >> "$PG_HBA"
echo "# Allow trust from Docker network for auto-repair" >> "$PG_HBA"
echo "host    all             all             172.0.0.0/8            trust" >> "$PG_HBA"
echo "host    all             all             10.0.0.0/8             trust" >> "$PG_HBA"
echo "host    all             all             192.168.0.0/16         trust" >> "$PG_HBA"
psql -U postgres -c "SELECT pg_reload_conf();"
echo "pg_hba.conf updated with Docker network trust rules"
