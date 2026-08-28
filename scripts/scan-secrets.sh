#!/usr/bin/env bash
#
# Fail the build if anything credential-shaped is tracked in git.
#
# Deliberately simple and readable rather than clever: a secret scanner nobody
# understands is a secret scanner nobody maintains, and one that cries wolf gets
# switched off within a sprint. This is a last line of defence — the actual
# control is that no code path in this repository accepts a connection string,
# and every Azure call authenticates with a managed identity.
#
# Exit codes: 0 clean, 1 findings, 2 usage/environment error.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Prefer git, because "tracked" is the property that matters — an ignored file
# cannot leak through a push. Before `git init`, fall back to the working tree
# so the scan still runs. A scanner that silently examines zero files is worse
# than no scanner, so the mode is always printed.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  MODE="tracked files"
  mapfile -t CANDIDATES < <(git ls-files)
else
  MODE="working tree (not a git repository yet)"
  mapfile -t CANDIDATES < <(
    find . \
      \( -name .git -o -name .venv -o -name node_modules -o -name __pycache__ \
         -o -name .mypy_cache -o -name .ruff_cache -o -name .pytest_cache \
         -o -name dist -o -name build -o -name .reap-state \) -prune -o \
      -type f -print | sed 's|^\./||'
  )
fi

if [[ "${#CANDIDATES[@]}" -eq 0 ]]; then
  echo "scan-secrets: found no files to scan; refusing to report a pass" >&2
  exit 2
fi

# Files that are *supposed* to contain credential-shaped strings: the redaction
# patterns themselves, the tests that prove redaction works, and the example
# environment file. Every entry here is a deliberate, reviewed exception.
ALLOWLIST=(
  ".env.example"                              # placeholders only, no values
  "packages/security/redaction.py"            # the detection patterns themselves
  "tests/security/test_telemetry_redaction.py" # synthetic JWT proving redaction
  "tests/unit/test_audit_receipt.py"          # fake api_key proving audit redaction
  "scripts/scan-secrets.sh"                   # this file's own rule table
  "uv.lock"                                   # dependency hashes, not credentials
)

# Each rule is "name|extended-regex". Anchored on assignment syntax wherever
# possible, because a bare high-entropy string matches half of any lockfile.
RULES=(
  "jwt|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
  "azure_storage_key|(AccountKey|SharedAccessKey)=[A-Za-z0-9+/]{20,}"
  "sas_token|(sig|sv)=[A-Za-z0-9%+/]{20,}&"
  "private_key|-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----"
  "assigned_secret|(client_secret|clientSecret|api_key|apiKey|password|passwd|pwd)[\"' ]*[:=][\"' ]*[A-Za-z0-9+/_-]{12,}"
  "connection_string|(Endpoint|DefaultEndpointsProtocol)=[^;]+;.*(Key|Secret)=[A-Za-z0-9+/]{20,}"
  "aws_access_key|AKIA[0-9A-Z]{16}"
  "github_token|gh[pousr]_[A-Za-z0-9]{20,}"
  "openai_key|sk-[A-Za-z0-9]{32,}"
)

is_allowlisted() {
  local candidate="$1"
  for allowed in "${ALLOWLIST[@]}"; do
    [[ "${candidate}" == "${allowed}" ]] && return 0
  done
  return 1
}

mapfile -t TRACKED < <(printf '%s\n' "${CANDIDATES[@]}")

findings=0
scanned=0

for file in "${TRACKED[@]}"; do
  [[ -f "${file}" ]] || continue
  is_allowlisted "${file}" && continue
  # Binary files cannot be reviewed by eye, so they are skipped here and caught
  # by the "no model artifacts in git" rule in .gitignore instead.
  if ! grep -Iq . "${file}" 2>/dev/null; then
    continue
  fi
  scanned=$((scanned + 1))

  for rule in "${RULES[@]}"; do
    name="${rule%%|*}"
    pattern="${rule#*|}"
    if matches=$(grep -nEI "${pattern}" "${file}" 2>/dev/null); then
      while IFS= read -r match; do
        line="${match%%:*}"
        echo "FINDING [${name}] ${file}:${line}"
        findings=$((findings + 1))
      done <<<"${matches}"
    fi
  done
done

# A tracked .env is a finding regardless of its contents.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1 &&
  git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo "FINDING [tracked_dotenv] .env is tracked in git; only .env.example belongs here"
  findings=$((findings + 1))
fi

echo
echo "scanned ${scanned} text files from ${MODE}, ${#ALLOWLIST[@]} allowlisted"

if [[ "${findings}" -gt 0 ]]; then
  echo "secret scan FAILED with ${findings} finding(s)" >&2
  echo "if a finding is a deliberate test fixture, add the file to ALLOWLIST with a reason" >&2
  exit 1
fi

echo "secret scan passed: no credential-shaped strings tracked"
