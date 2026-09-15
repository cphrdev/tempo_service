#!/usr/bin/env sh
# Obtain a real (browser-trusted) Let's Encrypt certificate and install it where
# nginx reads it. Replaces the self-signed development certificate.
#
#   ./scripts/issue-letsencrypt-cert.sh api.example.com you@example.com
#
# Requirements:
#   - The domain's DNS A/AAAA record already points at this server.
#   - Port 80 is reachable from the internet (Let's Encrypt validates over HTTP).
#   - The stack is already running, so nginx can serve the ACME challenge:
#       docker compose up -d
#     nginx needs *some* certificate to start, so run
#     scripts/generate-self-signed-cert.sh first on a fresh server.
#
# Running this accepts the Let's Encrypt Terms of Service (--agree-tos).
set -eu

DOMAIN="${1:-}"
EMAIL="${2:-}"

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "usage: $0 <domain> <email>" >&2
    echo "example: $0 api.example.com you@example.com" >&2
    exit 1
fi

cd "$(dirname "$0")/.."

echo "Requesting a certificate for $DOMAIN ..."
docker compose --profile certs run --rm certbot \
    certonly \
    --webroot --webroot-path /var/www/certbot \
    --domain "$DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --keep-until-expiring

echo "Installing the certificate for nginx ..."
docker compose --profile certs run --rm --entrypoint sh certbot -ec "
    cp -L /etc/letsencrypt/live/$DOMAIN/fullchain.pem /etc/nginx/certs/fullchain.pem
    cp -L /etc/letsencrypt/live/$DOMAIN/privkey.pem   /etc/nginx/certs/privkey.pem
    chmod 644 /etc/nginx/certs/fullchain.pem
    chmod 600 /etc/nginx/certs/privkey.pem
"

echo "Reloading nginx ..."
docker compose exec nginx nginx -s reload

echo
echo "Done. https://$DOMAIN should now load without a browser warning."
echo "Certificates expire in 90 days; schedule scripts/renew-letsencrypt-cert.sh."
