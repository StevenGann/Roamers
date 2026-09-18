/* Safety + battery sensors: bumpers, cliff (IR), wheel-drop, estop button,
 * battery voltage/current ADC. All active-low with internal pull-ups.
 */
#include "sensors.h"
#include "config.h"
#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include "hardware/adc.h"

static const uint _pins[] = {
    PIN_BUMP_L, PIN_BUMP_R,
    PIN_CLIFF_FL, PIN_CLIFF_FR, PIN_CLIFF_BL, PIN_CLIFF_BR,
    PIN_WHEEL_L, PIN_WHEEL_R,
    PIN_ESTOP,
};

void sensors_init(void) {
    for (size_t i = 0; i < sizeof(_pins) / sizeof(_pins[0]); i++) {
        gpio_init(_pins[i]);
        gpio_set_dir(_pins[i], GPIO_IN);
        gpio_pull_up(_pins[i]);
    }
    adc_init();
    adc_gpio_init(PIN_BATT_V);
    adc_gpio_init(PIN_BATT_I);
}

void sensors_scan(sensors_state_t *s) {
    s->bump_l    = !gpio_get(PIN_BUMP_L);
    s->bump_r    = !gpio_get(PIN_BUMP_R);
    s->cliff_fl  = !gpio_get(PIN_CLIFF_FL);
    s->cliff_fr  = !gpio_get(PIN_CLIFF_FR);
    s->cliff_bl  = !gpio_get(PIN_CLIFF_BL);
    s->cliff_br  = !gpio_get(PIN_CLIFF_BR);
    s->wheel_l   = !gpio_get(PIN_WHEEL_L);
    s->wheel_r   = !gpio_get(PIN_WHEEL_R);
    s->estop_btn = !gpio_get(PIN_ESTOP);

    adc_select_input(PIN_BATT_V - 26);
    s->batt_mv = (uint16_t)((float)adc_read() / 4095.0f * 3.3f * BATTERY_DIVIDER * 1000.0f);

    adc_select_input(PIN_BATT_I - 26);
    s->batt_ma = (int16_t)((float)adc_read() / 4095.0f * 3.3f * 1000.0f / BATTERY_SHUNT_MV_PER_A);
}
