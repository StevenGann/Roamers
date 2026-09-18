/* roamer_pico config — pin map and constants.
 *
 * PLACEHOLDERS: these pin numbers are sensible defaults until the chassis is
 * wired. Adjust here (and only here) once the H-bridge, encoders, and sensors
 * are mounted. All pins are within RP2350A's GP0-GP15 + GP26-GP29 (avoiding
 * GP16=WS2812 and GP23=SMPS).
 */
#pragma once

/* --- motors: 2× H-bridge, 2 PWM pins each (A/B) --- */
#define PIN_MOT_L_A   0
#define PIN_MOT_L_B   1
#define PIN_MOT_R_A   2
#define PIN_MOT_R_B   3

/* --- wheel encoders: quadrature, 2 pins each (A/B) --- */
#define PIN_ENC_L_A   4
#define PIN_ENC_L_B   5
#define PIN_ENC_R_A   6
#define PIN_ENC_R_B   7

/* --- safety sensors (active-low, internal pull-up) --- */
#define PIN_BUMP_L    8
#define PIN_BUMP_R    9
#define PIN_CLIFF_FL  10
#define PIN_CLIFF_FR  11
#define PIN_CLIFF_BL  12
#define PIN_CLIFF_BR  13
#define PIN_WHEEL_L   14
#define PIN_WHEEL_R   15

/* --- physical estop button (active-low) --- */
#define PIN_ESTOP     26

/* --- battery: ADC pins (voltage divider + current shunt) --- */
#define PIN_BATT_V    28
#define PIN_BATT_I    29

/* --- odometry / control constants (calibrate on chassis) --- */
#define ENC_CPR          1920        /* encoder counts per wheel rev (4x decode) */
#define WHEEL_DIAM_MM    65.0f
#define TRACK_MM         150.0f
#define BATTERY_DIVIDER  5.7f        /* V_batt = V_adc * divider */
#define BATTERY_SHUNT_MV_PER_A 100.0f  /* mV per amp across the shunt */

/* --- control loop --- */
#define PWM_WRAP         1000        /* PWM resolution 0..1000 */
#define LOOP_HZ          100         /* PID / motor tick rate */
#define TELEM_HZ         20          /* telemetry line rate */
#define MAX_VELOCITY_CM_S 25.0f      /* feedforward: full duty = this speed */
#define PID_KP           0.5f
#define PID_KI           0.1f
#define PID_KD           0.0f
#define MAX_DUTY         1.0f        /* max PWM fraction */
