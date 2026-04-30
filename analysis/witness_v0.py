"""Witness V0: turn one simulated agent's life into prose.

Reads the per-event log produced when `log_events = 1` and the most recent
agent snapshot, picks one agent with a "complete" arc, generates a
procedural name, and writes a past-tense narrative timeline of their life.

Usage:
  python3 analysis/witness_v0.py [run_dir]              # render one to stdout
  python3 analysis/witness_v0.py --all [run_dir]        # render every qualifying
                                                          agent to <run_dir>/lives/

Default run_dir = output/witness_v0.
"""
import csv
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

# ---- procedural name pools ---------------------------------------------------
# Picked by hashing the agent ID. Deterministic; same agent ID always yields
# the same name. No LLM. About 30×30 = 900 distinct names per scheme — enough
# uniqueness for one run's worth of agents (≤ ~700).

GIVEN_PARTS = [
    "Sel", "Tel", "Ash", "Pell", "Bren", "Cor", "Dav", "Eli",
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
    0: "the fat bottoms",
    1: "east coast",
    2: "west coast",
    3: "goldies",
}


# ---- place rendering helpers -------------------------------------------------
# Place names come from snapshots, but the preposition that fronts them in
# prose ("at the Old One" vs "in a wheat field" vs "on the grazed pasture") is
# a function of the place's type — encoded once here so both agent and place
# biographies render consistently.

PLACE_PREPS = {
    "tavern":  "at",
    "river":   "at",
    "house":   "in",
    "field":   "in",
    "pasture": "on",
    "ruins":   "at",
}

# Verbs of motion ("they went __ X") want a different preposition than the
# static setting clause ("a venture happened __ X"). Most places take "to";
# fields and pastures take "out to" because that's how English handles them.
PLACE_MOTION_PREPS = {
    "tavern":  "to",
    "river":   "to",
    "house":   "to",
    "field":   "out to",
    "pasture": "out to",
    "ruins":   "to",
}


def name_inline(name: str) -> str:
    """Lowercase a leading 'The'/'A' so the place name reads naturally
    mid-sentence ('at the Hidden Rapids', not 'at The Hidden Rapids').
    Other names ('Bill's', 'Green Eyes', 'Jutt's Creek') pass through."""
    if name.startswith("The "):
        return "the " + name[4:]
    if name.startswith("A "):
        return "a " + name[2:]
    return name


def setting_clause(places, place_id):
    """Returns ', at the Old One' / ', on the grazed pasture' / etc., or ''
    when the place is unknown (place_id == -1, or no places dict)."""
    if place_id is None or place_id < 0 or not places:
        return ""
    p = places.get(place_id)
    if not p:
        return ""
    prep = PLACE_PREPS.get(p["type"], "at")
    return f", {prep} {name_inline(p['name'])}"


def shared_event_lines(events, subject, places):
    """Render fire and notable-death witnessings for `subject`.

    For each fire, we have two signals: how much of the subject's *life* was
    spent at the burned place (the count, normalized by their total
    ventures), and the simulation's own attachment-weight at the moment of
    the fire (the value field of fire_witnessed). The prose grade folds
    both: long-time regulars get the heavy line; agents whose life only
    glanced the place get the lighter one.

    For notable deaths, ventures-with-the-deceased and pairwise trust at
    the moment of death (carried in the event's value) jointly determine
    the weight."""
    name = name_from_id(subject)

    sub_place_count   = defaultdict(int)
    sub_partner_count = defaultdict(int)
    sub_total_ventures = 0
    for e in events:
        if e["kind"] not in ("venture_success", "venture_failure"):
            continue
        if e["a"] != subject and e["b"] != subject:
            continue
        sub_total_ventures += 1
        pid = e.get("place_id", -1)
        if pid >= 0:
            sub_place_count[pid] += 1
        partner = e["b"] if e["a"] == subject else e["a"]
        if partner:
            sub_partner_count[partner] += 1

    out = []
    for e in events:
        if e["kind"] == "fire_witnessed" and e["a"] == subject:
            pid = e.get("place_id", -1)
            p = places.get(pid) if places else None
            if not p:
                continue
            y, d = years(e["tick"])
            inline = name_inline(p["name"])
            count = sub_place_count.get(pid, 0)

            # Grade by the simulation's own prior_w — the agent's attachment
            # magnitude at the moment of the fire. With loss-aversion driving
            # most attachments negative, the sign matters as much as the
            # magnitude: a strongly-negative attachment is a place the agent
            # had come to dread; a strongly-positive one is a place they had
            # come to lean on. Both are "high attached" but the meaning of
            # the fire differs.
            prior_w  = e["value"]
            attached = abs(prior_w)

            if prior_w >= 0.5:
                out.append(f"  In year {y} day {d}, fire took {inline}. "
                           f"{name} had come to lean on it ({count} "
                           f"ventures, attachment {prior_w:+.2f}); the "
                           f"loss took something from them.")
            elif prior_w <= -0.5:
                out.append(f"  In year {y} day {d}, fire took {inline}. "
                           f"{name} had come to dread it ({count} "
                           f"ventures, attachment {prior_w:+.2f}); the "
                           f"fire was a closure they hadn't asked for.")
            elif attached >= 0.15:
                out.append(f"  In year {y} day {d}, fire took {inline}. "
                           f"{name} knew it some ({count} ventures, "
                           f"attachment {prior_w:+.2f}); the news "
                           f"reached them.")
            elif count >= 1:
                out.append(f"  In year {y} day {d}, {inline} burned. "
                           f"{name} had been there {count} times "
                           f"(attachment {prior_w:+.2f}); the smoke was "
                           f"rumor more than wound.")
            else:
                out.append(f"  In year {y} day {d}, {inline} burned. "
                           f"{name} had never been there; "
                           f"someone else's grief.")
        elif e["kind"] == "notable_death_witnessed" and e["a"] == subject:
            deceased_id = e["b"]
            deceased_name = name_from_id(deceased_id)
            y, d = years(e["tick"])
            shared = sub_partner_count.get(deceased_id, 0)
            shared_frac = (shared / sub_total_ventures) if sub_total_ventures else 0
            trust = e["value"]
            if shared_frac >= 0.10 and trust >= 0.7:
                out.append(f"  In year {y} day {d}, {deceased_name} died. "
                           f"{name} had ventured with them {shared} times "
                           f"({shared_frac:.0%} of their life, trust "
                           f"{trust:+.2f}); the world thinned.")
            elif shared_frac >= 0.03:
                out.append(f"  In year {y} day {d}, {deceased_name} died. "
                           f"{name} had ventured with them {shared} times "
                           f"({shared_frac:.0%} of their life, trust "
                           f"{trust:+.2f}); it weighed.")
            else:
                out.append(f"  In year {y} day {d}, {deceased_name} died. "
                           f"{name} had ventured with them {shared} times "
                           f"(trust {trust:+.2f}); the loss was real "
                           f"but distant.")
    return out


