"""Witness V0: turn one simulated agent's life into prose.

Reads the per-event log produced when `log_events = 1` and the most recent
agent snapshot, picks one agent with a "complete" arc, generates a
procedural name, and writes a past-tense narrative timeline of their life.

Usage:
  python3 analysis/witness_v0.py [run_dir]

Default run_dir = output/witness_v0.
"""
import sys
import csv
import hashlib
from pathlib import Path
from collections import defaultdict


# ---- procedural name pools ---------------------------------------------------
# Picked by hashing the agent ID. Deterministic; same agent ID always yields
# the same name. No LLM. About 30×30 = 900 distinct names per scheme — enough
# uniqueness for one run's worth of agents (≤ ~700).

GIVEN_PARTS = [
    "Mar", "Tel", "Ash", "Pell", "Bren", "Cor", "Dav", "Eli",
    "Fen", "Gar", "Hess", "Iv", "Jor", "Kel", "Lir", "Mern",
    "Nor", "Or", "Pyl", "Quel", "Rin", "Saf", "Tam", "Ul",
    "Var", "Wes", "Xen", "Yor", "Zell", "An",
]
NAME_TAILS = [
    "ka", "rik", "dor", "lan", "yn", "us", "ra", "ven",
    "is", "ow", "in", "el", "ath", "or", "an", "im",
    "yl", "et", "as", "uri", "ek", "om", "yna", "lo",
    "id", "us", "ame", "ish", "ay", "een",
]


def name_from_id(agent_id: int) -> str:
    h = hashlib.md5(f"agent_{agent_id}".encode()).digest()
    given = GIVEN_PARTS[h[0] % len(GIVEN_PARTS)]
    tail  = NAME_TAILS[h[1] % len(NAME_TAILS)]
    return given + tail


# ---- trait descriptors -------------------------------------------------------
# The simulation has TRAIT_COUNT=2, TRAIT_LEVELS=2, so 4 distinct trait groups.
# Each group_key in [0..3] gets one hand-written descriptor. Words are vague on
# purpose — the witness project is about marginalization-by-symmetry-break, so
# the trait names should not have inherent value loading.

TRAIT_LABELS = {
    0: "the smooth-skinned",
    1: "the dappled",
    2: "the marked",
    3: "the bright-eyed",
}


# ---- data loading ------------------------------------------------------------

def load_events(path: Path):
    events = []
    with open(path) as f:
        for i, line in enumerate(f):
            if i == 0:  # header
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            events.append({
                "tick": int(parts[0]),
                "kind": parts[1],
                "a": int(parts[2]),
                "b": int(parts[3]),
                "value": float(parts[4]),
            })
    return events


def load_latest_snapshot(snap_dir: Path):
    """Return the most recent tick_*.tsv snapshot as a dict mapping
    entity_id → {trait_key, coop_quality, ...}."""
    snaps = sorted(snap_dir.glob("tick_*.tsv"))
    if not snaps:
        return {}, 0
    latest = snaps[-1]
    tick = int(latest.stem.split("_")[1])
    agents = {}
    section = None
    with open(latest) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#") or not line:
                continue
            if line.startswith("[agents]"):
                section = "agents"; next(f); continue  # skip header
            if line.startswith("[relationships]"):
                section = "rels"; break
            if section == "agents":
                cols = line.split("\t")
                if len(cols) < 8:
                    continue
                entity = int(cols[0])
                agents[entity] = {
                    "resources": float(cols[1]),
                    "age": int(cols[3]),
                    "traits": cols[5],
                    "group_key": int(cols[7]),
                }
    return agents, tick


def collect_traits_from_snapshots(snap_dir: Path):
    """Build entity_id -> group_key from ALL snapshots so we know traits even
    for agents who died before the final snapshot."""
    traits = {}
    for snap in sorted(snap_dir.glob("tick_*.tsv")):
        section = None
        with open(snap) as f:
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("#") or not line:
                    continue
                if line.startswith("[agents]"):
                    section = "agents"; next(f); continue
                if line.startswith("[relationships]"):
                    break
                if section == "agents":
                    cols = line.split("\t")
                    if len(cols) >= 8:
                        traits[int(cols[0])] = int(cols[7])
    return traits


# ---- agent selection ---------------------------------------------------------

