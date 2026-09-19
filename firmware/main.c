/* roamer_pico — the fast loop.
 *
 * Owns motor PID, encoder counting, and the bumper/cliff/wheel-drop safety stop,
 * all independent of the Pi. Speaks the line protocol in docs/pico-protocol.md
 * over USB CDC (ttyACM0). The Pi only sends velocity targets and receives state.
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include "pico/stdlib.h"
#include "config.h"
#include "motor.h"
#include "encoder.h"
#include "sensors.h"

#define VERSION "0.1.1"

static sensors_state_t _sens;
static bool _picked_up = false;  /* real value comes from the IMU on the Pi */

static void send_telemetry(void) {
    uint32_t ts = (uint32_t)to_ms_since_boot(get_absolute_time());
    printf("TELEM %lu %ld %ld %.2f %.2f %u %d %d %d %d %d %d %d %d %d %d %d\n",
        (unsigned long)ts,
        (long)encoder_left(), (long)encoder_right(),
        motor_vel_left(), motor_vel_right(),
        (unsigned int)_sens.batt_mv, (int)_sens.batt_ma,
        (int)motor_estop_active(),
        (int)_sens.bump_l, (int)_sens.bump_r,
        (int)_sens.cliff_fl, (int)_sens.cliff_fr, (int)_sens.cliff_bl, (int)_sens.cliff_br,
        (int)_sens.wheel_l, (int)_sens.wheel_r, (int)_picked_up);
}

static void handle_line(char *line) {
    char cmd[16] = {0};
    float a = 0.0f, b = 0.0f;
    int n = sscanf(line, "%15s %f %f", cmd, &a, &b);

    if (strcmp(cmd, "PING") == 0) {
        printf("PONG %s %lu\n", VERSION,
               (unsigned long)to_ms_since_boot(get_absolute_time()));
    } else if (strcmp(cmd, "MV") == 0) {
        if (motor_estop_active()) { printf("ERR ESTOP\n"); return; }
        if (n < 3) { printf("ERR PARSE\n"); return; }
        motor_set_target(a, b);
        printf("OK\n");
    } else if (strcmp(cmd, "STOP") == 0 || strcmp(cmd, "BRAKE") == 0) {
        motor_set_target(0.0f, 0.0f);
        printf("OK\n");
    } else if (strcmp(cmd, "ESTOP") == 0) {
        motor_estop();
        printf("EVT ESTOP cmd\n");
    } else if (strcmp(cmd, "RESET") == 0) {
        motor_reset();
        printf("OK\n");
    } else if (strcmp(cmd, "CONFIG") == 0) {
        printf("ERR UNSUPPORTED\n");  /* runtime config lands during calibration */
    } else if (line[0] != '\0') {
        printf("ERR PARSE\n");
    }
}

int main(void) {
    stdio_init_all();
    sleep_ms(500);  /* let USB CDC enumerate before the banner */

    motor_init();
    encoder_init();
    sensors_init();
    printf("READY roamer_pico %s\n", VERSION);

    char line[128];
    int line_len = 0;
    uint32_t last_loop = (uint32_t)to_ms_since_boot(get_absolute_time());
    uint32_t last_telem = last_loop;
    sensors_state_t prev = {0};

    while (true) {
        /* 1. drain serial, process complete lines */
        int ch;
        while ((ch = getchar_timeout_us(0)) != PICO_ERROR_TIMEOUT) {
            if (ch == '\n' || ch == '\r') {
                line[line_len] = '\0';
                handle_line(line);
                line_len = 0;
            } else if (line_len < (int)sizeof(line) - 1) {
                line[line_len++] = (char)ch;
            }
        }

        uint32_t now = (uint32_t)to_ms_since_boot(get_absolute_time());

        /* 2. control loop at LOOP_HZ */
        if (now - last_loop >= 1000 / LOOP_HZ) {
            float dt = (now - last_loop) / 1000.0f;
            last_loop = now;
            motor_tick(dt);
        }

        /* 3. safety scan + telemetry at TELEM_HZ */
        if (now - last_telem >= 1000 / TELEM_HZ) {
            last_telem = now;
            sensors_scan(&_sens);

            if (_sens.estop_btn && !motor_estop_active()) {
                motor_estop();
                printf("EVT ESTOP auto\n");
            }

            bool moving = (fabsf(motor_vel_left()) > 1.0f) ||
                          (fabsf(motor_vel_right()) > 1.0f);
            bool safety = _sens.bump_l || _sens.bump_r ||
                          _sens.cliff_fl || _sens.cliff_fr ||
                          _sens.cliff_bl || _sens.cliff_br ||
                          _sens.wheel_l || _sens.wheel_r;
            if (safety && moving) {
                motor_set_target(0.0f, 0.0f);
            }
            if (_sens.bump_l && !prev.bump_l) printf("EVT BUMP l\n");
            if (_sens.bump_r && !prev.bump_r) printf("EVT BUMP r\n");
            if (_sens.cliff_fl && !prev.cliff_fl) printf("EVT CLIFF fl\n");
            if (_sens.cliff_fr && !prev.cliff_fr) printf("EVT CLIFF fr\n");
            if (_sens.cliff_bl && !prev.cliff_bl) printf("EVT CLIFF bl\n");
            if (_sens.cliff_br && !prev.cliff_br) printf("EVT CLIFF br\n");
            if (_sens.wheel_l && !prev.wheel_l) printf("EVT WHEEL_DROP l\n");
            if (_sens.wheel_r && !prev.wheel_r) printf("EVT WHEEL_DROP r\n");

            send_telemetry();
            prev = _sens;
        }
    }
}
