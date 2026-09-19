/* Differential-drive motor control: PWM + velocity PID (feedforward + PI).
 * The fast loop that owns the wheels — never touches the Pi for the control
 * itself, only receives velocity targets and reports measured velocity.
 */
#include "motor.h"
#include "encoder.h"
#include "config.h"
#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/gpio.h"
#include "hardware/clocks.h"
#include <math.h>

static uint _slice[4];
static uint _chan[4];
static const uint _pin[4] = {PIN_MOT_L_A, PIN_MOT_L_B, PIN_MOT_R_A, PIN_MOT_R_B};

static bool _estop = false;
static float _target_l = 0.0f, _target_r = 0.0f;
static float _vel_l = 0.0f, _vel_r = 0.0f;
static float _integ_l = 0.0f, _integ_r = 0.0f;
static float _prev_err_l = 0.0f, _prev_err_r = 0.0f;
static int32_t _prev_enc_l = 0, _prev_enc_r = 0;

#define WHEEL_CIRC_CM ((float)(3.14159265358979f * WHEEL_DIAM_MM / 10.0f))

/* idx: 0 = left motor, 1 = right motor. duty in [-1, 1]. */
static void _drive(int idx, float duty) {
    if (duty > MAX_DUTY) duty = MAX_DUTY;
    if (duty < -MAX_DUTY) duty = -MAX_DUTY;
    int a = idx * 2, b = idx * 2 + 1;
    if (duty >= 0.0f) {
        pwm_set_chan_level(_slice[a], _chan[a], (uint16_t)(duty * PWM_WRAP));
        pwm_set_chan_level(_slice[b], _chan[b], 0);
    } else {
        pwm_set_chan_level(_slice[a], _chan[a], 0);
        pwm_set_chan_level(_slice[b], _chan[b], (uint16_t)(-duty * PWM_WRAP));
    }
}

void motor_init(void) {
    for (int i = 0; i < 4; i++) {
        gpio_set_function(_pin[i], GPIO_FUNC_PWM);
        _slice[i] = pwm_gpio_to_slice_num(_pin[i]);
        _chan[i] = pwm_gpio_to_channel(_pin[i]);
        pwm_set_wrap(_slice[i], PWM_WRAP);
        float div = (float)clock_get_hz(clk_sys) / ((float)PWM_HZ * (float)PWM_WRAP);
        pwm_set_clkdiv(_slice[i], div);
        pwm_set_chan_level(_slice[i], _chan[i], 0);
        pwm_set_enabled(_slice[i], true);
    }
    _prev_enc_l = encoder_left();
    _prev_enc_r = encoder_right();
}

void motor_set_target(float l, float r) {
    _target_l = l;
    _target_r = r;
}

void motor_tick(float dt_s) {
    int32_t el = encoder_left(), er = encoder_right();
    int32_t dl = el - _prev_enc_l, dr = er - _prev_enc_r;
    _prev_enc_l = el; _prev_enc_r = er;
    if (dt_s <= 0.0f) dt_s = 0.001f;
    _vel_l = (float)dl / (float)ENC_CPR * WHEEL_CIRC_CM / dt_s;
    _vel_r = (float)dr / (float)ENC_CPR * WHEEL_CIRC_CM / dt_s;

    if (_estop) {
        _drive(0, 0.0f); _drive(1, 0.0f);
        _integ_l = _integ_r = 0.0f;
        return;
    }

    float err_l = _target_l - _vel_l;
    float err_r = _target_r - _vel_r;
    _integ_l += err_l * dt_s;
    _integ_r += err_r * dt_s;
    float der_l = (err_l - _prev_err_l) / dt_s;
    float der_r = (err_r - _prev_err_r) / dt_s;
    _prev_err_l = err_l; _prev_err_r = err_r;

    float ff_l = _target_l / MAX_VELOCITY_CM_S;
    float ff_r = _target_r / MAX_VELOCITY_CM_S;
    float out_l = ff_l + (PID_KP * err_l + PID_KI * _integ_l + PID_KD * der_l);
    float out_r = ff_r + (PID_KP * err_r + PID_KI * _integ_r + PID_KD * der_r);

    _drive(0, out_l);
    _drive(1, out_r);
}

void motor_estop(void) { _estop = true; _target_l = _target_r = 0.0f; }
void motor_reset(void) { _estop = false; _integ_l = _integ_r = 0.0f; }
bool motor_estop_active(void) { return _estop; }
float motor_vel_left(void)  { return _vel_l; }
float motor_vel_right(void) { return _vel_r; }
