#pragma once

// LVGL port for the ES3C35P board: ST77922 display + touch.

// Registers the ST77922 panel as the LVGL display (rotation, 4-px alignment, flush).
// Call after lv_init(). Returns false if the panel or buffers could not be set up.
bool lvgl_display_init();

// Registers the ST77922 touch controller as an LVGL pointer. Call after lvgl_display_init().
bool lvgl_touch_init();
