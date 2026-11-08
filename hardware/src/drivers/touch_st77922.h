#pragma once
#include <stdint.h>

// Touch side of the Sitronix ST77922 TDDI over I2C (protocol from the vendor LVGL demo).
// Registers are 16-bit big-endian. Coordinates are in the panel's native portrait orientation.

bool touch_init();  // needs the shared I2C bus (Wire) started                       // reset the touch controller and check it answers on I2C
bool touch_read(int16_t *x, int16_t *y); // first valid touch point; false when not touched
