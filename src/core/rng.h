#ifndef RELATIONSHIPS_CORE_RNG_H
#define RELATIONSHIPS_CORE_RNG_H

#include <stdint.h>

/* Global PCG32 state used by the legacy modules (agents, ventures,
   relationships). Existing API unchanged. */
void rng_seed(uint64_t seed);
uint32_t rng_u32(void);
float rng_float(void);
float rng_range_f(float min, float max);
int rng_range_i(int min, int max_inclusive);

/* Independent PCG32 sub-stream. Each new witness-world module owns one and
   draws from it via the rng_stream_* functions, so flipping a module on or
   off does not perturb the trajectory of other modules at the same seed. */
typedef struct RngStream {
    uint64_t state;
    uint64_t inc;
} RngStream;

void     rng_stream_init(RngStream *s, uint64_t seed, uint64_t stream_id);
uint32_t rng_stream_u32(RngStream *s);
float    rng_stream_float(RngStream *s);
float    rng_stream_range_f(RngStream *s, float min, float max);
int      rng_stream_range_i(RngStream *s, int min, int max_inclusive);

#endif
