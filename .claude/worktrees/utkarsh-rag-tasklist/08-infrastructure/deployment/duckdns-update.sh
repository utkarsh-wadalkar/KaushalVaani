#!/usr/bin/env bash
set -euo pipefail

: "${DUCKDNS_DOMAIN:?Set DUCKDNS_DOMAIN without the .duckdns.org suffix}"
: "${DUCKDNS_TOKEN:?Set DUCKDNS_TOKEN}"
: "${DROPLET_RESERVED_IP:?Set DROPLET_RESERVED_IP}"

curl --fail --silent --show-error "https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip=${DROPLET_RESERVED_IP}"
printf '\nDuckDNS updated for %s\n' "$DUCKDNS_DOMAIN"
