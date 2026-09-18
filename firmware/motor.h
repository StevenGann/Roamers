#pragma once
#include <stdbool.h>

void motor_init(void);
void motor_set_target(float left_cm_s, float right_cm_s);
void motor_tick(float dt_s);
void motor_estop(void);
void motor_reset(void);
bool motor_estop_active(void);
float motor_vel_left(void);   /* cm/s */
float motor_vel_right(void);
