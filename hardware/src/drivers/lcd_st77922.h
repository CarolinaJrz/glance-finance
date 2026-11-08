#pragma once
#include <stdint.h>

// Minimal Sitronix ST77922 QSPI driver (ESP-IDF spi_master, Arduino core 2.x).
// Commands:  opcode 0x02, 24-bit address 0x00 <cmd> 00, params on 1 line.
// Pixels:    opcode 0x32, address 0x00 3C 00, RGB565 big-endian on 4 lines.
// Coordinates are in the panel's native portrait orientation (LCD_NATIVE_W x LCD_NATIVE_H).
// The column start and width of every window must be a multiple of 4.

bool lcd_init();  // bus + vendor panel init, returns false on SPI error
// Draw a native-coordinate area (inclusive). px is little-endian RGB565, row stride in pixels.
void lcd_draw(int x1, int y1, int x2, int y2, const uint16_t *px, int stride_px);
