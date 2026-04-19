#ifndef RELATIONSHIPS_CORE_RNG_H
#define RELATIONSHIPS_CORE_RNG_H

#include <stdint.h>

void rng_seed(uint64_t seed);
uint32_t rng_u32(void);
float rng_float(void);
float rng_range_f(float min, float max);
int rng_range_i(int min, int max_inclusive);

#endif
