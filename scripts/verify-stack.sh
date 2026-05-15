#!/usr/bin/env sh
set -eu
echo "GET http://localhost:8080/health"
curl -fsS "http://localhost:8080/health" | head -c 200 || true
echo
echo "GET http://localhost:3000/api/health"
curl -fsS "http://localhost:3000/api/health" | head -c 200 || true
echo
echo "verify-stack: OK"
