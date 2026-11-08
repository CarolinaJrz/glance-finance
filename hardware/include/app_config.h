#pragma once
// ES3C35P assumptions copied from upstream pin map. Verify before use.
#define LCD_NATIVE_W 320
#define LCD_NATIVE_H 480
#define LCD_ROTATION 0
#define LCD_MADCTL 0x00
#define LCD_SPI_HZ 40000000
#define LCD_CHUNK_BYTES 32768
#define LCD_PIN_BL 41
#define BACKLIGHT_DEFAULT_PCT 100
#define BACKLIGHT_MIN_PCT 5
#define BACKLIGHT_PWM_CHANNEL 7
#define BACKLIGHT_PWM_FREQ 5000
#define LCD_PIN_CS 10
#define LCD_PIN_SCK 12
#define LCD_PIN_D0 11
#define LCD_PIN_D1 13
#define LCD_PIN_D2 14
#define LCD_PIN_D3 9
#define LCD_PIN_TE 42
#define I2C_PIN_SDA 38
#define I2C_PIN_SCL 39
#define I2C_BUS_HZ 400000
#define TP_PIN_INT 47
#define TP_PIN_RST 48
#define TOUCH_I2C_ADDR 0x55
#define TOUCH_MIRROR_X 0
#define TOUCH_MIRROR_Y 0
