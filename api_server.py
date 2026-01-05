"""
REST API Server for MI Matrix Display System
Flask-based HTTP endpoints for pixel control and display management.
"""

import asyncio
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from typing import List, Tuple
import base64

from matrix_controller import get_controller, MatrixController
from grid_manager import get_grid_manager, GridManager
from display_registry import get_registry

# Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for browser access

# Async event loop for Bluetooth operations
_loop: asyncio.AbstractEventLoop = None
_controller: MatrixController = None
_grid: GridManager = None


def run_async(coro):
    """Run async coroutine from sync Flask context."""
    return asyncio.run_coroutine_threadsafe(coro, _loop).result()


# ==================== Display Management ====================

@app.route('/displays', methods=['GET'])
def list_displays():
    """Get all registered displays."""
    displays = _controller.get_displays()
    return jsonify({
        "success": True,
        "displays": displays,
        "count": len(displays)
    })


@app.route('/displays/scan', methods=['GET', 'POST'])
def scan_displays():
    """Scan for MI Matrix Display devices."""
    # Get timeout from query string or JSON body
    timeout = 10
    if request.method == 'POST' and request.data:
        try:
            data = request.get_json(force=True, silent=True)
            if data and 'timeout' in data:
                timeout = data['timeout']
        except:
            pass
    elif request.args.get('timeout'):
        timeout = int(request.args.get('timeout'))
    
    try:
        devices = run_async(_controller.scan(timeout))
        return jsonify({
            "success": True,
            "devices_found": devices,
            "count": len(devices)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/displays/<mac_address>/connect', methods=['GET', 'POST'])
def connect_display(mac_address: str):
    """Connect to a display by MAC address."""
    # Normalize MAC address format
    mac_address = mac_address.replace('-', ':').upper()
    
    # Get grid_position from query string or JSON body
    grid_position = None
    if request.method == 'POST' and request.data:
        try:
            data = request.get_json(force=True, silent=True)
            if data and 'grid_position' in data:
                grid_position = data['grid_position']
        except:
            pass
    elif request.args.get('grid_position'):
        grid_position = int(request.args.get('grid_position'))
    
    try:
        success = run_async(_controller.connect_display(mac_address, grid_position))
        return jsonify({
            "success": success,
            "mac_address": mac_address,
            "grid_position": grid_position
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/displays/<mac_address>/disconnect', methods=['POST'])
def disconnect_display(mac_address: str):
    """Disconnect from a display."""
    mac_address = mac_address.replace('-', ':').upper()
    
    try:
        run_async(_controller.disconnect_display(mac_address))
        return jsonify({"success": True, "mac_address": mac_address})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/displays/<mac_address>/status', methods=['GET'])
def display_status(mac_address: str):
    """Get display status."""
    mac_address = mac_address.replace('-', ':').upper()
    display = _controller.get_display(mac_address)
    
    if display:
        return jsonify({"success": True, "display": display})
    else:
        return jsonify({"success": False, "error": "Display not found"}), 404


# ==================== Pixel Operations ====================

@app.route('/displays/<mac_address>/pixel', methods=['POST'])
def set_pixel(mac_address: str):
    """
    Set a single pixel.
    
    Body: {"x": 0, "y": 0, "r": 255, "g": 0, "b": 0}
    """
    mac_address = mac_address.replace('-', ':').upper()
    data = request.json
    
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    
    try:
        x = int(data['x'])
        y = int(data['y'])
        r = int(data.get('r', 255))
        g = int(data.get('g', 255))
        b = int(data.get('b', 255))
        
        success = _controller.set_pixel(mac_address, x, y, r, g, b)
        return jsonify({"success": success})
    except (KeyError, ValueError) as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/displays/<mac_address>/pixels', methods=['POST'])
def set_pixels(mac_address: str):
    """
    Set multiple pixels at once.
    
    Body: {"pixels": [{"x": 0, "y": 0, "r": 255, "g": 0, "b": 0}, ...]}
    """
    mac_address = mac_address.replace('-', ':').upper()
    data = request.json
    
    if not data or 'pixels' not in data:
        return jsonify({"success": False, "error": "No pixels provided"}), 400
    
    try:
        count = 0
        for p in data['pixels']:
            success = _controller.set_pixel(
                mac_address, 
                int(p['x']), int(p['y']),
                int(p.get('r', 255)), int(p.get('g', 255)), int(p.get('b', 255))
            )
            if success:
                count += 1
        
        return jsonify({"success": True, "pixels_set": count})
    except (KeyError, ValueError) as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/displays/<mac_address>/image', methods=['POST'])
def set_image(mac_address: str):
    """
    Set full 16x16 image.
    
    Body: {"pixels": [[r,g,b], [r,g,b], ...]} (256 RGB arrays)
    or:   {"image_base64": "..."} (base64 encoded image)
    """
    mac_address = mac_address.replace('-', ':').upper()
    data = request.json
    
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    
    try:
        if 'pixels' in data:
            # Direct pixel array
            pixels = [(p[0], p[1], p[2]) for p in data['pixels']]
            if len(pixels) != 256:
                return jsonify({
                    "success": False, 
                    "error": f"Expected 256 pixels, got {len(pixels)}"
                }), 400
            
            success = _controller.set_image(mac_address, pixels)
            
        elif 'image_base64' in data:
            # Base64 image
            from grid_manager import get_grid_manager
            from PIL import Image
            import io
            
            img_data = base64.b64decode(data['image_base64'])
            img = Image.open(io.BytesIO(img_data))
            img = img.resize((16, 16)).convert('RGB')
            
            pixels = []
            for y in range(16):
                for x in range(16):
                    p = img.getpixel((x, y))
                    pixels.append((p[0], p[1], p[2]))
            
            success = _controller.set_image(mac_address, pixels)
        else:
            return jsonify({"success": False, "error": "No pixels or image provided"}), 400
        
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/displays/<mac_address>/clear', methods=['POST'])
def clear_display(mac_address: str):
    """Clear display to black."""
    mac_address = mac_address.replace('-', ':').upper()
    success = _controller.clear_display(mac_address)
    return jsonify({"success": success})


@app.route('/displays/<mac_address>/fill', methods=['POST'])
def fill_display(mac_address: str):
    """
    Fill display with solid color.
    
    Body: {"r": 255, "g": 0, "b": 0}
    """
    mac_address = mac_address.replace('-', ':').upper()
    data = request.json or {}
    
    r = int(data.get('r', 0))
    g = int(data.get('g', 0))
    b = int(data.get('b', 0))
    
    success = _controller.fill_display(mac_address, r, g, b)
    return jsonify({"success": success})


# ==================== Grid Operations ====================

@app.route('/grid', methods=['GET'])
def get_grid_status():
    """Get 4x4 grid status."""
    return jsonify({
        "success": True,
        "grid": _grid.registry.get_grid_status(),
        "dimensions": {
            "rows": 4,
            "cols": 4,
            "total_pixels": 64 * 64
        }
    })


@app.route('/grid/pixel', methods=['POST'])
def set_global_pixel():
    """
    Set pixel in global 64x64 grid.
    
    Body: {"x": 0, "y": 0, "r": 255, "g": 0, "b": 0}
    """
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data"}), 400
    
    try:
        success = _grid.set_global_pixel(
            int(data['x']), int(data['y']),
            int(data.get('r', 255)),
            int(data.get('g', 255)),
            int(data.get('b', 255))
        )
        return jsonify({"success": success})
    except (KeyError, ValueError) as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/grid/image', methods=['POST'])
def set_grid_image():
    """
    Set full 64x64 grid image.
    
    Body: {"image_base64": "..."} (base64 encoded image)
    """
    data = request.json
    if not data or 'image_base64' not in data:
        return jsonify({"success": False, "error": "No image provided"}), 400
    
    try:
        img_data = base64.b64decode(data['image_base64'])
        success = _grid.load_image_bytes(img_data)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/grid/clear', methods=['POST'])
def clear_grid():
    """Clear entire grid to black."""
    _grid.clear_grid()
    return jsonify({"success": True})


@app.route('/grid/schedule', methods=['GET'])
def get_update_schedule():
    """Get update schedule for connected displays."""
    interval = request.args.get('interval_ms', 1000, type=int)
    schedule = _grid.get_update_schedule(interval)
    return jsonify({"success": True, "schedule": schedule})


# ==================== By Grid Position ====================

@app.route('/position/<int:position>/pixel', methods=['POST'])
def set_pixel_by_position(position: int):
    """Set pixel on display at grid position."""
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data"}), 400
    
    try:
        success = _controller.set_pixel_by_position(
            position,
            int(data['x']), int(data['y']),
            int(data.get('r', 255)),
            int(data.get('g', 255)),
            int(data.get('b', 255))
        )
        return jsonify({"success": success})
    except (KeyError, ValueError) as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/position/<int:position>/image', methods=['POST'])
def set_image_by_position(position: int):
    """Set image on display at grid position."""
    data = request.json
    if not data or 'pixels' not in data:
        return jsonify({"success": False, "error": "No pixels"}), 400
    
    try:
        pixels = [(p[0], p[1], p[2]) for p in data['pixels']]
        success = _controller.set_image_by_position(position, pixels)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== Root Route ====================

@app.route('/', methods=['GET'])
def index():
    """Root endpoint - shows API is running."""
    return jsonify({
        "name": "MI Matrix Display API",
        "version": "1.0",
        "endpoints": [
            "GET  /health",
            "GET  /displays",
            "POST /displays/scan",
            "POST /displays/<mac>/connect",
            "POST /displays/<mac>/pixel",
            "POST /displays/<mac>/image"
        ]
    })


# ==================== Health Check ====================

@app.route('/health', methods=['GET'])
def health_check():
    """API health check."""
    displays = _controller.get_displays()
    connected = sum(1 for d in displays if d.get('state') == 'connected')
    
    return jsonify({
        "status": "healthy",
        "displays_registered": len(displays),
        "displays_connected": connected
    })


# ==================== Server Startup ====================

def start_async_loop():
    """Start async event loop in background thread."""
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_forever()


def run_server(host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
    """
    Start the API server.
    
    Args:
        host: Bind address (0.0.0.0 for network access)
        port: Port number
        debug: Flask debug mode
    """
    global _controller, _grid
    
    # Start async loop in background
    loop_thread = threading.Thread(target=start_async_loop, daemon=True)
    loop_thread.start()
    
    # Wait for loop to start
    import time
    while _loop is None:
        time.sleep(0.1)
    
    # Initialize controller and grid manager
    _controller = get_controller()
    _grid = get_grid_manager()
    
    # Start controller
    asyncio.run_coroutine_threadsafe(_controller.start(), _loop)
    
    print("")
    print("=" * 50)
    print("MI Matrix Display API Server")
    print("=" * 50)
    print("Server starting on http://{}:{}".format(host, port))
    print("")
    print("Endpoints:")
    print("  GET  /              - API info")
    print("  GET  /health        - Health check")
    print("  GET  /displays      - List displays")
    print("  POST /displays/scan - Scan for devices")
    print("  POST /displays/<mac>/connect")
    print("  POST /displays/<mac>/pixel")
    print("  POST /displays/<mac>/image")
    print("=" * 50)
    print("")
    
    # Run Flask
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    run_server()

