#!/usr/bin/env sh
# Generate a self-signed certificate for local HTTPS development.
# Production deployments should replace nginx/certs with a real certificate
# (e.g. Let's Encrypt fullchain.pem + privkey.pem).
set -eu

DOMAIN="${1:-localhost}"
CERT_DIR="$(cd "$(dirname "$0")/.." && pwd)/nginx/certs"

mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -keyout "$CERT_DIR/privkey.pem" \
  -out "$CERT_DIR/fullchain.pem" \
  -subj "/CN=$DOMAIN" \
  -addext "subjectAltName=DNS:$DOMAIN,DNS:localhost,IP:127.0.0.1"

chmod 600 "$CERT_DIR/privkey.pem"
echo "Wrote $CERT_DIR/fullchain.pem and $CERT_DIR/privkey.pem for CN=$DOMAIN"
