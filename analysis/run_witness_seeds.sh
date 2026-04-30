#!/usr/bin/env bash
# Run scenarios/witness_v0.conf across N seeds, then turn each run's event
# log into one prose file per qualifying agent under
# output/witness_v0__seed<SEED>/lives/.
#
# Usage:
#   analysis/run_witness_seeds.sh N [SCENARIO]
# Default scenario: scenarios/witness_v0.conf

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: $0 N_SEEDS [scenario.conf]" >&2
    exit 2
fi

N="$1"
SCENARIO="${2:-scenarios/witness_v0.conf}"

[ -f "$SCENARIO" ] || { echo "no such scenario: $SCENARIO" >&2; exit 1; }
[ -x "./build-rel/relationships" ] \
    || { echo "build-rel/relationships missing — run cmake --build build-rel -j" >&2; exit 1; }

BASENAME="$(basename "$SCENARIO" .conf)"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# launch all seeds in parallel
for i in $(seq 0 $((N-1))); do
    SEED=$((1000 + i))
    OUT="output/${BASENAME}__seed${SEED}"
    rm -rf "$OUT"
    CONF="${TMPDIR}/cfg_${SEED}.conf"
    sed -e "s|^seed .*|seed = ${SEED}|" \
        -e "s|^output_dir .*|output_dir = ${OUT}|" \
        "$SCENARIO" > "$CONF"
    ./build-rel/relationships "$CONF" > "${TMPDIR}/log_${SEED}" 2>&1 &
done
wait

# render narratives for each seed
total_lives=0
for i in $(seq 0 $((N-1))); do
    SEED=$((1000 + i))
    OUT="output/${BASENAME}__seed${SEED}"
    if [ ! -f "${OUT}/events.log" ]; then
        echo "FAILED seed=${SEED} (no events.log)" >&2
        cat "${TMPDIR}/log_${SEED}" >&2
        exit 1
    fi
    n=$(python3 analysis/witness_v0.py --all "$OUT" 2>&1 \
        | awk '/wrote/ { print $3 }')
    total_lives=$((total_lives + ${n:-0}))
    echo "  seed ${SEED}: ${n:-0} lives → ${OUT}/lives/"
done

echo "ok: ${N} seeds, ${total_lives} narratives total under output/${BASENAME}__seed*/lives/"
