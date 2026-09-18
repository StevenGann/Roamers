#pragma once
#include <stdint.h>

void encoder_init(void);
int32_t encoder_left(void);   /* cumulative count */
int32_t encoder_right(void);
