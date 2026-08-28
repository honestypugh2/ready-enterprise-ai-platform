#!/usr/bin/env bash
#
# Deploy, or preview, the platform infrastructure.
#
# `--what-if` is the default posture in every review: a deployment you cannot
# preview is a deployment you cannot approve. Nothing here creates a resource
# without an explicit confirmation, and no secret is ever passed on the command
# line — every Azure call authenticates with the operator's own signed-in
# identity, and the deployed workload authenticates with a managed identity.
#
# Usage:
#   scripts/deploy.sh --what-if [--env dev]        preview only (default)
#   scripts/deploy.sh --apply --env dev            deploy after confirmation
#   scripts/deploy.sh --validate --env dev         template validation only
#
# Exit codes: 0 ok, 1 deployment/validation failure, 2 usage or prerequisites.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

INFRA_DIR="${INFRA_DIR:-infra}"
ENVIRONMENT="dev"
MODE="what-if"
LOCATION="${AZURE_LOCATION:-}"

usage() {
  sed -n '3,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --what-if) MODE="what-if" ;;
    --apply) MODE="apply" ;;
    --validate) MODE="validate" ;;
    --env)
      ENVIRONMENT="${2:-}"
      shift
      ;;
    --location)
      LOCATION="${2:-}"
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "deploy: unknown argument '$1'" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

case "${ENVIRONMENT}" in
  dev | test | prod) ;;
  *)
    echo "deploy: --env must be one of dev, test, prod (got '${ENVIRONMENT}')" >&2
    exit 2
    ;;
esac

TEMPLATE="${INFRA_DIR}/main.bicep"
PARAMETERS="${INFRA_DIR}/environments/${ENVIRONMENT}/main.bicepparam"

if [[ ! -f "${TEMPLATE}" || ! -f "${PARAMETERS}" ]]; then
  echo "deploy: expected ${TEMPLATE} and ${PARAMETERS}." >&2
  echo "Infrastructure is not present in this working tree." >&2
  echo "See IMPLEMENTATION_STATUS.md for what is built and what is planned." >&2
  exit 2
fi

if ! command -v az >/dev/null 2>&1; then
  echo "deploy: the Azure CLI is required (https://aka.ms/azure-cli)" >&2
  exit 2
fi

if ! az account show >/dev/null 2>&1; then
  echo "deploy: not signed in; run 'az login' first" >&2
  exit 2
fi

SUBSCRIPTION_NAME=$(az account show --query name -o tsv)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

if [[ -z "${LOCATION}" ]]; then
  echo "deploy: set AZURE_LOCATION or pass --location (no default is assumed)" >&2
  exit 2
fi

DEPLOYMENT_NAME="reap-${ENVIRONMENT}-$(date -u +%Y%m%d%H%M%S)"

echo "subscription   ${SUBSCRIPTION_NAME} (${SUBSCRIPTION_ID})"
echo "environment    ${ENVIRONMENT}"
echo "location       ${LOCATION}"
echo "template       ${TEMPLATE}"
echo "parameters     ${PARAMETERS}"
echo "mode           ${MODE}"
echo

run_deployment() {
  az deployment sub "$1" \
    --name "${DEPLOYMENT_NAME}" \
    --location "${LOCATION}" \
    --template-file "${TEMPLATE}" \
    --parameters "${PARAMETERS}" \
    "${@:2}"
}

case "${MODE}" in
  validate)
    run_deployment validate --only-show-errors
    echo "template validated"
    ;;
  what-if)
    # Preview only. This command cannot change anything.
    run_deployment what-if
    echo
    echo "preview only — nothing was changed. Re-run with --apply to deploy."
    ;;
  apply)
    if [[ "${ENVIRONMENT}" == "prod" ]]; then
      echo "Refusing to deploy to prod from a workstation." >&2
      echo "Production deployments run from the pipeline with workload identity" >&2
      echo "federation and a recorded approval. See .github/workflows/infra.yml." >&2
      exit 2
    fi

    echo "Previewing changes before applying:"
    run_deployment what-if
    echo
    read -r -p "Apply these changes to ${SUBSCRIPTION_NAME}? [y/N] " confirmation
    if [[ "${confirmation}" != "y" && "${confirmation}" != "Y" ]]; then
      echo "aborted; nothing was changed"
      exit 0
    fi
    run_deployment create --only-show-errors
    echo "deployment ${DEPLOYMENT_NAME} complete"
    ;;
esac
