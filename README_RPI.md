# MI Matrix Display - Raspberry Pi Multi-Display System

Extension of the mi-led-display SDK for Raspberry Pi with REST API control and support for up to 16 displays in a 4×4 grid.

## Quick Start

### Installation (Raspberry Pi)

```bash
cd mi-led-display
pip install -r requirements.txt
```

### Start the API Server

```bash
python api_server.py
```

The server runs on `http://0.0.0.0:5000`

## API Usage

### Scan for Displays
```bash
curl -X POST http://localhost:5000/displays/scan
```

### Connect to Display
```bash
curl -X POST http://localhost:5000/displays/AA:BB:CC:DD:EE:FF/connect \
  -H "Content-Type: application/json" \
  -d '{"grid_position": 0}'
```

### Set Single Pixel
```bash
curl -X POST http://localhost:5000/displays/AA:BB:CC:DD:EE:FF/pixel \
  -H "Content-Type: application/json" \
  -d '{"x": 0, "y": 0, "r": 255, "g": 0, "b": 0}'
```

### Set Full Image (256 RGB values)
```bash
curl -X POST http://localhost:5000/displays/AA:BB:CC:DD:EE:FF/image \
  -H "Content-Type: application/json" \
  -d '{"pixels": [[255,0,0], [0,255,0], ...]}'
```

### Grid Operations (4×4 layout)
```bash
# Set pixel in 64×64 global grid
curl -X POST http://localhost:5000/grid/pixel \
  -d '{"x": 32, "y": 32, "r": 0, "g": 255, "b": 0}'
```

## File Structure

| File | Purpose |
|------|---------|
| `api_server.py` | Flask REST API (run this) |
| `matrix_controller.py` | High-level display interface |
| `rpi_bluetooth_manager.py` | BLE connection management |
| `display_registry.py` | Multi-display state tracking |
| `grid_manager.py` | 4×4 grid coordinate mapping |
| `config_manager.py` | Persistent configuration |

## Grid Layout (16 Displays)

```
┌───────┬───────┬───────┬───────┐
│   0   │   1   │   2   │   3   │
├───────┼───────┼───────┼───────┤
│   4   │   5   │   6   │   7   │
├───────┼───────┼───────┼───────┤
│   8   │   9   │  10   │  11   │
├───────┼───────┼───────┼───────┤
│  12   │  13   │  14   │  15   │
└───────┴───────┴───────┴───────┘
```

Each display is 16×16 pixels, for a total of 64×64 pixels.

## Timing

- **Per-display update**: ~200-250ms
- **Full 16-display refresh**: ~16 seconds (1 sec/display sequential)
- **Configurable via**: `config_manager.py`
