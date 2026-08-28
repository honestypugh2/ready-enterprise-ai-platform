#!/usr/bin/env bash
#
# Build and lint every Bicep template under infra/.
#
# Compilation is the check that matters: `az bicep build` resolves modules,
# validates the resource schema against the current API versions, and fails on
# anything the linter is configured to treat as an error. Running it locally is
# what stops a template reaching a subscription broken.
#
# Exit codes: 0 clean, 1 findings, 2 missing prerequisites.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

INFRA_DIR="${INFRA_DIR:-infra}"

if [[ ! -d "${INFRA_DIR}" ]]; then
  echo "validate-bicep: ${INFRA_DIR}/ does not exist yet." >&2
  echo "Nothing was validated. See IMPLEMENTATION_STATUS.md for what is built." >&2
  exit 2
fi

mapfile -t TEMPLATES < <(find "${INFRA_DIR}" -type f -name '*.bicep' | sort)
mapfile -t PARAM_FILES < <(find "${INFRA_DIR}" -type f -name '*.bicepparam' | sort)

if [[ "${#TEMPLATES[@]}" -eq 0 ]]; then
  echo "validate-bicep: no .bicep files found under ${INFRA_DIR}/; refusing to report a pass" >&2
  exit 2
fi

if ! command -v az >/dev/null 2>&1; then
  echo "validate-bicep: the Azure CLI is required (https://aka.ms/azure-cli)" >&2
  exit 2
fi

# The CLI installs and manages the Bicep binary itself, so no separate toolchain.
if ! az bicep version >/dev/null 2>&1; then
  echo "validate-bicep: installing the Bicep CLI"
  az bicep install >/dev/null
fi

echo "bicep $(az bicep version --only-show-errors 2>/dev/null | head -1)"
echo "validating ${#TEMPLATES[@]} template(s) and ${#PARAM_FILES[@]} parameter file(s)"
echo

failures=0
OUT_DIR="$(mktemp -d)"
trap 'rm -rf "${OUT_DIR}"' EXIT

for template in "${TEMPLATES[@]}"; do
  printf '  %-58s' "${template}"
  if output=$(az bicep build --file "${template}" --outdir "${OUT_DIR}" 2>&1); then
    # Warnings are printed but do not fail the build; errors already exited.
    if [[ -n "${output}" ]]; then
      echo "warn"
      echo "${output}" | sed 's/^/      /'
    else
      echo "ok"
    fi
  else
    echo "FAILED"
    echo "${output}" | sed 's/^/      /'
    failures=$((failures + 1))
  fi
done

for param in "${PARAM_FILES[@]}"; do
  printf '  %-58s' "${param}"
  if output=$(az bicep build-params --file "${param}" --outfile /dev/null 2>&1); then
    echo "ok"
  else
    echo "FAILED"
    echo "${output}" | sed 's/^/      /'
    failures=$((failures + 1))
  fi
done

echo
if [[ "${failures}" -gt 0 ]]; then
  echo "bicep validation FAILED for ${failures} file(s)" >&2
  exit 1
fi

echo "bicep validation passed"
