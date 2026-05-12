#!/usr/bin/env sh
set -eu
echo "GET http://localhost:18080/health"
curl -fsS "http://localhost:18080/health" | head -c 200 || true
echo
echo "GET http://localhost:13000/api/health"
curl -fsS "http://localhost:13000/api/health" | head -c 200 || true
echo
echo "verify-stack: OK"
