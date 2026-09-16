#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/opt/echoquery}"
ENV_FILE="${ENV_FILE:-/etc/echoquery/api.env}"
API_HOSTNAME="${API_HOSTNAME:?Set API_HOSTNAME, for example echoquery-api.duckdns.org}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:?Set LETSENCRYPT_EMAIL before certificate issuance}"

[[ -d "$ROOT_DIR" ]] || { echo "Release directory does not exist: $ROOT_DIR" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Missing production env file: $ENV_FILE" >&2; exit 1; }
[[ "$(stat -c '%a' "$ENV_FILE")" == "600" ]] || { echo "$ENV_FILE must have mode 600" >&2; exit 1; }
grep -Eq '^APP_ENV=production$' "$ENV_FILE" || { echo "API env must set APP_ENV=production" >&2; exit 1; }
grep -Eq '^PUBLIC_API_ORIGIN=https://' "$ENV_FILE" || { echo "PUBLIC_API_ORIGIN must use HTTPS" >&2; exit 1; }
grep -Eq '^PUBLIC_WS_ORIGIN=wss://' "$ENV_FILE" || { echo "PUBLIC_WS_ORIGIN must use WSS" >&2; exit 1; }
if grep -Eq 'REPLACE_|VERIFY_' "$ENV_FILE"; then
  echo "Production env contains unresolved placeholders" >&2
  exit 1
fi

install -d -m 755 /etc/nginx/sites-available /etc/nginx/sites-enabled /var/www/certbot
rm -f /etc/nginx/sites-enabled/default

if [[ ! -f "/etc/letsencrypt/live/${API_HOSTNAME}/fullchain.pem" ]]; then
  cat > /etc/nginx/sites-available/echoquery-api.conf <<EOF
server {
  listen 80;
  server_name ${API_HOSTNAME};
  location /.well-known/acme-challenge/ { root /var/www/certbot; }
  location / { return 404; }
}
EOF
  ln -sfn /etc/nginx/sites-available/echoquery-api.conf /etc/nginx/sites-enabled/echoquery-api.conf
  nginx -t
  systemctl reload nginx
  certbot certonly --webroot -w /var/www/certbot -d "$API_HOSTNAME" --email "$LETSENCRYPT_EMAIL" --agree-tos --no-eff-email
fi

sed "s/__API_HOSTNAME__/${API_HOSTNAME}/g" "$ROOT_DIR/08-infrastructure/nginx/nginx.conf" > /etc/nginx/sites-available/echoquery-api.conf
ln -sfn /etc/nginx/sites-available/echoquery-api.conf /etc/nginx/sites-enabled/echoquery-api.conf
nginx -t
docker compose -f "$ROOT_DIR/08-infrastructure/compose/docker-compose.prod.yml" up -d --build
systemctl reload nginx
curl --fail --silent --show-error "https://${API_HOSTNAME}/health" >/dev/null
echo "EchoQuery deployed at https://${API_HOSTNAME}"
