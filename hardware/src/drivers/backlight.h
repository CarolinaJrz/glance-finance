#pragma once
#include <stdint.h>

// LCD backlight brightness: PWM on LCD_PIN_BL (it drives a MOSFET, so it dims smoothly).
void backlight_begin();          // starts at BACKLIGHT_DEFAULT_PCT
void backlight_set(uint8_t pct); // 0..100 (0 = off)
uint8_t backlight_get();
