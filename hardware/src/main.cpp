#include <Arduino.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include <lvgl.h>
#include <math.h>
#include "app_config.h"
#include "drivers/lvgl_port.h"

// Only synthetic, local demo packets. No Wi-Fi, Bluetooth, SD, OTA, or AI.
static DynamicJsonDocument wallet(16384);
static String incoming, previous;
static unsigned long lastPacket = 0;
static bool hasData = false, wasFresh = false, discarding = false;
static int slide = 0;
static constexpr size_t MAX_LINE = 8000;
static constexpr unsigned long STALE_MS = 6000;
static const lv_color_t NAVY = lv_color_hex(0x102e55), WHITE = lv_color_hex(0xffffff),
                        SOFT = lv_color_hex(0xcfe1f3), INK = lv_color_hex(0x142c4c),
                        BLUE = lv_color_hex(0x2b5a86), MUTED = lv_color_hex(0x526f90);

static int pages() { return hasData ? 1 + (int)wallet["accounts"].size() : 1; }
static bool fresh() { return hasData && (unsigned long)(millis() - lastPacket) < STALE_MS; }
static String amount(JsonVariantConst v) {
  if (v.isNull()) return "--";
  double n = v.as<double>();
  if (!isfinite(n) || fabs(n) > 999999999) return "--";
  char buf[36]; snprintf(buf, sizeof(buf), "%s$%.2f", n < 0 ? "-" : "", fabs(n)); return String(buf);
}
static String decimalValue(JsonVariantConst v, const char *suffix, double scale=1) {
  if (v.isNull()) return "--";
  double n = v.as<double>() * scale;
  if (!isfinite(n)) return "--";
  char b[36]; snprintf(b, sizeof(b), "%.2f%s", n, suffix); return String(b);
}
static lv_obj_t *label(lv_obj_t *parent, const String &text, int x, int y, int w, lv_color_t color, const lv_font_t *font) {
  lv_obj_t *o = lv_label_create(parent);
  lv_label_set_text(o, text.c_str()); lv_obj_set_pos(o,x,y); lv_obj_set_width(o,w);
  lv_label_set_long_mode(o, LV_LABEL_LONG_DOT); lv_obj_set_style_text_color(o,color,0);
  lv_obj_set_style_text_font(o,font,0); return o;
}
static void row(lv_obj_t *card, int y, const char *key, const String &val) {
  label(card, key, 16, y, 125, MUTED, &lv_font_montserrat_14);
  lv_obj_t *v = label(card,val,142,y,120,INK,&lv_font_montserrat_14);
  lv_obj_set_style_text_align(v, LV_TEXT_ALIGN_RIGHT, 0);
}
static void render();
static void move(int delta) { slide=(slide+delta+pages())%pages(); render(); }
static void prev_cb(lv_event_t *) { move(-1); }
static void next_cb(lv_event_t *) { move(1); }
static void gesture_cb(lv_event_t *e) {
  lv_indev_t *in=lv_indev_active(); if (!in) return;
  lv_dir_t d=lv_indev_get_gesture_dir(in);
  if (d==LV_DIR_LEFT) move(1); else if (d==LV_DIR_RIGHT) move(-1);
}
static void button(lv_obj_t *parent, const char *text, int x, lv_event_cb_t cb) {
  lv_obj_t *b=lv_button_create(parent); lv_obj_set_pos(b,x,421); lv_obj_set_size(b,82,42);
  lv_obj_set_style_bg_color(b,BLUE,0); lv_obj_set_style_radius(b,8,0);
  lv_obj_set_style_shadow_width(b,0,0); lv_obj_add_event_cb(b,cb,LV_EVENT_CLICKED,nullptr);
  lv_obj_t *t=lv_label_create(b); lv_label_set_text(t,text); lv_obj_center(t);
}
static String typeName(const String &s) {
  if(s=="checking")return "Checking"; if(s=="savings")return "Savings";
  if(s=="cd")return "Certificate of deposit"; if(s=="ira")return "Retirement";
  if(s=="brokerage")return "Investment"; if(s=="auto_loan")return "Auto loan";
  if(s=="personal_loan")return "Personal loan"; if(s=="mortgage")return "Mortgage";
  return "Account";
}
static void render() {
  lv_obj_t *root=lv_screen_active(); lv_obj_clean(root);
  lv_obj_set_style_bg_color(root,NAVY,0); lv_obj_clear_flag(root, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(root, LV_OBJ_FLAG_CLICKABLE);
  // Root event is registered once in setup, not here.
  label(root,"WALLET WELLNESS",20,20,180,WHITE,&lv_font_montserrat_14);
  label(root,!hasData?"WAITING":fresh()?"DEMO / LIVE":"OFFLINE",205,20,100,SOFT,&lv_font_montserrat_14);
  if (!hasData) {
    label(root,"WALLET PREVIEW",20,65,280,SOFT,&lv_font_montserrat_14);
    label(root,"Waiting for demo",20,100,280,WHITE,&lv_font_montserrat_24);
    label(root,"Connect the local app",20,140,280,SOFT,&lv_font_montserrat_14);
    label(root,"Synthetic data only",20,380,280,SOFT,&lv_font_montserrat_14);
    return;
  }
  String name,kind,note,value; JsonObjectConst a;
  if(slide==0) {
    kind="OVERVIEW"; name="Checking balance"; value=amount(wallet["checking"]);
    note=fresh()?"Synthetic demo account":"Last known balance";
  } else {
    a=wallet["accounts"][slide-1].as<JsonObjectConst>();
    String t=a["type"] | ""; name=String(a["name"] | "Account");
    bool debt=t=="credit_card"||t=="auto_loan"||t=="personal_loan"||t=="mortgage";
    kind=t=="credit_card"?"CREDIT CARD":debt?"LOAN":"ACCOUNT";
    value=amount(a["balance"]); note=debt?"Balance owed":"Account balance";
  }
  label(root,kind,20,65,280,SOFT,&lv_font_montserrat_14);
  label(root,name,20,92,280,WHITE,&lv_font_montserrat_14);
  label(root,value,20,120,280,WHITE,&lv_font_montserrat_32);
  label(root,note,20,160,280,SOFT,&lv_font_montserrat_14);
  lv_obj_t *card=lv_obj_create(root); lv_obj_set_pos(card,20,197); lv_obj_set_size(card,280,162);
  lv_obj_set_style_bg_color(card,WHITE,0); lv_obj_set_style_border_width(card,0,0);
  lv_obj_set_style_radius(card,12,0); lv_obj_set_style_pad_all(card,0,0); lv_obj_clear_flag(card,LV_OBJ_FLAG_SCROLLABLE);
  if(slide==0) {
    label(card,"Financial snapshot",16,16,245,INK,&lv_font_montserrat_14);
    row(card,48,"Liquid cash",amount(wallet["liquid_cash"]));
    row(card,78,"Emergency fund",decimalValue(wallet["emergency_months"]," mo"));
    row(card,108,"Net worth",amount(wallet["net_worth"]));
    if (!wallet["last_purchase"].isNull()) row(card,132,"Last purchase",String("-")+amount(wallet["last_purchase"]["amount"]));
  } else {
    String t=a["type"] | "";
    label(card,t=="credit_card"?"Card details":"Account details",16,16,245,INK,&lv_font_montserrat_14);
    if(t=="credit_card") {
      double limit=a["credit_limit"] | 0.0, owed=a["balance"] | 0.0;
      row(card,48,"Available credit",limit>0?amount(JsonVariantConst()):String("--"));
      // Replace the placeholder via a small, safely formatted amount string.
      char tmp[40]; snprintf(tmp,sizeof(tmp),"$%.2f",limit>owed?limit-owed:0.0);
      lv_obj_t *last=lv_obj_get_child(card,2); lv_label_set_text(last,limit>0?tmp:"--");
      row(card,75,"Credit limit",amount(a["credit_limit"]));
      char pct[32]; if(limit>0) snprintf(pct,sizeof(pct),"%.1f%%",owed*100/limit); else snprintf(pct,sizeof(pct),"--");
      row(card,102,"Utilization",pct); row(card,129,"APR",decimalValue(a["apr"],"%",100));
    } else {
      row(card,48,"Type",typeName(t));
      if(!a["apy"].isNull()) row(card,78,"APY",decimalValue(a["apy"],"%",100));
      else if(!a["apr"].isNull()) row(card,78,"APR",decimalValue(a["apr"],"%",100));
      if(!a["monthly_payment"].isNull()) row(card,108,"Monthly payment",amount(a["monthly_payment"]));
    }
  }
  label(root,fresh()?"Synthetic data · Not financial advice":"Connection lost · values may be stale",20,375,280,SOFT,&lv_font_montserrat_14);
  button(root,"< Prev",16,prev_cb); button(root,"Next >",222,next_cb);
  char count[24]; snprintf(count,sizeof(count),"%d / %d",slide+1,pages());
  lv_obj_t *c=label(root,count,112,435,96,SOFT,&lv_font_montserrat_14);
  lv_obj_set_style_text_align(c,LV_TEXT_ALIGN_CENTER,0);
}
static void handleLine() {
  if (incoming.length()==0) return;
  if(incoming==previous && hasData) { lastPacket=millis(); return; }
  DynamicJsonDocument next(16384);
  if(deserializeJson(next,incoming) || next["version"]!=1 || !next["accounts"].is<JsonArray>() || next["accounts"].size()>40) return;
  wallet.clear(); wallet.set(next); previous=incoming; hasData=true; lastPacket=millis();
  if(slide>=pages()) slide=0; render();
}
void setup() {
  Serial.begin(115200); Wire.begin(I2C_PIN_SDA,I2C_PIN_SCL,I2C_BUS_HZ);
  lv_init(); lv_tick_set_cb([]()->uint32_t{return millis();});
  if(!lvgl_display_init()) { Serial.println("display init failed"); return; }
  if(!lvgl_touch_init()) Serial.println("touch init failed");
  lv_obj_add_event_cb(lv_screen_active(),gesture_cb,LV_EVENT_GESTURE,nullptr);
  render();
}
void loop() {
  while(Serial.available()) {
    char c=(char)Serial.read();
    if(c=='\n') { if(!discarding) handleLine(); incoming=""; discarding=false; }
    else if(!discarding && c!='\r') { if(incoming.length()<MAX_LINE) incoming+=c; else { incoming=""; discarding=true; } }
  }
  bool now=fresh(); if(now!=wasFresh) { wasFresh=now; if(hasData) render(); }
  lv_timer_handler(); delay(5);
}
