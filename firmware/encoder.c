/* Quadrature wheel encoders — 2x decode on the A-channel edges via GPIO IRQ.
 *
 * Correct for robot-wheel rates (hundreds of counts/sec); the RP2350 handles
 * the IRQ load trivially. If we ever need 4x decode or much higher rates,
 * switch to PIO (see pico-examples pio/quadrature_encoder).
 */
#include "encoder.h"
#include "config.h"
#include "pico/stdlib.h"
#include "hardware/gpio.h"

static volatile int32_t _enc_l = 0;
static volatile int32_t _enc_r = 0;

static void enc_irq(uint gpio, uint32_t events) {
    if (gpio == PIN_ENC_L_A) {
        bool a = gpio_get(PIN_ENC_L_A);
        bool b = gpio_get(PIN_ENC_L_B);
        _enc_l += (a == b) ? +1 : -1;
    } else if (gpio == PIN_ENC_R_A) {
        bool a = gpio_get(PIN_ENC_R_A);
        bool b = gpio_get(PIN_ENC_R_B);
        _enc_r += (a == b) ? +1 : -1;
    }
}

void encoder_init(void) {
    gpio_init(PIN_ENC_L_A); gpio_set_dir(PIN_ENC_L_A, GPIO_IN); gpio_pull_up(PIN_ENC_L_A);
    gpio_init(PIN_ENC_L_B); gpio_set_dir(PIN_ENC_L_B, GPIO_IN); gpio_pull_up(PIN_ENC_L_B);
    gpio_init(PIN_ENC_R_A); gpio_set_dir(PIN_ENC_R_A, GPIO_IN); gpio_pull_up(PIN_ENC_R_A);
    gpio_init(PIN_ENC_R_B); gpio_set_dir(PIN_ENC_R_B, GPIO_IN); gpio_pull_up(PIN_ENC_R_B);

    gpio_set_irq_enabled_with_callback(PIN_ENC_L_A,
        GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true, enc_irq);
    gpio_set_irq_enabled(PIN_ENC_R_A,
        GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true);
}

int32_t encoder_left(void)  { return _enc_l; }
int32_t encoder_right(void) { return _enc_r; }
