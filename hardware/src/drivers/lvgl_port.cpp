#include "drivers/lvgl_port.h"
#include <Arduino.h>
#include <lvgl.h>
#include <esp_heap_caps.h>
#include "app_config.h"
#include "drivers/lcd_st77922.h"
#include "drivers/touch_st77922.h"
#include "drivers/backlight.h"

static uint16_t *s_rot_buf;  // PSRAM scratch for software rotation

// ST77922 needs window column start/width in multiples of 4: grow every invalidated area to 4-px alignment.
// Both axes are rounded because rotation maps logical y onto panel columns.
static void rounder_cb(lv_event_t *e) {
  lv_area_t *a = (lv_area_t *)lv_event_get_param(e);
  a->x1 &= ~3;
  a->y1 &= ~3;
  a->x2 |= 3;
  a->y2 |= 3;
}

// Rotate to the panel's native portrait layout, then push over QSPI
static void flush_cb(lv_display_t *disp, const lv_area_t *area, uint8_t *px_map) {
  const lv_display_rotation_t rot = lv_display_get_rotation(disp);
  const int32_t w = lv_area_get_width(area);
  const int32_t h = lv_area_get_height(area);

  if (rot == LV_DISPLAY_ROTATION_0) {
    lcd_draw(area->x1, area->y1, area->x2, area->y2, (const uint16_t *)px_map, w);
  } else {
    lv_area_t native = *area;
    lv_display_rotate_area(disp, &native);
    const int32_t nw = lv_area_get_width(&native);
    lv_draw_sw_rotate(px_map, s_rot_buf, w, h, w * 2, nw * 2, rot, LV_COLOR_FORMAT_RGB565);
    lcd_draw(native.x1, native.y1, native.x2, native.y2, s_rot_buf, nw);
  }
  lv_display_flush_ready(disp);
}

bool lvgl_display_init() {
  backlight_begin();
  if (!lcd_init()) return false;

  // Full-screen draw buffer in PSRAM so a flush is never split off 4-px alignment
  const size_t buf_bytes = LCD_NATIVE_W * LCD_NATIVE_H * 2;
  void *buf = heap_caps_malloc(buf_bytes, MALLOC_CAP_SPIRAM);
  s_rot_buf = (uint16_t *)heap_caps_malloc(buf_bytes, MALLOC_CAP_SPIRAM);
  if (!buf || !s_rot_buf) return false;

  lv_display_t *disp = lv_display_create(LCD_NATIVE_W, LCD_NATIVE_H);
  lv_display_set_color_format(disp, LV_COLOR_FORMAT_RGB565);
  lv_display_set_rotation(disp, (lv_display_rotation_t)LCD_ROTATION);
  lv_display_set_buffers(disp, buf, NULL, buf_bytes, LV_DISPLAY_RENDER_MODE_PARTIAL);
  lv_display_set_flush_cb(disp, flush_cb);
  lv_display_add_event_cb(disp, rounder_cb, LV_EVENT_INVALIDATE_AREA, NULL);

  return true;
}

// Touch points are native portrait; LVGL rotates them to match the display rotation
static void touch_read_cb(lv_indev_t *indev, lv_indev_data_t *data) {
  int16_t x, y;
  if (touch_read(&x, &y)) {
    data->point.x = x;
    data->point.y = y;
    data->state = LV_INDEV_STATE_PRESSED;
  } else {
    data->state = LV_INDEV_STATE_RELEASED;
  }
}

bool lvgl_touch_init() {
  if (!touch_init()) return false;
  lv_indev_t *indev = lv_indev_create();
  lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
  lv_indev_set_read_cb(indev, touch_read_cb);
  return true;
}
