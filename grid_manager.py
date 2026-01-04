"""
Grid Manager for MI Matrix Display System
Manages 4x4 grid of displays (64x64 total pixels).
"""

from typing import Dict, List, Optional, Tuple
from PIL import Image
import io

from display_registry import get_registry, DisplayInfo


class GridManager:
    """
    Manages a 4x4 grid of MI Matrix Displays.
    Total resolution: 64x64 pixels (16x16 per display).
    
    Grid Layout:
    +---+---+---+---+
    | 0 | 1 | 2 | 3 |
    +---+---+---+---+
    | 4 | 5 | 6 | 7 |
    +---+---+---+---+
    | 8 | 9 |10 |11 |
    +---+---+---+---+
    |12 |13 |14 |15 |
    +---+---+---+---+
    """
    
    GRID_ROWS = 4
    GRID_COLS = 4
    DISPLAY_WIDTH = 16
    DISPLAY_HEIGHT = 16
    TOTAL_WIDTH = GRID_COLS * DISPLAY_WIDTH  # 64
    TOTAL_HEIGHT = GRID_ROWS * DISPLAY_HEIGHT  # 64
    
    def __init__(self):
        self.registry = get_registry()
        # Buffer for full 64x64 grid
        self._grid_buffer: List[List[Tuple[int, int, int]]] = [
            [(0, 0, 0) for _ in range(self.TOTAL_WIDTH)]
            for _ in range(self.TOTAL_HEIGHT)
        ]
    
    # ==================== Coordinate Mapping ====================
    
    def global_to_display(self, gx: int, gy: int) -> Tuple[int, int, int]:
        """
        Convert global grid coordinates to display position and local coords.
        
        Args:
            gx, gy: Global coordinates (0-63)
            
        Returns:
            (display_position, local_x, local_y)
        """
        if not (0 <= gx < self.TOTAL_WIDTH and 0 <= gy < self.TOTAL_HEIGHT):
            raise ValueError(f"Coordinates ({gx}, {gy}) out of range")
        
        # Determine which display (grid position)
        display_col = gx // self.DISPLAY_WIDTH
        display_row = gy // self.DISPLAY_HEIGHT
        display_position = display_row * self.GRID_COLS + display_col
        
        # Local coordinates within display
        local_x = gx % self.DISPLAY_WIDTH
        local_y = gy % self.DISPLAY_HEIGHT
        
        return (display_position, local_x, local_y)
    
    def display_to_global(self, position: int, lx: int, ly: int) -> Tuple[int, int]:
        """
        Convert display position and local coords to global coords.
        
        Args:
            position: Display position (0-15)
            lx, ly: Local coordinates (0-15)
            
        Returns:
            (global_x, global_y)
        """
        display_row = position // self.GRID_COLS
        display_col = position % self.GRID_COLS
        
        global_x = display_col * self.DISPLAY_WIDTH + lx
        global_y = display_row * self.DISPLAY_HEIGHT + ly
        
        return (global_x, global_y)
    
    # ==================== Grid Buffer Operations ====================
    
    def set_global_pixel(self, gx: int, gy: int, 
                         r: int, g: int, b: int) -> bool:
        """
        Set pixel in global grid buffer.
        
        Args:
            gx, gy: Global coordinates (0-63)
            r, g, b: Color values (0-255)
        """
        if 0 <= gx < self.TOTAL_WIDTH and 0 <= gy < self.TOTAL_HEIGHT:
            self._grid_buffer[gy][gx] = (r & 0xFF, g & 0xFF, b & 0xFF)
            
            # Also update the display's local buffer
            pos, lx, ly = self.global_to_display(gx, gy)
            display = self.registry.get_display_by_position(pos)
            if display:
                self.registry.set_pixel(display.mac_address, lx, ly, r, g, b)
            
            return True
        return False
    
    def get_global_pixel(self, gx: int, gy: int) -> Tuple[int, int, int]:
        """Get pixel from global grid buffer."""
        if 0 <= gx < self.TOTAL_WIDTH and 0 <= gy < self.TOTAL_HEIGHT:
            return self._grid_buffer[gy][gx]
        return (0, 0, 0)
    
    def clear_grid(self) -> None:
        """Clear entire grid to black."""
        for y in range(self.TOTAL_HEIGHT):
            for x in range(self.TOTAL_WIDTH):
                self._grid_buffer[y][x] = (0, 0, 0)
        
        # Mark all displays as dirty
        for display in self.registry.get_all_displays():
            self.registry.set_image(display.mac_address, [(0, 0, 0)] * 256)
    
    def fill_grid(self, r: int, g: int, b: int) -> None:
        """Fill entire grid with solid color."""
        color = (r & 0xFF, g & 0xFF, b & 0xFF)
        for y in range(self.TOTAL_HEIGHT):
            for x in range(self.TOTAL_WIDTH):
                self._grid_buffer[y][x] = color
        
        # Update all displays
        for display in self.registry.get_all_displays():
            self.registry.set_image(display.mac_address, [color] * 256)
    
    # ==================== Image Loading ====================
    
    def load_image(self, image_path: str) -> bool:
        """
        Load 64x64 image and distribute to displays.
        
        Args:
            image_path: Path to image file (will be resized to 64x64)
        """
        try:
            img = Image.open(image_path)
            return self.load_pil_image(img)
        except Exception as e:
            print(f"Failed to load image: {e}")
            return False
    
    def load_image_bytes(self, image_data: bytes) -> bool:
        """Load image from bytes."""
        try:
            img = Image.open(io.BytesIO(image_data))
            return self.load_pil_image(img)
        except Exception as e:
            print(f"Failed to load image: {e}")
            return False
    
    def load_pil_image(self, img: Image.Image) -> bool:
        """
        Load PIL Image and distribute to grid displays.
        
        Args:
            img: PIL Image object
        """
        # Resize to 64x64
        img = img.resize((self.TOTAL_WIDTH, self.TOTAL_HEIGHT))
        img = img.convert('RGB')
        
        # Update grid buffer
        for y in range(self.TOTAL_HEIGHT):
            for x in range(self.TOTAL_WIDTH):
                pixel = img.getpixel((x, y))
                self._grid_buffer[y][x] = (pixel[0], pixel[1], pixel[2])
        
        # Distribute to displays
        self._distribute_to_displays()
        return True
    
    def _distribute_to_displays(self) -> None:
        """Distribute grid buffer to individual displays."""
        for position in range(16):
            display = self.registry.get_display_by_position(position)
            if not display:
                continue
            
            # Extract 16x16 region for this display
            pixels: List[Tuple[int, int, int]] = []
            display_row = position // self.GRID_COLS
            display_col = position % self.GRID_COLS
            
            start_y = display_row * self.DISPLAY_HEIGHT
            start_x = display_col * self.DISPLAY_WIDTH
            
            for ly in range(self.DISPLAY_HEIGHT):
                for lx in range(self.DISPLAY_WIDTH):
                    gx = start_x + lx
                    gy = start_y + ly
                    pixels.append(self._grid_buffer[gy][gx])
            
            self.registry.set_image(display.mac_address, pixels)
    
    # ==================== Display Region Extraction ====================
    
    def get_display_pixels(self, position: int) -> List[Tuple[int, int, int]]:
        """
        Get 16x16 pixel array for a specific display position.
        
        Args:
            position: Grid position (0-15)
            
        Returns:
            List of 256 (r, g, b) tuples in row-major order
        """
        pixels = []
        display_row = position // self.GRID_COLS
        display_col = position % self.GRID_COLS
        
        start_y = display_row * self.DISPLAY_HEIGHT
        start_x = display_col * self.DISPLAY_WIDTH
        
        for ly in range(self.DISPLAY_HEIGHT):
            for lx in range(self.DISPLAY_WIDTH):
                gx = start_x + lx
                gy = start_y + ly
                pixels.append(self._grid_buffer[gy][gx])
        
        return pixels
    
    # ==================== Update Scheduling ====================
    
    def get_update_order(self) -> List[int]:
        """
        Get list of display positions to update in order.
        Returns only positions with connected displays.
        """
        order = []
        for pos in range(16):
            display = self.registry.get_display_by_position(pos)
            if display and display.state.value == "connected":
                order.append(pos)
        return order
    
    def get_update_schedule(self, interval_ms: int = 1000) -> Dict:
        """
        Get timing schedule for sequential display updates.
        
        Args:
            interval_ms: Milliseconds between each display update
            
        Returns:
            Dict with timing info
        """
        order = self.get_update_order()
        total_time_ms = len(order) * interval_ms
        
        return {
            "display_order": order,
            "interval_ms": interval_ms,
            "total_refresh_ms": total_time_ms,
            "fps": 1000 / total_time_ms if total_time_ms > 0 else 0
        }


# Singleton instance
_grid_manager = None


def get_grid_manager() -> GridManager:
    """Get or create singleton GridManager instance."""
    global _grid_manager
    if _grid_manager is None:
        _grid_manager = GridManager()
    return _grid_manager
