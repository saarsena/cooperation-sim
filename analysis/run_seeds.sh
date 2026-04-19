#!/usr/bin/env bash
# Run a scenario across N seeds, each writing to output/<name>__seed<K>.
# Usage:  analysis/run_seeds.sh scenarios/markers_only.conf 16
# Requires the release binary at ./build-rel/relationships.
set -euo pipefail

if [ $# -lt 2 ]; then
    echo "usage: $0 scenario.conf N_SEEDS [OUT_PREFIX]" >&2
    exit 2
fi

SCENARIO="$1"
N="$2"
PREFIX="${3:-}"

[ -f "$SCENARIO" ] || { echo "no such scenario: $SCENARIO" >&2; exit 1; }
[ -x "./build-rel/relationships" ] \
    || { echo "build-rel/relationships missing — run cmake --build build-rel -j" >&2; exit 1; }

BASENAME="$(basename "$SCENARIO" .conf)"
BASE_OUT="$(grep -E '^output_dir' "$SCENARIO" | awk -F= '{gsub(/ /,"",$2); print $2}')"
# Derive a prefix from config name if none given; strip the legacy output_dir.
PREFIX="${PREFIX:-$BASENAME}"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

for i in $(seq 0 $((N-1))); do
    SEED=$((1000 + i))
    OUT="output/${PREFIX}__seed${SEED}"
    rm -rf "$OUT"
    CONF="${TMPDIR}/cfg_${SEED}.conf"
    sed -e "s|^seed .*|seed = ${SEED}|" \
        -e "s|^output_dir .*|output_dir = ${OUT}|" \
        "$SCENARIO" > "$CONF"
    ./build-rel/relationships "$CONF" > "${TMPDIR}/log_${SEED}" 2>&1 &
done
wait

for i in $(seq 0 $((N-1))); do
    SEED=$((1000 + i))
    OUT="output/${PREFIX}__seed${SEED}"
    if [ ! -f "${OUT}/metrics.csv" ]; then
        echo "FAILED seed=${SEED}" >&2
        cat "${TMPDIR}/log_${SEED}" >&2
        exit 1
    fi
done

echo "ok: ${N} seeds under output/${PREFIX}__seed*"
