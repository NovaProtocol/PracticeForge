#!/bin/sh

echo "Pushing..."
git push origin main --force 2>&1 || true

echo ""
echo "Notifying Dockhand..."
RESP=$(curl -s -w "\n%{http_code}" -X POST http://localhost:3000/api/git/stacks/7/webhook \
  -H "Content-Type: application/json" \
  -d "{\"ref\": \"refs/heads/main\", \"secret\": \"$SECRET\"}")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
echo "HTTP $HTTP_CODE"
echo "$BODY"
