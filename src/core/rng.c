#include "core/rng.h"

static uint64_t g_state = 0x853c49e6748fea9bULL;
static uint64_t g_inc   = 0xda3e39cb94b95bdbULL;

void rng_seed(uint64_t seed) {
    g_state = 0u;
    g_inc = (seed << 1u) | 1u;
    rng_u32();
    g_state += 0x853c49e6748fea9bULL ^ seed;
    rng_u32();
}

uint32_t rng_u32(void) {
    uint64_t oldstate = g_state;
    g_state = oldstate * 6364136223846793005ULL + g_inc;
    uint32_t xorshifted = (uint32_t)(((oldstate >> 18u) ^ oldstate) >> 27u);
    uint32_t rot = (uint32_t)(oldstate >> 59u);
    return (xorshifted >> rot) | (xorshifted << ((-rot) & 31));
}

float rng_float(void) {
    return (float)(rng_u32() >> 8) * (1.0f / 16777216.0f);
}

float rng_range_f(float min, float max) {
    return min + (max - min) * rng_float();
}

int rng_range_i(int min, int max_inclusive) {
    if (max_inclusive <= min) return min;
    uint32_t span = (uint32_t)(max_inclusive - min + 1);
    return min + (int)(rng_u32() % span);
}

/* ---- sub-stream API ------------------------------------------------------
   Mirrors the global init/advance pattern but stores state in caller-owned
   memory. The seeding routine matches rng_seed: derive `inc` from the seed
   (XORed with the per-stream id so different modules get different streams),
   warm the state with two draws, then mix the seed into state. */

void rng_stream_init(RngStream *s, uint64_t seed, uint64_t stream_id) {
    s->state = 0u;
    /* `inc` must be odd; XOR with stream_id then force low bit. */
    s->inc = ((seed ^ stream_id) << 1u) | 1u;
    rng_stream_u32(s);
    s->state += 0x853c49e6748fea9bULL ^ seed ^ stream_id;
    rng_stream_u32(s);
}

uint32_t rng_stream_u32(RngStream *s) {
    uint64_t oldstate = s->state;
    s->state = oldstate * 6364136223846793005ULL + s->inc;
    uint32_t xorshifted = (uint32_t)(((oldstate >> 18u) ^ oldstate) >> 27u);
    uint32_t rot = (uint32_t)(oldstate >> 59u);
    return (xorshifted >> rot) | (xorshifted << ((-rot) & 31));
}

float rng_stream_float(RngStream *s) {
    return (float)(rng_stream_u32(s) >> 8) * (1.0f / 16777216.0f);
}

float rng_stream_range_f(RngStream *s, float min, float max) {
    return min + (max - min) * rng_stream_float(s);
}

int rng_stream_range_i(RngStream *s, int min, int max_inclusive) {
    if (max_inclusive <= min) return min;
    uint32_t span = (uint32_t)(max_inclusive - min + 1);
    return min + (int)(rng_stream_u32(s) % span);
}
