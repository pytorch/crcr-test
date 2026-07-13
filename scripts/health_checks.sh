#!/usr/bin/env bash
# Emit --check name=outcome pairs (one per line) for write_health_report.py.
# Usage: mapfile -t ARGS < <(scripts/health_checks.sh SPEC)
#        python3 tests/write_health_report.py "${ARGS[@]}" ...

set -euo pipefail

spec="${1:?spec required (l1-light, l1-full, l1-push-deleted, l2-full)}"

emit_check() {
  local name="$1"
  local var="$2"
  echo --check
  echo "${name}=${!var:-skipped}"
}

case "$spec" in
  l1-light)
    emit_check validate_payload VALIDATE_PAYLOAD
    emit_check checkout_pytorch CHECKOUT_PYTORCH
    emit_check verify_checkout VERIFY_CHECKOUT
    emit_check delivery_id DELIVERY_ID
    ;;
  l1-full)
    emit_check validate_payload VALIDATE_PAYLOAD
    emit_check in_progress_callback IN_PROGRESS_CALLBACK
    emit_check checkout_pytorch CHECKOUT_PYTORCH
    emit_check verify_checkout VERIFY_CHECKOUT
    emit_check delivery_id DELIVERY_ID
    ;;
  l1-push-deleted)
    emit_check push_deleted_semantics PUSH_DELETED_SEMANTICS
    emit_check validate_payload VALIDATE_PAYLOAD
    emit_check delivery_id DELIVERY_ID
    ;;
  l2-full)
    emit_check validate_payload VALIDATE_PAYLOAD
    emit_check in_progress_callback IN_PROGRESS_CALLBACK
    emit_check checkout_pytorch CHECKOUT_PYTORCH
    emit_check verify_checkout VERIFY_CHECKOUT
    emit_check smoke_checks SMOKE_CHECKS
    ;;
  *)
    echo "unknown health check spec: $spec" >&2
    exit 2
    ;;
esac

if [ "${INCLUDE_COMPLETED_CALLBACK:-}" = "1" ]; then
  emit_check completed_callback COMPLETED_CALLBACK
fi
