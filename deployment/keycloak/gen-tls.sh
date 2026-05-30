#!/usr/bin/env bash
# gen-tls.sh — Generate self-signed TLS cert for Keycloak.
# In production replace with a CA-signed certificate.
#
#   Usage:  bash gen-tls.sh [IP_OR_HOSTNAME]

set -euo pipefail

HOST="${1:-10.10.10.150}"
mkdir -p tls

openssl req -x509 -nodes -newkey rsa:4096 -days 825 \
  -keyout tls/tls.key \
  -out    tls/tls.crt \
  -subj   "/CN=${HOST}/O=AIP Qx/C=FR" \
  -addext "subjectAltName=IP:${HOST},DNS:${HOST}" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"

chmod 600 tls/tls.key
echo "TLS cert/key written to tls/tls.crt and tls/tls.key"
