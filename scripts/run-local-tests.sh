#!/usr/bin/env bash
# Run offline CRCR validator tests (no relay required).
# Live L1/L2 probe workflows: crcr-dispatch-receiver.yml, crcr-l2-ci.yml
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Unit tests ==="
python3 -m unittest discover -s tests -p 'test_*.py' -v

echo ""
echo "=== Fixture validation ==="
for f in tests/fixtures/*.json; do
  echo "Validating $f"
  python3 tests/validate_dispatch_payload.py < "$f"
done

echo ""
echo "All local tests passed."
