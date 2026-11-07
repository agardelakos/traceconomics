#!/usr/bin/env bash
# Append run records to the branch `test-history` and push, retrying when another run pushed first.
#
#   GH_TOKEN=… .github/scripts/test_history_push.sh "<commit message>" RECORD.json [--catalog CATALOG.json] [RECORD.json …]
#
# The branch holds only data (tests/catalog/history.py, "append"): one file per run, the newest
# catalog and the obsolete IDs. It only ever moves forward: a push that loses a race fetches the
# new tip, appends again on top of it and retries, never forces. The first run creates the branch
# as an orphan, so it shares no history with the code.
set -euo pipefail

message=$1; shift
records=(); catalog=()
while (($#)); do
  case $1 in
    --catalog) catalog=(--catalog "$(realpath "$2")"); shift 2 ;;
    *) records+=("$(realpath "$1")"); shift ;;
  esac
done
((${#records[@]})) || { echo "no record to append"; exit 0; }

history_py=$(realpath tests/catalog/history.py)
url=${TEST_HISTORY_REMOTE:-"https://github.com/${GITHUB_REPOSITORY}.git"}   # the override is for testing the script
auth=$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 -w0)
git_() { git -c http.extraheader="AUTHORIZATION: basic ${auth}" "$@"; }
store=$(mktemp -d)

for attempt in 1 2 3 4 5; do
  rm -rf "$store" && mkdir -p "$store" && cd "$store"
  git init -q -b test-history
  git config user.name "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  if git_ fetch -q --depth 1 "$url" test-history 2>/dev/null; then
    git reset -q --hard FETCH_HEAD
  fi
  for r in "${records[@]}"; do
    python -I "$history_py" append --store . "$r" "${catalog[@]}"
  done
  git add -A
  if git diff --cached --quiet; then echo "nothing new to record"; exit 0; fi
  git commit -q -m "$message"
  if git_ push -q "$url" HEAD:test-history; then
    echo "recorded on test-history (attempt $attempt)"
    exit 0
  fi
  echo "push refused (another run was first?); trying again"
  sleep $((attempt * 5))
  cd - >/dev/null
done
echo "could not push to test-history after 5 attempts"
exit 1
