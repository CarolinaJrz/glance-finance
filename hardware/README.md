# Wallet Wellness: separate screen prototype

Status: prepared for a likely LCDwiki ES3C35P / Hosyond 3.5-inch 320×480 ESP32-S3, NOT tested or uploaded to the physical device. The photo and listing are a strong match, not proof that all units use the same pins/controller. Do not upload or reset the borrowed board until its owner confirms the existing work is safe and approves it.

This is a separate firmware project plus a laptop bridge. No changes to the web app or PNC workshop source are required. No real bank connection. Prototype for synthetic data only; do not use for personal financial data. No authentication or encrypted transport.

## Safe laptop-only test (does not contact the screen)

1. Start the existing Wallet Wellness web app in its usual terminal.
2. Open a second terminal, go to this extracted folder, and run `python3 bridge.py`.
3. It prints one compact JSON snapshot from `http://127.0.0.1:5000/state` and exits. This default mode does not open a serial port. If the server is not running, it gives an error.
4. Change a synthetic purchase in the web app and run again to compare. No real transaction happens.

The bridge intentionally sends only screen-relevant fields, not the budget or chatbot. For an actual device update, separate explicit serial options exist in `python3 bridge.py --help`; do not use those on the current dashboard firmware. A Python package, pyserial, is required for serial mode only. Start that stage with guidance after the board and source are protected.

## Firmware

`src/main.cpp` implements the compact overview and per-account deck; Previous/Next and left/right gestures are included. Last received data becomes OFFLINE after six seconds without an update. Account order is credit cards, cash/savings, retirement, investments, and loans. The display handles no connection itself; the laptop has to run both the app and bridge.

`platformio.ini` and `include/app_config.h` target portrait 320×480 using the likely board's pin map. The drivers under `src/drivers` are unmodified copies from [AndyGJorgensen's ES3C35P starter](https://github.com/AndyGJorgensen/hosyond-esp32-s3-3.5-touchscreen-starter), revision 5e0fc4a8299a0de4c07aa71719060cf3b7a527c9; see DRIVER_LICENSE.txt. Touch, orientation, rendering, USB serial, and startup remain unverified on this specific unit.

To compile only after setting up VS Code + PlatformIO: `pio run`. This builds firmware locally and does not flash it. Do **not** run an upload command yet. Bluetooth is not included; this version is a USB-first prototype.

## Preservation

The existing app and PNC files were not modified, and no board access was performed in creation. Hardware firmware can contain existing data or credentials; do not copy or disclose it without the owner's permission. Some devices prevent readout or use encryption, and a flash dump is not editable project source or guaranteed restorable. Ask the owner for their source and safe backup/restore process before touching firmware. If we later update project files, preserve each prior version and record why in the Discovery Log.
