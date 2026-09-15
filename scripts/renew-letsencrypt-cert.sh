#!/usr/bin/env sh
# Renew the Let's Encrypt certificate and reload nginx if it changed.
# Certbot is a no-op unless the certificate is within 30 days of expiry, so
# this is safe to run often. Schedule it twice daily, e.g. in root's crontab:
#
#   17 3,15 * * * /root/projects/tempo_service/scripts/renew-letsencrypt-cert.sh >> /var/log/certbot-renew.log 2>&1
set -eu

DOMAIN="${1:-}"

if [ -z "$DOMAIN" ]; then
    echo "usage: $0 <domain>" >&2
    exit 1
fi

cd "$(dirname "$0")/.."

docker compose --profile certs run --rm certbot renew --webroot --webroot-path /var/www/certbot

# Copy unconditionally: cheap, and keeps nginx in sync after any renewal.
docker compose --profile certs run --rm --entrypoint sh certbot -ec "
    cp -L /etc/letsencrypt/live/$DOMAIN/fullchain.pem /etc/nginx/certs/fullchain.pem
    cp -L /etc/letsencrypt/live/$DOMAIN/privkey.pem   /etc/nginx/certs/privkey.pem
    chmod 644 /etc/nginx/certs/fullchain.pem
    chmod 600 /etc/nginx/certs/privkey.pem
"

docker compose exec nginx nginx -s reload
echo "Renewal check complete for $DOMAIN."
