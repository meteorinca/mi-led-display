# MI Matrix Display - Complete Instructions

## Overview

This project controls the **Merkury Innovations 16x16 LED Matrix Display** via Bluetooth from a Raspberry Pi. The display communicates over Bluetooth Low Energy (BLE).

---

## Quick Start (Step by Step)

### Step 1: Install Dependencies

```bash
cd mi-led-display
pip install -r requirements.txt
```

### Step 2: Find Your Display's MAC Address

Power on your MI Matrix Display, then run:

```bash
python bt_scanner.py
```

You'll see output like:
```
=== MI MATRIX DISPLAYS FOUND ===
  Name: MI Matrix Display
  MAC Address: AA:BB:CC:DD:EE:FF    <-- Copy this!
  Signal (RSSI): -45 dBm
```

**Save that MAC address!** You'll need it for the next steps.

### Step 3: Start the API Server

```bash
python api_server.py
```

Server runs at `http://localhost:5000`

### Step 4: Connect to Your Display

Replace `AA:BB:CC:DD:EE:FF` with YOUR MAC address:

```bash
curl -X POST http://localhost:5000/displays/AA:BB:CC:DD:EE:FF/connect
```

### Step 5: Draw Something!

**Set a single red pixel at position (8,8):**
```bash
curl -X POST http://localhost:5000/displays/AA:BB:CC:DD:EE:FF/pixel \
  -H "Content-Type: application/json" \
  -d '{"x": 8, "y": 8, "r": 255, "g": 0, "b": 0}'
```

**Fill the entire display with green:**
```bash
curl -X POST http://localhost:5000/displays/AA:BB:CC:DD:EE:FF/fill \
  -H "Content-Type: application/json" \
  -d '{"r": 0, "g": 255, "b": 0}'
```

**Clear the display (all black):**
```bash
curl -X POST http://localhost:5000/displays/AA:BB:CC:DD:EE:FF/clear
```

---

## File Structure Explained

| File | What It Does |
|------|--------------|
| `bt_scanner.py` | **Start here!** Finds display MAC addresses |
| `api_server.py` | REST API server - run this to control displays via HTTP |
| `rpi_bluetooth_manager.py` | Low-level BLE connection handling (used by api_server) |
| `matrix_controller.py` | High-level pixel/image commands (used by api_server) |
| `display_registry.py` | Tracks multiple displays (used internally) |
| `config_manager.py` | Saves settings (used internally) |
| `grid_manager.py` | For 4x4 multi-display setups (future use) |

### Original Files (from upstream project)

| File | What It Does |
|------|--------------|
| `draw_pixels.py` | Standalone script to draw random pixels |
| `draw_picture.py` | Standalone script to send full images |
| `faster_connect.py` | Quick device scanner |
| `protocol.txt` | Documents the BLE command format |

### The `snoops/` Folder

These are **Bluetooth packet captures** from Android. The original developers used these to reverse-engineer the display protocol. You don't need them unless you're debugging the protocol.

---

## API Reference

### Scan for Displays
```
POST /displays/scan
```

### Connect to Display
```
POST /displays/<MAC>/connect
Body: {"grid_position": 0}  (optional, for multi-display)
```

### Set Single Pixel
```
POST /displays/<MAC>/pixel
Body: {"x": 0, "y": 0, "r": 255, "g": 0, "b": 0}
```
- x, y: 0-15 (pixel coordinates)
- r, g, b: 0-255 (color values)

### Set Full Image (256 Pixels)
```
POST /displays/<MAC>/image
Body: {"pixels": [[r,g,b], [r,g,b], ...]}  (256 RGB arrays)
```

### Fill with Solid Color
```
POST /displays/<MAC>/fill
Body: {"r": 255, "g": 0, "b": 0}
```

### Clear Display
```
POST /displays/<MAC>/clear
```

### Check Status
```
GET /displays/<MAC>/status
GET /health
```

---

## Troubleshooting

### "No displays found"
- Make sure display is powered on
- Display should show something (not completely off)
- Run `python bt_scanner.py continuous` for a longer scan

### "Connection failed"
- Display might be connected to your phone - disconnect it first
- Try power cycling the display
- Make sure Bluetooth is enabled: `sudo hciconfig hci0 up`

### "Server runs but http://localhost:5000 doesn't work"
- Check firewall settings
- Try `http://127.0.0.1:5000`
- Make sure Flask started (look for "Running on http://..." message)

---

## Multi-Display Setup (16 Displays in 4x4 Grid)

For future expansion to 16 displays:

1. Scan and note all MAC addresses
2. Connect each with a grid position (0-15):
   ```bash
   curl -X POST http://localhost:5000/displays/MAC1/connect -d '{"grid_position": 0}'
   curl -X POST http://localhost:5000/displays/MAC2/connect -d '{"grid_position": 1}'
   # ... etc
   ```

3. Use grid endpoints for 64x64 pixel control:
   ```bash
   curl -X POST http://localhost:5000/grid/pixel -d '{"x": 32, "y": 32, "r": 255, "g": 0, "b": 0}'
   ```

Grid positions:
```
+---+---+---+---+
| 0 | 1 | 2 | 3 |
+---+---+---+---+
| 4 | 5 | 6 | 7 |
+---+---+---+---+
| 8 | 9 |10 |11 |
+---+---+---+---+
|12 |13 |14 |15 |
+---+---+---+---+
```
