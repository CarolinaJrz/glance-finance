#include "drivers/touch_st77922.h"
#include <Arduino.h>
#include <Wire.h>
#include "app_config.h"

#define REG_FW_VERSION   0x0000
#define REG_MAX_X_H      0x0005  // max X (2 bytes), max Y (2 bytes), max touches (1 byte)
#define REG_MAX_TOUCHES  0x0009
#define REG_TOUCH_INFO   0x0010  // bit3: coordinates available
#define REG_REPORT_0     0x0014  // 7-byte report per touch
#define REPORT_BYTES     7
#define MAX_REPORTS      10

static bool read_reg(uint16_t reg, uint8_t *data, size_t len) {
  Wire.beginTransmission(TOUCH_I2C_ADDR);
  Wire.write(reg >> 8);
  Wire.write(reg & 0xFF);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((uint8_t)TOUCH_I2C_ADDR, (uint8_t)len) != len) return false;
  for (size_t i = 0; i < len; i++) data[i] = Wire.read();
  return true;
}

bool touch_init() {
  pinMode(TP_PIN_INT, INPUT);
  pinMode(TP_PIN_RST, OUTPUT);
  digitalWrite(TP_PIN_RST, LOW);
  delay(100);
  digitalWrite(TP_PIN_RST, HIGH);
  delay(100);

  uint8_t version;
  uint8_t info[5];
  if (!read_reg(REG_FW_VERSION, &version, 1) || !read_reg(REG_MAX_X_H, info, sizeof(info))) return false;
  Serial.printf("Touch: fw %u, max %ux%u, %u points\n", version, (info[0] << 8) | info[1],
                (info[2] << 8) | info[3], info[4]);
  return true;
}

bool touch_read(int16_t *x, int16_t *y) {
  uint8_t status;
  if (!read_reg(REG_TOUCH_INFO, &status, 1) || !(status & 0x08)) return false;

  uint8_t count;
  if (!read_reg(REG_MAX_TOUCHES, &count, 1) || count == 0) return false;
  if (count > MAX_REPORTS) count = MAX_REPORTS;

  uint8_t rep[MAX_REPORTS * REPORT_BYTES];
  if (!read_reg(REG_REPORT_0, rep, count * REPORT_BYTES)) return false;

  for (int i = 0; i < count; i++) {
    const uint8_t *r = &rep[i * REPORT_BYTES];
    if (!(r[0] & 0x80)) continue;  // not a valid point
    int16_t px = ((r[0] & 0x3F) << 8) | r[1];
    int16_t py = (r[2] << 8) | r[3];
    if (TOUCH_MIRROR_X) px = LCD_NATIVE_W - 1 - px;
    if (TOUCH_MIRROR_Y) py = LCD_NATIVE_H - 1 - py;
    *x = constrain(px, 0, LCD_NATIVE_W - 1);
    *y = constrain(py, 0, LCD_NATIVE_H - 1);
    return true;
  }
  return false;
}
