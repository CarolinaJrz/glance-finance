// LVGL heap in PSRAM (LV_USE_STDLIB_MALLOC = LV_STDLIB_CUSTOM in platformio.ini).
// With the C library malloc, every allocation under 4 KB lands in internal RAM (the core's
// SPIRAM_MALLOC_ALWAYSINTERNAL), and LVGL's many small objects then starve WiFi/TLS/SD of
// internal memory (the TLS handshake fails with "esp-sha: Failed to allocate buf memory").
#include <lvgl.h>
#include <esp_heap_caps.h>

#if LV_USE_STDLIB_MALLOC == LV_STDLIB_CUSTOM

static const uint32_t CAPS = MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT;

extern "C" {

void lv_mem_init(void) {}
void lv_mem_deinit(void) {}

lv_mem_pool_t lv_mem_add_pool(void *mem, size_t bytes) {
  LV_UNUSED(mem);
  LV_UNUSED(bytes);
  return NULL;
}

void lv_mem_remove_pool(lv_mem_pool_t pool) { LV_UNUSED(pool); }

void *lv_malloc_core(size_t size) {
  void *p = heap_caps_malloc(size, CAPS);
  return p ? p : malloc(size);  // PSRAM full: fall back to internal
}

void *lv_realloc_core(void *p, size_t new_size) {
  void *q = heap_caps_realloc(p, new_size, CAPS);
  return q ? q : realloc(p, new_size);
}

void lv_free_core(void *p) { heap_caps_free(p); }

void lv_mem_monitor_core(lv_mem_monitor_t *mon_p) { LV_UNUSED(mon_p); }

lv_result_t lv_mem_test_core(void) { return LV_RESULT_OK; }

}  // extern "C"

#endif
