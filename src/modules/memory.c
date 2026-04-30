#include "modules/memory.h"

#include "core/world.h"
#include "modules/agents.h"
#include "output/event_log.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

ECS_COMPONENT_DECLARE(Stories);

#define TICKS_PER_YEAR 365.0f

void MemoryModuleImport(ecs_world_t *world) {
    ECS_MODULE(world, MemoryModule);
    ECS_COMPONENT_DEFINE(world, Stories);
}

/* Continuous-decay-from-origin: a story's fidelity at any moment depends
   only on the gap between now and origin_tick, not on transmission path.
   Two holders of the same story at the same tick see the same fidelity. */
float memory_fidelity_now(const Story *s, int current_tick,
                          float decay_per_year) {
    int dt = current_tick - s->origin_tick;
    if (dt <= 0) return 1.0f;
    if (decay_per_year <= 0.0f) return 0.0f;
    if (decay_per_year >= 1.0f) return 1.0f;
    float years = (float)dt / TICKS_PER_YEAR;
    return powf(decay_per_year, years);
}

/* Eviction priority. Higher priority = more durable. High-magnitude
   stories stick longer than recent-but-trivial ones, even though their
   fidelity decays at the same rate; magnitude is the "this mattered"
   anchor. */
static float story_priority(const Story *s, int now, float decay) {
    return memory_fidelity_now(s, now, decay) + s->origin_magnitude;
}

/* Add `s` to `inv`. If `inv` is full, evict the lowest-priority existing
   slot — but only if the new slot's priority is higher. Otherwise discard
   the new story. (A story whose priority can't beat any existing one is
   too weak to displace anything.) */
static void inventory_add(Stories *inv, const Story *s,
                          int now, float decay) {
    if (inv->n < STORY_CAPACITY) {
        inv->slots[inv->n++] = *s;
        return;
    }
    int   worst_idx = 0;
    float worst_pri = story_priority(&inv->slots[0], now, decay);
    for (int i = 1; i < STORY_CAPACITY; i++) {
        float p = story_priority(&inv->slots[i], now, decay);
        if (p < worst_pri) { worst_pri = p; worst_idx = i; }
    }
    float new_pri = story_priority(s, now, decay);
    if (new_pri > worst_pri) {
        inv->slots[worst_idx] = *s;
    }
    /* else: discarded. The new story is too weak to displace anything. */
}

void memory_record_witness(ecs_world_t *world, const Config *cfg,
                           ecs_entity_t agent,
                           int origin_tick, int origin_kind,
                           int origin_place, float origin_magnitude) {
    if (!cfg->memory_enabled) return;
    if (origin_magnitude < 0.0f) origin_magnitude = 0.0f;
    if (origin_magnitude > 1.0f) origin_magnitude = 1.0f;

    Stories inv;
    const Stories *cur = ecs_get(world, agent, Stories);
    if (cur) inv = *cur;
    else     memset(&inv, 0, sizeof inv);

    Story s = {0};
    s.origin_tick               = origin_tick;
    s.origin_kind               = (uint8_t)origin_kind;
    s.origin_place              = (int8_t)origin_place;
    s.was_direct_witness        = 1;
    s.source_was_origin_witness = 1;  /* the holder IS the origin */
    s.origin_magnitude          = origin_magnitude;
    s.source_id                 = 0;

    SimState *st = world_state(world);
    inventory_add(&inv, &s, st->current_tick, cfg->story_inherit_decay);
    ecs_set_ptr(world, agent, Stories, &inv);
}

void memory_inherit_from(ecs_world_t *world, const Config *cfg,
                         ecs_entity_t heir, ecs_entity_t ancestor) {
    if (!cfg->memory_enabled) return;
    if (!ancestor) return;

    const Stories *src = ecs_get(world, ancestor, Stories);
    if (!src || src->n == 0) return;

    SimState *st = world_state(world);
    int   now    = st->current_tick;
    float decay  = cfg->story_inherit_decay;
    float min_fid = cfg->story_min_fidelity;

    Stories inv;
    const Stories *cur = ecs_get(world, heir, Stories);
    if (cur) inv = *cur;
    else     memset(&inv, 0, sizeof inv);

    for (int i = 0; i < src->n; i++) {
        const Story *src_slot = &src->slots[i];
        float fid = memory_fidelity_now(src_slot, now, decay);
        /* Drop stories whose continuous-decay-from-origin fidelity has
           fallen below the floor. They're not transmitted further — that's
           how stories die. */
        if (fid < min_fid) continue;

        Story new_slot = *src_slot;
        new_slot.was_direct_witness        = 0;
        /* Provenance: was the immediate source the original witness, or
           themselves a relay? This is the one bit that lets the chronicler
           attribute "inherited from Selka" only when Selka was the witness,
           and "the story had reached Selka from before her own time"
           otherwise. */
        new_slot.source_was_origin_witness = src_slot->was_direct_witness;
        new_slot.source_id                 = ancestor;
        /* origin_tick / kind / place / magnitude unchanged. */

        inventory_add(&inv, &new_slot, now, decay);

        /* Log: a=heir, b=ancestor, value=fidelity_at_inheritance,
           place_id=origin_place. Lets biography readers reconstruct the
           heir's inventory by replaying. */
        event_log_write(now, "story_inherited",
                        heir, ancestor, fid, src_slot->origin_place);
    }

    ecs_set_ptr(world, heir, Stories, &inv);
}