# ---- data loading ------------------------------------------------------------

def load_events(path: Path):
    """Read events.log. Tolerates both the legacy 5-column format (no place
    info, written before the witness-world places module) and the 6-column
    format with a place_id. Missing place_id rows get place_id = -1."""
    events = []
    with open(path) as f:
        for i, line in enumerate(f):
            if i == 0:  # header
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            place_id = int(parts[5]) if len(parts) >= 6 else -1
            events.append({
                "tick": int(parts[0]),
                "kind": parts[1],
                "a": int(parts[2]),
                "b": int(parts[3]),
                "value": float(parts[4]),
                "place_id": place_id,
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


def load_stories_from_snapshots(snap_dir: Path):
    """Walk every snapshot and pick up each (agent, story-slot) pair.
    For a given agent and a given originating event (keyed by origin_tick
    + origin_kind + origin_place), the most-recent snapshot wins —
    that's the closest representation we have of that story's slot at
    the end of that agent's life.

    Returns: {agent_id: list of slot dicts, each with keys
                  origin_tick, origin_kind, origin_place,
                  was_direct, source_was_origin, origin_magnitude,
                  source_id, snapshot_tick}}.
    Empty dict if no snapshots have a [stories] section."""
    stories_by_agent = defaultdict(dict)  # {agent: {key: slot}}
    for snap in sorted(snap_dir.glob("tick_*.tsv")):
        snap_tick = int(snap.stem.split("_")[1])
        section = None
        with open(snap) as f:
            for line in f:
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[stories]"):
                    section = "stories"; next(f); continue
                if line.startswith("["):
                    section = None; continue
                if section == "stories":
                    cols = line.split("\t")
                    if len(cols) < 8:
                        continue
                    aid = int(cols[0])
                    slot = {
                        "origin_tick":      int(cols[1]),
                        "origin_kind":      int(cols[2]),
                        "origin_place":     int(cols[3]),
                        "was_direct":       int(cols[4]),
                        "source_was_origin":int(cols[5]),
                        "origin_magnitude": float(cols[6]),
                        "source_id":        int(cols[7]),
                        "snapshot_tick":    snap_tick,
                    }
                    key = (slot["origin_tick"], slot["origin_kind"],
                           slot["origin_place"])
                    stories_by_agent[aid][key] = slot
    return {aid: list(slots.values())
            for aid, slots in stories_by_agent.items()}


def story_fidelity_at(slot, t, decay_per_year=0.92):
    """Continuous decay from origin: fidelity(t) = decay^years_since_origin.
    Defaults to 0.92 to match config's provisional default; pass the
    actual decay used in the run if rendering analysis-style output."""
    dt = t - slot["origin_tick"]
    if dt <= 0: return 1.0
    if decay_per_year <= 0: return 0.0
    if decay_per_year >= 1: return 1.0
    return decay_per_year ** (dt / 365.0)


def render_inherited_stories(slots, subject_name, places, traits,
                             biography_tick, decay_per_year,
                             min_fidelity=0.10, max_lines=5):
    """Render the 'What they had heard' section for one agent. Filters to
    inherited slots (was_direct=0), sorts by current fidelity descending,
    caps at max_lines.

    Three prose tiers:
      - high fidelity (>= 0.5): full detail preserved
      - mid fidelity  (>= min_fidelity): vague but present
      - below min_fidelity: dropped (story has died)

    Two provenance tiers within each, set by `source_was_origin`:
      - 1: "inherited from <name> the story of..."
      - 0: "the story had reached <name> from before her own time, and
            from <name> it reached <subject>"
    """
    rows = []
    for slot in slots:
        if slot["was_direct"]:
            continue                    # rendered elsewhere
        fid = story_fidelity_at(slot, biography_tick, decay_per_year)
        if fid < min_fidelity:
            continue
        rows.append((fid, slot))
    rows.sort(key=lambda r: -r[0])
    rows = rows[:max_lines]
    if not rows:
        return []

    out = ["What they had heard:"]
    for fid, slot in rows:
        y, d = years(slot["origin_tick"])
        kind = slot["origin_kind"]
        pid  = slot["origin_place"]
        place = places.get(pid) if (places and pid >= 0) else None
        place_inline = name_inline(place["name"]) if place else None
        prep = PLACE_PREPS.get(place["type"], "at") if place else "somewhere"
        ancestor_name = (name_from_id(slot["source_id"])
                         if slot["source_id"] else None)
        # What was the event?
        if kind == 0:
            event_phrase = f"fire {prep} {place_inline}" if place_inline else "a fire"
        elif kind == 1:
            event_phrase = (f"a notable death {prep} {place_inline}"
                            if place_inline
                            else "a notable death")
        else:
            event_phrase = "an event"

        if fid >= 0.5:
            # High fidelity: details are intact. Year is given precisely;
            # the chronicler renders the agent's actual knowledge.
            if slot["source_was_origin"] and ancestor_name:
                out.append(f"  In year {y}, {event_phrase}. "
                           f"{ancestor_name} had been there; from {ancestor_name} "
                           f"the story reached {subject_name} intact "
                           f"(fidelity {fid:.2f}).")
            elif ancestor_name:
                out.append(f"  In year {y}, {event_phrase}. The story had "
                           f"reached {ancestor_name} from before her own time, "
                           f"and from {ancestor_name} it reached {subject_name} "
                           f"(fidelity {fid:.2f}).")
            else:
                out.append(f"  In year {y}, {event_phrase}. "
                           f"{subject_name} carried the story, source forgotten "
                           f"(fidelity {fid:.2f}).")
        else:
            # Mid fidelity: the chronicler uses parentheses to separate
            # what the simulation knows from what the agent knows. The
            # agent doesn't experience year-precision; the chronicler does.
            if slot["source_was_origin"] and ancestor_name:
                out.append(f"  {subject_name} knew, vaguely, of "
                           f"{event_phrase} in some year long before "
                           f"(the chronicle says year {y}). "
                           f"{ancestor_name} had been there, but to "
                           f"{subject_name} the story was almost folklore "
                           f"(fidelity {fid:.2f}).")
            elif ancestor_name:
                out.append(f"  {subject_name} carried the dim shape of "
                           f"{event_phrase}, long before — the chronicle says "
                           f"year {y}; to {subject_name} it was simply long ago. "
                           f"Whose ancestor had stood in it, the story did not "
                           f"keep (fidelity {fid:.2f}).")
            else:
                out.append(f"  Some half-remembered {event_phrase} — the "
                           f"chronicle dates it to year {y}, but {subject_name} "
                           f"only knew it had happened (fidelity {fid:.2f}).")
    return out


def load_places(snap_dir: Path):
    """Read the [places] section from the most recent snapshot. Returns
    {place_index: {'name': str, 'type': str, 'fires': int, 'deaths': int,
                   'total_ventures': int}}. Empty dict if the snapshot has
    no places section (legacy run, or places_enabled=0 with empty section).
    Tolerates both the V1 3-column format (place_index, name, type) and the
    V2 6-column format that adds fires/deaths/total_ventures."""
    snaps = sorted(snap_dir.glob("tick_*.tsv"))
    if not snaps:
        return {}
    places = {}
    section = None
    with open(snaps[-1]) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            if line.startswith("[places]"):
                section = "places"; next(f); continue  # skip header
            if line.startswith("["):
                section = None; continue
            if section == "places":
                cols = line.split("\t")
                if len(cols) >= 3:
                    rec = {"name": cols[1], "type": cols[2],
                           "fires": 0, "deaths": 0, "total_ventures": 0}
                    if len(cols) >= 6:
                        rec["fires"]          = int(cols[3])
                        rec["deaths"]         = int(cols[4])
                        rec["total_ventures"] = int(cols[5])
                    places[int(cols[0])] = rec
    return places


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


def qualifying_agents(lives, traits,
                      min_lifespan=1500, min_ventures=30, min_relationships=4):
    """Return list of (aid, life, lifespan) tuples for every agent with a
    complete and reasonably full life arc."""
    out = []
    for aid, life in lives.items():
        if life["birth"] is None or life["death"] is None:
            continue
        lifespan = life["death"] - life["birth"]
        if lifespan < min_lifespan:
            continue
        if life["ventures"] < min_ventures:
            continue
        if life["relationships_formed"] < min_relationships:
            continue
        if aid not in traits:
            continue
        out.append((aid, life, lifespan))
    return out


def select_subject(lives, max_tick, traits):
    """Pick an agent with a complete and reasonably full life."""
    candidates = qualifying_agents(lives, traits)

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


def render_life(events, subject, traits, lives, places=None,
                stories_by_agent=None, decay_per_year=0.92):
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
    # Witness-world Phase 2: shared-event records (fire_witnessed,
    # notable_death_witnessed) are rendered in their own dedicated section
    # below. Strip them from `relevant` so they don't appear as
    # raw '(tick: fire_witnessed)' lines in the early/late slices.
    SHARED_KINDS = {"fire_witnessed", "notable_death_witnessed"}
    relevant = [e for e in sub_events
                if e["kind"] != "agent_birth"
                and e["kind"] not in SHARED_KINDS]

    # Witness-world: relationship_created/destroyed events don't carry a
    # place_id (they're logged outside the venture system), but they always
    # co-occur with a venture event at the same tick involving the same pair.
    # Borrow that venture's place so first-encounter and severing lines can be
    # rendered with their setting attached.
    venture_place = {}
    for e in relevant:
        if e["kind"] not in ("venture_success", "venture_failure"):
            continue
        key = (e["tick"], frozenset({e["a"], e["b"]}))
        venture_place.setdefault(key, e.get("place_id", -1))

    def event_place(e):
        pid = e.get("place_id", -1)
        if pid >= 0:
            return pid
        key = (e["tick"], frozenset({e["a"], e["b"]}))
        return venture_place.get(key, -1)

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
        setting = setting_clause(places, event_place(e))
        if e["kind"] == "relationship_created":
            return (f"In year {y} day {d}{setting}, {name} first met "
                    f"{other_name}, {other_label}. The bond was new and "
                    f"uncertain (trust {e['value']:+.2f}).")
        if e["kind"] == "venture_success":
            return (f"Year {y}, day {d}{setting}: {name} and {other_name} "
                    f"ventured together and it went well. Trust between "
                    f"them stood at {e['value']:+.2f}.")
        if e["kind"] == "venture_failure":
            return (f"Year {y}, day {d}{setting}: {name} and {other_name} "
                    f"tried something and it failed them. Trust slipped to "
                    f"{e['value']:+.2f}.")
        if e["kind"] == "relationship_destroyed":
            return (f"In year {y} day {d}, {name}'s tie to {other_name} was "
                    f"severed — one of them did not survive what came next.")
        if e["kind"] == "agent_death":
            return (f"In year {y} day {d}, {name} died.")
        return f"({e['tick']}: {e['kind']})"

    # opening events: first encounter with each trait group, in order met.
    # This mirrors the per-trait coda — the reader is introduced to each
    # group at the start, then sees how the relationships across those groups
    # turned out at the end. Falls back to plain first-N if traits are
    # unknown for too many early partners.
    early_intros = []
    seen_traits = set()
    for e in relevant:
        if e["kind"] != "relationship_created":
            continue
        other = e["b"] if e["a"] == subject else e["a"]
        if other == 0:
            continue
        ptrait = traits.get(other, -1)
        if ptrait in seen_traits:
            continue
        seen_traits.add(ptrait)
        early_intros.append((e, other, ptrait))
        if len(seen_traits) >= len(TRAIT_LABELS):
            break

    if relevant:
        out.append("")
        out.append("Early life:")
        if len(early_intros) >= 2:
            for e, other, ptrait in early_intros:
                y, d = years(e["tick"])
                pname = name_from_id(other)
                plabel = TRAIT_LABELS.get(ptrait, "of an unfamiliar kind")
                trust = e["value"]
                if trust >= 0:
                    outcome = "their first venture went well"
                else:
                    outcome = "their first venture failed"
                setting = setting_clause(places, event_place(e))
                out.append(f"  In year {y} day {d}{setting}, {name}'s first "
                           f"encounter with {plabel} — {pname} — "
                           f"{outcome}; trust set to {trust:+.2f}.")
        else:
            # not enough trait info for the structured intro — fall back
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

    # Witness-world Phase 2: shared events the world inflicted on this life.
    # Fires they witnessed (graded by their prior history at the place) and
    # notable deaths they grieved (graded by ventures-shared with the
    # deceased). Chronological. Skipped when no such events touched them.
    shared = shared_event_lines(events, subject, places)
    if shared:
        out.append("")
        out.append("What the world did to them:")
        out.extend(shared)

    # Witness-world Phase 3: inherited stories — the cultural memory the
    # subject carried, sampled from a single social ancestor at spawn and
    # decayed continuously from each story's origin tick. Rendered with
    # epistemic framing distinct from direct experience: high-fidelity
    # stories preserve names and years; low-fidelity ones use parenthetical
    # chronicler-knows / agent-doesn't-know construction. Skipped when no
    # stories survive at biography time.
    if stories_by_agent is not None and subject in stories_by_agent:
        slots = stories_by_agent[subject]
        # Biography tick: the latest snapshot tick at which the subject
        # appeared (their final captured-state moment).
        bio_tick = max((s["snapshot_tick"] for s in slots), default=0)
        story_lines = render_inherited_stories(
            slots, name, places, traits, bio_tick, decay_per_year)
        if story_lines:
            out.append("")
            out.extend(story_lines)

    # midlife bridge: name the partner the subject ventured with most often
    # and give the reader one specific human-scale fact about the middle of
    # the life. Skips when no clear standout (≥ 20 ventures with one partner).
    pair_counts = defaultdict(lambda: {"win": 0, "loss": 0,
                                       "first": None, "last": None})
    for e in relevant:
        if e["kind"] not in ("venture_success", "venture_failure"):
            continue
        other = e["b"] if e["a"] == subject else e["a"]
        if other == 0:
            continue
        c = pair_counts[other]
        if e["kind"] == "venture_success":
            c["win"] += 1
        else:
            c["loss"] += 1
        if c["first"] is None:
            c["first"] = e["tick"]
        c["last"] = e["tick"]

    if pair_counts:
        partner, c = max(pair_counts.items(),
                         key=lambda kv: (kv[1]["win"] + kv[1]["loss"], kv[0]))
        total = c["win"] + c["loss"]
        if total >= 20:
            mid_y, _ = years((c["first"] + c["last"]) // 2)
            pname = name_from_id(partner)
            plabel = TRAIT_LABELS.get(traits.get(partner, -1),
                                      "of an unfamiliar kind")
            if c["win"] > c["loss"]:
                out.append(
                    f"By year {mid_y}, {name} had grown close to {pname} "
                    f"({plabel}); they ventured together {total} times, and "
                    f"only {c['loss']} of those went badly.")
            else:
                out.append(
                    f"By year {mid_y}, {name} and {pname} ({plabel}) had "
                    f"settled into a wary kind of partnership; of {total} "
                    f"ventures together, only {c['win']} went well.")

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
        own_trait = traits.get(subject, -1)
        rows = []
        for tk, oc in sorted(by_partner_label.items()):
            tot = oc["win"] + oc["loss"]
            if tot == 0:
                continue
            label = TRAIT_LABELS.get(tk)
            if not label:
                # Skip partners whose trait was never captured (died before
                # the first snapshot). Including them produced
                # "with of an unknown kind: …", which reads as a typo.
                continue
            wr = oc["win"] / tot
            same = " (same kind as them)" if tk == own_trait else ""
            rows.append(f"  • with {label}{same}: "
                        f"{oc['win']}/{tot} ventures succeeded "
                        f"({wr:.0%}).")
        if rows:
            out.append("")
            out.append("How the world treated them, by trait of partner:")
            out.extend(rows)

    # Witness-world: per-place outcome breakdown — a parallel to the trait coda
    # but indexed by where their ventures happened. Skipped when no place data.
    if places:
        by_place = defaultdict(lambda: {"win": 0, "loss": 0})
        for e in relevant:
            if e["kind"] not in ("venture_success", "venture_failure"):
                continue
            pid = e.get("place_id", -1)
            if pid < 0:
                continue
            if e["kind"] == "venture_success":
                by_place[pid]["win"] += 1
            else:
                by_place[pid]["loss"] += 1
        if by_place:
            out.append("")
            out.append("Where they spent their days:")
            ordered = sorted(by_place.items(),
                             key=lambda kv: -(kv[1]["win"] + kv[1]["loss"]))
            for pid, oc in ordered:
                p = places.get(pid)
                if not p:
                    continue
                tot = oc["win"] + oc["loss"]
                wr = oc["win"] / tot if tot else 0.0
                prep = PLACE_PREPS.get(p["type"], "at")
                out.append(f"  • {prep} {name_inline(p['name'])}: "
                           f"{oc['win']}/{tot} ventures went well "
                           f"({wr:.0%}).")

    return "\n".join(out)


# ---- place biography ---------------------------------------------------------
# Same arc as the agent biography — opening, midlife stats, named earliest and
# latest visits, a coda — but the subject is a place. Places don't die, so the
# emotional shape is the gap between what people wanted from the place and what
# they got: who kept coming back, what they came back to.

def _opening_line(name: str, type_str: str) -> str:
    """Per-type opening phrasing for a place biography. The naive uniform
    template ('{name}, a {type}, ...') breaks for two cases: 'a ruins' is
    ungrammatical, and 'A wheat field, a field, ...' is self-repeating.
    Handle both with the lightest possible touch — let the name lead the
    sentence, append the type clause only when it adds information."""
    # Names like "A wheat field" already carry their descriptor; adding
    # "a field" would just echo. Let the name stand alone.
    if name.startswith("A "):
        return f"{name} has been there for as long as the chronicle remembers."
    type_singular = "ruin" if type_str == "ruins" else type_str
    article = "an" if type_singular[:1].lower() in "aeiou" else "a"
    return (f"{name}, {article} {type_singular}, has been there for as "
            f"long as the chronicle remembers.")


def _place_character(rate: float, baseline: float) -> str:
    """A short clause describing how the place compares to the world's
    overall venture success rate. Returns '' when the place is unremarkable."""
    diff = rate - baseline
    if diff >  0.08: return "— a place where things tended to go well"
    if diff >  0.03: return "— a place that, on the whole, worked out"
    if diff > -0.03: return ""
    if diff > -0.08: return "— a place that often disappointed"
    return "— a place where things tended to fall apart, more often than not"


def render_place(events, place_idx, places, traits, lives,
                 baseline_success_rate=None,
                 stories_by_agent=None, decay_per_year=0.92):
    p = places.get(place_idx)
    if p is None:
        return f"(no place at index {place_idx})"

    name = p["name"]
    typ  = p["type"]
    prep = PLACE_PREPS.get(typ, "at")
    motion_prep = PLACE_MOTION_PREPS.get(typ, "to")
    inline = name_inline(name)
    fires_count  = p.get("fires", 0)
    deaths_count = p.get("deaths", 0)

    # Pull every event that happened at this place. We only stamp place_id on
    # venture events, so this is purely a venture-history walk.
    here = [e for e in events
            if e.get("place_id", -1) == place_idx
            and e["kind"] in ("venture_success", "venture_failure")]
    here.sort(key=lambda e: e["tick"])

    # Phase 2: world-events that touched this place (fires here, deaths
    # most-associated with this place).
    fires_here = sorted(
        [e for e in events
         if e["kind"] == "fire" and e.get("place_id", -1) == place_idx],
        key=lambda e: e["tick"])
    deaths_here = sorted(
        [e for e in events
         if e["kind"] == "notable_death" and e.get("place_id", -1) == place_idx],
        key=lambda e: e["tick"])

    out = []
    out.append(_opening_line(name, typ))

    if not here:
        out.append("")
        out.append("No one ever came here. The place waited.")
        return "\n".join(out)

    wins   = sum(1 for e in here if e["kind"] == "venture_success")
    losses = sum(1 for e in here if e["kind"] == "venture_failure")
    total  = wins + losses
    rate   = wins / total

    # Compute the world's baseline if not provided. Used to characterize this
    # place's outcome rate relative to the world it sits in.
    if baseline_success_rate is None:
        all_v = [e for e in events
                 if e["kind"] in ("venture_success", "venture_failure")]
        if all_v:
            baseline_success_rate = sum(1 for e in all_v
                                        if e["kind"] == "venture_success") / len(all_v)
        else:
            baseline_success_rate = rate

    char = _place_character(rate, baseline_success_rate)
    char_clause = f" {char}" if char else ""

    out.append("")
    out.append(f"Across the years, {total} ventures unfolded {prep} {inline}. "
               f"Of these, {wins} went well ({rate:.0%}) and {losses} did "
               f"not{char_clause}.")

    # Phase 2: things-that-befell-this-place. Touchstone events render
    # before the per-event slices because they're the place's biography
    # spine — what the place itself "remembered". Skipped when none.
    if fires_here or deaths_here:
        out.append("")
        out.append("Touchstones:")
        for e in fires_here:
            y, d = years(e["tick"])
            n_aff = int(e["value"])
            out.append(f"  In year {y} day {d}, fire visited {inline}. "
                       f"{n_aff} souls were alive that hour; "
                       f"the place was changed.")
        for e in deaths_here:
            y, d = years(e["tick"])
            n_strong = int(e["value"])
            who = name_from_id(e["a"]) if e["a"] else "someone"
            who_trait = TRAIT_LABELS.get(traits.get(e["a"], -1))
            who_str = f"{who} ({who_trait})" if who_trait else who
            out.append(f"  In year {y} day {d}, {who_str} died. "
                       f"{inline} had been their place above all others, "
                       f"hosting {n_strong} bonds that grieved them.")

    # Phase 3: how many living agents still carry a story originating at
    # this place, and at what fidelity. Graph op = filter all alive agents
    # by (∃ slot ∈ Stories : slot.origin_place == this_place ∧
    # slot.fidelity ≥ τ). Human face = "still carried", broken into the
    # high-fidelity tier ("first-hand fidelity") and the mid-fidelity tier
    # ("folklore"). Skipped when no living carriers remain.
    if stories_by_agent:
        # Use the latest snapshot tick we saw — same as the agent biographies'
        # biography_tick discipline. We only count once per (carrier, slot).
        latest_tick = max(
            (s["snapshot_tick"]
             for slots in stories_by_agent.values() for s in slots),
            default=0)
        high_carriers = 0
        mid_carriers  = 0
        for aid, slots in stories_by_agent.items():
            best_fid = 0.0
            for s in slots:
                if s["origin_place"] != place_idx: continue
                # Only count from the latest snapshot the carrier appeared
                # in (their biography moment).
                if s["snapshot_tick"] != latest_tick: continue
                fid = story_fidelity_at(s, latest_tick, decay_per_year)
                if fid > best_fid: best_fid = fid
            if best_fid >= 0.5:
                high_carriers += 1
            elif best_fid >= 0.10:
                mid_carriers += 1
        if high_carriers or mid_carriers:
            out.append("")
            ly, _ = years(latest_tick)
            total_carriers = high_carriers + mid_carriers
            out.append(f"By year {ly}, {total_carriers} people still "
                       f"carried a story of {inline} — {high_carriers} of "
                       f"them at first-hand fidelity, {mid_carriers} of "
                       f"them as folklore.")

    # Earliest visits — the place's first few witnesses.
    cap_early = 4
    cap_late  = 5

    def _line(e):
        a, b = e["a"], e["b"]
        an = name_from_id(a) if a else "someone"
        bn = name_from_id(b) if b else "someone"
        at = TRAIT_LABELS.get(traits.get(a, -1))
        bt = TRAIT_LABELS.get(traits.get(b, -1))
        a_str = f"{an} ({at})" if at else an
        b_str = f"{bn} ({bt})" if bt else bn
        y, d = years(e["tick"])
        verb = ("their venture went well" if e["kind"] == "venture_success"
                else "their venture failed")
        return (f"  In year {y} day {d}, {a_str} and {b_str} went "
                f"{motion_prep} {inline}; {verb}.")

    out.append("")
    out.append("Earliest visits:")
    for e in here[:cap_early]:
        out.append(_line(e))

    # Who came back most. Counts unique-visitor stats across the place's
    # entire history. Cap at 4 names so this stays a paragraph, not a roster.
    visitor_outcomes = defaultdict(lambda: {"win": 0, "loss": 0})
    for e in here:
        for who in (e["a"], e["b"]):
            if not who:
                continue
            if e["kind"] == "venture_success":
                visitor_outcomes[who]["win"] += 1
            else:
                visitor_outcomes[who]["loss"] += 1

    if visitor_outcomes:
        ranked = sorted(visitor_outcomes.items(),
                        key=lambda kv: -(kv[1]["win"] + kv[1]["loss"]))
        # Filter to anyone who came back ≥ 5 times — once-visitors are noise
        # in this list. Cap the displayed count.
        regulars = [(aid, oc) for aid, oc in ranked
                    if (oc["win"] + oc["loss"]) >= 5][:4]
        if regulars:
            out.append("")
            out.append("Who came back most often:")
            for aid, oc in regulars:
                tot = oc["win"] + oc["loss"]
                wr  = oc["win"] / tot
                an  = name_from_id(aid)
                at  = TRAIT_LABELS.get(traits.get(aid, -1), "of an unfamiliar kind")
                out.append(f"  • {an}, {at}: {tot} visits, "
                           f"{oc['win']} good and {oc['loss']} bad ({wr:.0%}).")

    # Latest visits — what was happening at the place near the end of the run.
    if len(here) > cap_early + cap_late:
        out.append("")
        out.append("Latest visits:")
        for e in here[-cap_late:]:
            out.append(_line(e))

    # Coda: outcomes by partner trait at this place. Lets the reader see
    # whether the place was kinder to some kinds of agent than others — the
    # place-side echo of the per-agent trait coda.
    by_pair_trait = defaultdict(lambda: {"win": 0, "loss": 0})
    for e in here:
        # Index by an unordered pair of traits so we count each venture once.
        ta = traits.get(e["a"], -1)
        tb = traits.get(e["b"], -1)
        key = tuple(sorted((ta, tb)))
        if e["kind"] == "venture_success":
            by_pair_trait[key]["win"] += 1
        else:
            by_pair_trait[key]["loss"] += 1
    if by_pair_trait:
        rows = []
        for key, oc in by_pair_trait.items():
            tot = oc["win"] + oc["loss"]
            if tot < 5:
                continue
            ta_label = TRAIT_LABELS.get(key[0])
            tb_label = TRAIT_LABELS.get(key[1])
            if not ta_label or not tb_label:
                # Skip trait-pairs where one side never made it into a
                # snapshot — counting "of an unknown kind" rows just adds
                # noise to a coda that's about who fared well together.
                continue
            wr = oc["win"] / tot
            pair_str = (f"{ta_label} with their own" if key[0] == key[1]
                        else f"{ta_label} with {tb_label}")
            rows.append((tot, pair_str, oc["win"], wr))
        if rows:
            out.append("")
            out.append(f"Who fared well {prep} {inline}, and who didn't:")
            rows.sort(key=lambda r: -r[0])
            for tot, pair_str, wins, wr in rows:
                out.append(f"  • {pair_str}: {wins}/{tot} ventures went well "
                           f"({wr:.0%}).")

    return "\n".join(out)


# ---- main --------------------------------------------------------------------

def render_all(events, traits, lives, out_dir: Path, places=None,
               stories_by_agent=None, decay_per_year=0.92):
    """Render every qualifying agent's life to a separate text file in
    out_dir/<name>_<id>.txt. Returns count written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for aid, _life, _ls in sorted(qualifying_agents(lives, traits),
                                  key=lambda c: c[0]):
        text = render_life(events, aid, traits, lives, places=places,
                           stories_by_agent=stories_by_agent,
                           decay_per_year=decay_per_year)
        name = name_from_id(aid)
        path = out_dir / f"{name}_{aid}.txt"
        path.write_text(text + "\n")
        written += 1
    return written


def render_all_places(events, places, traits, lives, out_dir: Path,
                      stories_by_agent=None, decay_per_year=0.92):
    """Render every place's biography. Returns count written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for pid in sorted(places.keys()):
        text = render_place(events, pid, places, traits, lives,
                            stories_by_agent=stories_by_agent,
                            decay_per_year=decay_per_year)
        # Filename: stable, place-index-prefixed so they sort by index.
        slug = places[pid]["name"].replace(" ", "_").replace("'", "")
        path = out_dir / f"{pid:02d}_{slug}.txt"
        path.write_text(text + "\n")
        written += 1
    return written


def main():
    args = sys.argv[1:]
    all_mode = False
    all_places_mode = False
    place_idx = None
    while args and args[0].startswith("--"):
        if args[0] == "--all":
            all_mode = True
            args = args[1:]
        elif args[0] == "--all-places":
            all_places_mode = True
            args = args[1:]
        elif args[0] == "--place" and len(args) >= 2:
            place_idx = int(args[1])
            args = args[2:]
        else:
            sys.exit(f"unknown flag {args[0]}")
    run_dir = Path(args[0]) if args else Path("output/witness_v0")
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
    places = load_places(snap_dir)
    if places:
        print(f"# {len(places)} places: "
              + ", ".join(places[i]["name"] for i in sorted(places.keys())))
    stories_by_agent = load_stories_from_snapshots(snap_dir)
    if stories_by_agent:
        n_slots = sum(len(v) for v in stories_by_agent.values())
        print(f"# {len(stories_by_agent)} agents with {n_slots} story slots in snapshots")

    # Decay used at biography render time. Should match the simulation's
    # story_inherit_decay; reads from a sidecar if present, else default.
    decay_per_year = 0.92

    lives = index_lives(events)
    max_tick = max(e["tick"] for e in events)

    if all_mode:
        out_dir = run_dir / "lives"
        n = render_all(events, traits, lives, out_dir, places=places,
                       stories_by_agent=stories_by_agent,
                       decay_per_year=decay_per_year)
        print(f"# wrote {n} narratives to {out_dir}")
        if places:
            places_out = run_dir / "places"
            m = render_all_places(events, places, traits, lives, places_out,
                              stories_by_agent=stories_by_agent,
                              decay_per_year=decay_per_year)
            print(f"# wrote {m} place biographies to {places_out}")
        return

    if all_places_mode:
        if not places:
            sys.exit("no places found in snapshots — was places_enabled=1 set?")
        places_out = run_dir / "places"
        m = render_all_places(events, places, traits, lives, places_out,
                              stories_by_agent=stories_by_agent,
                              decay_per_year=decay_per_year)
        print(f"# wrote {m} place biographies to {places_out}")
        return

    if place_idx is not None:
        if not places:
            sys.exit("no places found in snapshots — was places_enabled=1 set?")
        if place_idx not in places:
            sys.exit(f"place index {place_idx} not found "
                     f"(valid: {sorted(places.keys())})")
        print(render_place(events, place_idx, places, traits, lives))
        return

    subject = select_subject(lives, max_tick, traits)
    if subject is None:
        sys.exit("no agent met the selection criteria — relax thresholds and rerun")
    print(f"# selected agent {subject}")
    print()

    print(render_life(events, subject, traits, lives, places=places,
                      stories_by_agent=stories_by_agent,
                      decay_per_year=decay_per_year))


if __name__ == "__main__":
    main()
