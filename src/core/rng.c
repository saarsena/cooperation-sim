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
