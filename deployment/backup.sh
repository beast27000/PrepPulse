#!/usr/bin/env bash
set -euo pipefail
cd /opt/preppulse
compose=(docker compose -f deployment/compose.yaml)
umask 077
install -d -m 750 -g 10001 /data/backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive=/data/backups/preppulse-$stamp.tar.gz
# Stop writers briefly for a consistent Mongo + source-file + SQLite snapshot.
"${compose[@]}" stop api worker care-worker
trap '"${compose[@]}" up -d api worker care-worker' EXIT
"${compose[@]}" exec -T mongo mongodump --archive --gzip --db preppulse > /data/private/mongodb.archive.gz
tar -czf "$archive" -C /data private
"${compose[@]}" up -d api worker care-worker
trap - EXIT
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -in "$archive" -out "$archive.enc" -pass file:/etc/preppulse/backup.key
# Retain the encrypted file; remove only this just-created plaintext archive.
rm -- "$archive"
chown 10001:10001 "$archive.enc"
chmod 600 "$archive.enc"
"${compose[@]}" run --rm -T -v /data/backups:/backups:ro api python scripts/upload_pilot_backup.py "/backups/$(basename "$archive.enc")"