def index_lives(events):
    """Return {agent_id: dict(birth=tick, death=tick or None,
                                ventures=int, relationships_formed=int)}."""
    lives = defaultdict(lambda: {
        "birth": None, "death": None, "initial_resources": None,
        "ventures": 0, "venture_successes": 0, "venture_failures": 0,
        "relationships_formed": 0, "relationships_lost": 0,
    })
    for e in events:
        a, b, kind, tick = e["a"], e["b"], e["kind"], e["tick"]
        if kind == "agent_birth":
            lives[a]["birth"] = tick
            lives[a]["initial_resources"] = e["value"]
        elif kind == "agent_death":
            lives[a]["death"] = tick
        elif kind == "venture_success":
            lives[a]["ventures"] += 1; lives[a]["venture_successes"] += 1
            lives[b]["ventures"] += 1; lives[b]["venture_successes"] += 1
        elif kind == "venture_failure":
            lives[a]["ventures"] += 1; lives[a]["venture_failures"] += 1
            lives[b]["ventures"] += 1; lives[b]["venture_failures"] += 1
        elif kind == "relationship_created":
            lives[a]["relationships_formed"] += 1
            lives[b]["relationships_formed"] += 1
        elif kind == "relationship_destroyed":
            lives[a]["relationships_lost"] += 1
            lives[b]["relationships_lost"] += 1
    return lives


def select_subject(lives, max_tick, traits):
    """Pick an agent with a complete and reasonably full life."""
    candidates = []
    for aid, life in lives.items():
        if life["birth"] is None or life["death"] is None:
            continue
        lifespan = life["death"] - life["birth"]
        if lifespan < 1500:
            continue
        if life["ventures"] < 30:
            continue
        if life["relationships_formed"] < 4:
            continue
        if aid not in traits:
            continue
        candidates.append((aid, life, lifespan))

    if not candidates:
        return None

    # pick the candidate whose venture-failure rate diverges most from the
    # population norm — that gives us someone visibly affected by the
    # loss-aversion dynamics. Tie-break by lifespan, then by id.
    fail_rates = []
    for aid, life, _ in candidates:
        rate = life["venture_failures"] / max(life["ventures"], 1)
        fail_rates.append(rate)
    avg_fail = sum(fail_rates) / len(fail_rates)

    def key(c):
        aid, life, lifespan = c
        rate = life["venture_failures"] / max(life["ventures"], 1)
        return (-abs(rate - avg_fail), -lifespan, aid)

    candidates.sort(key=key)
    return candidates[0][0]


# ---- narrative rendering -----------------------------------------------------

def years(tick, ticks_per_year=365):
    """Translate ticks into 'year N, day M' style time. Pure prose helper."""
    y = tick // ticks_per_year
    d = tick % ticks_per_year
    return y, d


