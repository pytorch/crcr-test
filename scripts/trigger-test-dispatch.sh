#!/usr/bin/env bash
# Send a test repository_dispatch to exercise L1/L2 workflows.
# Requires: gh CLI, workflows merged to the target repo default branch (main).
#
# Usage:
#   ./scripts/trigger-test-dispatch.sh              # L1+L2 (pull_request/opened)
#   ./scripts/trigger-test-dispatch.sh push         # L1 only (push event)
#
# Target repo: current gh repo, or pytorch/crcr-test. Override with CRCR_TEST_REPO.
set -euo pipefail
cd "$(dirname "$0")/.."

REPO="${CRCR_TEST_REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo pytorch/crcr-test)}"
MODE="${1:-pr}"

echo "Fetching latest pytorch/pytorch main SHA..."
PYTORCH_SHA="$(git ls-remote https://github.com/pytorch/pytorch.git HEAD | awk '{print $1}')"
if [[ -z "${PYTORCH_SHA}" ]]; then
  echo "error: could not resolve pytorch main SHA" >&2
  exit 1
fi
echo "Using SHA: ${PYTORCH_SHA}"

DELIVERY_ID="local-test-$(date -u +%Y%m%dT%H%M%SZ)-$$"

if [[ "${MODE}" == "push" ]]; then
  EVENT_TYPE="push"
  PAYLOAD=$(jq -n \
    --arg sha "${PYTORCH_SHA}" \
    --arg did "${DELIVERY_ID}" \
    '{
      event_type: "push",
      client_payload: {
        event_type: "push",
        delivery_id: $did,
        payload: {
          ref: "refs/heads/main",
          after: $sha,
          deleted: false,
          base_ref: "refs/heads/main",
          repository: { full_name: "pytorch/pytorch" }
        }
      }
    }')
else
  EVENT_TYPE="pull_request"
  PAYLOAD=$(jq -n \
    --arg sha "${PYTORCH_SHA}" \
    --arg did "${DELIVERY_ID}" \
    '{
      event_type: "pull_request",
      client_payload: {
        event_type: "pull_request",
        delivery_id: $did,
        payload: {
          action: "opened",
          repository: { full_name: "pytorch/pytorch" },
          pull_request: {
            number: 999999,
            title: "CRCR local dispatch test",
            head: {
              sha: $sha,
              repo: { full_name: "pytorch/pytorch" }
            }
          }
        }
      }
    }')
fi

echo "Dispatching ${EVENT_TYPE} to ${REPO} (delivery_id=${DELIVERY_ID})..."
echo "${PAYLOAD}" | gh api --method POST "repos/${REPO}/dispatches" --input -

echo ""
echo "Done. Check workflow runs at:"
echo "  https://github.com/${REPO}/actions"
echo ""
echo "Note: callbacks require the target repo on the CRCR allowlist and a relay dispatch record."
echo "Synthetic delivery_id dispatches exercise L1/L2 workflow steps; callbacks may fail locally."
