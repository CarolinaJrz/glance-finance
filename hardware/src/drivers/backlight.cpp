#include "drivers/backlight.h"
#include <Arduino.h>
#include "app_config.h"

static uint8_t s_pct;

void backlight_begin() {
  ledcSetup(BACKLIGHT_PWM_CHANNEL, BACKLIGHT_PWM_FREQ, 8);
  ledcAttachPin(LCD_PIN_BL, BACKLIGHT_PWM_CHANNEL);
  backlight_set(BACKLIGHT_DEFAULT_PCT);
}

void backlight_set(uint8_t pct) {
  s_pct = min<uint8_t>(pct, 100);
  ledcWrite(BACKLIGHT_PWM_CHANNEL, s_pct * 255 / 100);
}

uint8_t backlight_get() { return s_pct; }