def render_life(events, subject, traits, lives):
    name = name_from_id(subject)
    trait_label = TRAIT_LABELS.get(traits.get(subject, 0), "of unknown lineage")
    life = lives[subject]
    out = []

    sub_events = [e for e in events
                  if e["a"] == subject or e["b"] == subject]
    sub_events.sort(key=lambda e: e["tick"])

    # opening
    if life["birth"] is None:
        out.append(f"{name} of the original generation, {trait_label}, "
                   f"woke into the world before the chronicler began counting.")
    else:
        y, d = years(life["birth"])
        ir = life.get("initial_resources")
        ir_str = f" with {ir:.0f} measures of food set aside" if ir else ""
        out.append(f"{name}, {trait_label}, was born in year {y}, day {d}"
                   f"{ir_str}.")

    # First few interactions, then summary, then last few interactions.
    # The full event stream would be far too long to read; we want the shape
    # of the life, not every venture. So: render the first 5 events,
    # the last 5 events, and a paragraph summary in between.

    cap_early = 6
    cap_late = 8
    relevant = [e for e in sub_events if e["kind"] != "agent_birth"]

    # build per-partner stats so the narration can name partners properly
    partner_first_meeting = {}  # other_id -> first tick they met subject
    partner_outcomes = defaultdict(lambda: {"win": 0, "loss": 0})
    for e in relevant:
        other = e["b"] if e["a"] == subject else e["a"]
        if other == 0:
            continue
        partner_first_meeting.setdefault(other, e["tick"])
        if e["kind"] == "venture_success":
            partner_outcomes[other]["win"] += 1
        elif e["kind"] == "venture_failure":
            partner_outcomes[other]["loss"] += 1

    def render_event(e, ctx):
        other = e["b"] if e["a"] == subject else e["a"]
        other_name = name_from_id(other) if other and other != 0 else None
        other_label = TRAIT_LABELS.get(traits.get(other, -1), "of an unfamiliar kind")
        y, d = years(e["tick"])
        if e["kind"] == "relationship_created":
            return (f"In year {y} day {d}, {name} first met {other_name}, "
                    f"{other_label}. The bond was new and uncertain "
                    f"(trust {e['value']:+.2f}).")
        if e["kind"] == "venture_success":
            return (f"Year {y}, day {d}: {name} and {other_name} ventured "
                    f"together and it went well. Trust between them stood at "
                    f"{e['value']:+.2f}.")
        if e["kind"] == "venture_failure":
            return (f"Year {y}, day {d}: {name} and {other_name} tried "
                    f"something and it failed them. Trust slipped to "
                    f"{e['value']:+.2f}.")
        if e["kind"] == "relationship_destroyed":
            return (f"In year {y} day {d}, {name}'s tie to {other_name} was "
                    f"severed — one of them did not survive what came next.")
        if e["kind"] == "agent_death":
            return (f"In year {y} day {d}, {name} died.")
        return f"({e['tick']}: {e['kind']})"

    # opening events
    if relevant:
        out.append("")
        out.append("Early life:")
        for e in relevant[:cap_early]:
            out.append("  " + render_event(e, "early"))

    # midlife summary
    if life["ventures"] > 0:
        win_rate = life["venture_successes"] / life["ventures"]
        out.append("")
        out.append(f"Across the years, {name} attempted {life['ventures']} "
                   f"ventures with others. Of these, {life['venture_successes']} "
                   f"succeeded ({win_rate:.0%}) and {life['venture_failures']} "
                   f"failed.")
        out.append(f"They formed {life['relationships_formed']} relationships "
                   f"and watched {life['relationships_lost']} of those bonds "
                   f"end (most because the other person died, some because "
                   f"trust drifted to nothing).")

    # closing events. We want the death event to land prominently — but it
    # often shares a tick with a cascade of relationship_destroyed events,
    # which would otherwise crowd it out of a naive tail slice. So: pick the
    # last K events that come BEFORE the death, then end with the death line.
    death_idx = None
    for i, e in enumerate(relevant):
        if e["kind"] == "agent_death":
            death_idx = i
            break

    if death_idx is not None:
        out.append("")
        out.append("Later life:")
        pre_death = relevant[:death_idx]
        # show last cap_late events leading up to death, plus a 1-line
        # summary of how many ties were severed at death (the cascade)
        for e in pre_death[-cap_late:]:
            out.append("  " + render_event(e, "late"))
        # cascade summary
        post = relevant[death_idx + 1:]
        same_tick_destroys = sum(1 for e in post
                                 if e["kind"] == "relationship_destroyed"
                                 and e["tick"] == relevant[death_idx]["tick"])
        if same_tick_destroys:
            y, d = years(relevant[death_idx]["tick"])
            out.append(f"  In year {y} day {d}, {name} died. "
                       f"{same_tick_destroys} bonds went unwitnessed at the "
                       f"same hour, severed because no one was left on "
                       f"{name}'s side of them.")
        else:
            out.append("  " + render_event(relevant[death_idx], "late"))
    elif len(relevant) > cap_early + cap_late:
        out.append("")
        out.append("Later life:")
        for e in relevant[-cap_late:]:
            out.append("  " + render_event(e, "late"))
    elif len(relevant) > cap_early:
        out.append("")
        out.append("Later life:")
        for e in relevant[cap_early:]:
            out.append("  " + render_event(e, "late"))

    # frame: show the shape of the trust the system held them in
    by_partner_label = defaultdict(lambda: {"win": 0, "loss": 0})
    for partner, oc in partner_outcomes.items():
        plabel = traits.get(partner, -1)
        by_partner_label[plabel]["win"] += oc["win"]
        by_partner_label[plabel]["loss"] += oc["loss"]
    if by_partner_label:
        out.append("")
        out.append("How the world treated them, by trait of partner:")
        own_trait = traits.get(subject, -1)
        for tk, oc in sorted(by_partner_label.items()):
            tot = oc["win"] + oc["loss"]
            if tot == 0:
                continue
            label = TRAIT_LABELS.get(tk, "of an unknown kind")
            wr = oc["win"] / tot
            same = " (same kind as them)" if tk == own_trait else ""
            out.append(f"  • with {label}{same}: "
                       f"{oc['win']}/{tot} ventures succeeded "
                       f"({wr:.0%}).")

    return "\n".join(out)


# ---- main --------------------------------------------------------------------

def main():
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output/witness_v0")
    if not run_dir.exists():
        sys.exit(f"no run dir at {run_dir} — run scenarios/witness_v0.conf first")

    events_path = run_dir / "events.log"
    if not events_path.exists():
        sys.exit(f"no events.log at {events_path} — was log_events=1 set?")

    snap_dir = run_dir / "snapshots"
    print(f"# loading {events_path}")
    events = load_events(events_path)
    print(f"# {len(events):,} events")
    traits = collect_traits_from_snapshots(snap_dir)
    print(f"# {len(traits)} agents seen across snapshots")

    lives = index_lives(events)
    max_tick = max(e["tick"] for e in events)

    subject = select_subject(lives, max_tick, traits)
    if subject is None:
        sys.exit("no agent met the selection criteria — relax thresholds and rerun")
    print(f"# selected agent {subject}")
    print()

    print(render_life(events, subject, traits, lives))


if __name__ == "__main__":
    main()
