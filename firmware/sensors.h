#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    bool bump_l, bump_r;
    bool cliff_fl, cliff_fr, cliff_bl, cliff_br;
    bool wheel_l, wheel_r;
    bool estop_btn;
    uint16_t batt_mv;
    int16_t batt_ma;
} sensors_state_t;

void sensors_init(void);
void sensors_scan(sensors_state_t *out);
