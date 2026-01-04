"""
Display Registry for MI Matrix Display System
Manages runtime state of multiple displays and grid mapping.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class DisplayState(Enum):
    """Connection state for a display."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class DisplayInfo:
    """Runtime information about a single display."""
    mac_address: str
    name: str = ""
    state: DisplayState = DisplayState.DISCONNECTED
    grid_position: Optional[int] = None  # 0-15 for 4x4 grid
    last_connected: Optional[datetime] = None
    error_message: Optional[str] = None
    client: Optional[object] = None  # BleakClient when connected
    
    # Pixel buffer for this display (16x16 = 256 pixels, RGB)
    pixel_buffer: List[Tuple[int, int, int]] = field(
        default_factory=lambda: [(0, 0, 0)] * 256
    )
    buffer_dirty: bool = False  # True if buffer needs to be sent
    
    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dict."""
        return {
            "mac_address": self.mac_address,
            "name": self.name,
            "state": self.state.value,
            "grid_position": self.grid_position,
            "last_connected": self.last_connected.isoformat() if self.last_connected else None,
            "error_message": self.error_message
        }


class DisplayRegistry:
    """
    Registry tracking all known displays and their runtime state.
    Supports 4x4 grid (16 displays) for future expansion.
    """
    
    # Grid constants
    GRID_ROWS = 4
    GRID_COLS = 4
    PIXELS_PER_DISPLAY = 16
    
    def __init__(self):
        self._displays: Dict[str, DisplayInfo] = {}  # MAC -> DisplayInfo
        self._position_map: Dict[int, str] = {}  # position -> MAC
        self._lock = asyncio.Lock()
    
    async def register_display(self, mac_address: str, name: str = "",
                                grid_position: Optional[int] = None) -> DisplayInfo:
        """
        Register a new display or update existing one.
        
        Args:
            mac_address: Bluetooth MAC address
            name: Human-readable name
            grid_position: Optional grid position (0-15)
        """
        async with self._lock:
            if mac_address in self._displays:
                display = self._displays[mac_address]
                if name:
                    display.name = name
                if grid_position is not None:
                    self._update_position(mac_address, grid_position)
            else:
                display = DisplayInfo(
                    mac_address=mac_address,
                    name=name or f"Display_{len(self._displays)}",
                    grid_position=grid_position
                )
                self._displays[mac_address] = display
                if grid_position is not None:
                    self._position_map[grid_position] = mac_address
            
            return display
    
    def _update_position(self, mac_address: str, position: int) -> None:
        """Update grid position for a display (must hold lock)."""
        if position < 0 or position > 15:
            raise ValueError("Grid position must be 0-15")
        
        # Remove old position mapping
        display = self._displays.get(mac_address)
        if display and display.grid_position is not None:
            self._position_map.pop(display.grid_position, None)
        
        # Remove any existing display at new position
        if position in self._position_map:
            old_mac = self._position_map[position]
            if old_mac in self._displays:
                self._displays[old_mac].grid_position = None
        
        # Set new position
        self._position_map[position] = mac_address
        if display:
            display.grid_position = position
    
    async def unregister_display(self, mac_address: str) -> bool:
        """Remove a display from the registry."""
        async with self._lock:
            if mac_address in self._displays:
                display = self._displays[mac_address]
                if display.grid_position is not None:
                    self._position_map.pop(display.grid_position, None)
                del self._displays[mac_address]
                return True
            return False
    
    def get_display(self, mac_address: str) -> Optional[DisplayInfo]:
        """Get display by MAC address."""
        return self._displays.get(mac_address)
    
    def get_display_by_position(self, position: int) -> Optional[DisplayInfo]:
        """Get display at grid position."""
        mac = self._position_map.get(position)
        return self._displays.get(mac) if mac else None
    
    def get_display_by_grid_coords(self, row: int, col: int) -> Optional[DisplayInfo]:
        """Get display at (row, col) in grid."""
        if 0 <= row < self.GRID_ROWS and 0 <= col < self.GRID_COLS:
            position = row * self.GRID_COLS + col
            return self.get_display_by_position(position)
        return None
    
    def get_all_displays(self) -> List[DisplayInfo]:
        """Get all registered displays."""
        return list(self._displays.values())
    
    def get_connected_displays(self) -> List[DisplayInfo]:
        """Get all connected displays."""
        return [d for d in self._displays.values() 
                if d.state == DisplayState.CONNECTED]
    
    async def set_state(self, mac_address: str, state: DisplayState,
                        error_message: Optional[str] = None) -> None:
        """Update display connection state."""
        async with self._lock:
            if mac_address in self._displays:
                display = self._displays[mac_address]
                display.state = state
                display.error_message = error_message
                if state == DisplayState.CONNECTED:
                    display.last_connected = datetime.now()
    
    async def set_client(self, mac_address: str, client: object) -> None:
        """Store BleakClient reference for connected display."""
        async with self._lock:
            if mac_address in self._displays:
                self._displays[mac_address].client = client
    
    # Pixel Buffer Operations
    def set_pixel(self, mac_address: str, x: int, y: int, 
                  r: int, g: int, b: int) -> bool:
        """
        Set a pixel in the display's buffer.
        
        Args:
            mac_address: Display MAC address
            x, y: Pixel coordinates (0-15)
            r, g, b: Color values (0-255)
        """
        display = self._displays.get(mac_address)
        if display and 0 <= x < 16 and 0 <= y < 16:
            index = y * 16 + x
            display.pixel_buffer[index] = (r & 0xFF, g & 0xFF, b & 0xFF)
            display.buffer_dirty = True
            return True
        return False
    
    def set_image(self, mac_address: str, pixels: List[Tuple[int, int, int]]) -> bool:
        """
        Set entire 16x16 image for display.
        
        Args:
            mac_address: Display MAC address
            pixels: List of 256 (r, g, b) tuples in row-major order
        """
        display = self._displays.get(mac_address)
        if display and len(pixels) == 256:
            display.pixel_buffer = [
                (p[0] & 0xFF, p[1] & 0xFF, p[2] & 0xFF) 
                for p in pixels
            ]
            display.buffer_dirty = True
            return True
        return False
    
    def get_dirty_displays(self) -> List[DisplayInfo]:
        """Get displays with pending pixel updates."""
        return [d for d in self._displays.values() if d.buffer_dirty]
    
    def clear_dirty_flag(self, mac_address: str) -> None:
        """Mark display buffer as sent."""
        if mac_address in self._displays:
            self._displays[mac_address].buffer_dirty = False
    
    # Grid Utilities
    @staticmethod
    def position_to_coords(position: int) -> Tuple[int, int]:
        """Convert grid position (0-15) to (row, col)."""
        return (position // 4, position % 4)
    
    @staticmethod
    def coords_to_position(row: int, col: int) -> int:
        """Convert (row, col) to grid position (0-15)."""
        return row * 4 + col
    
    def get_grid_status(self) -> List[List[Optional[Dict]]]:
        """
        Get 4x4 grid status for visualization.
        Returns 2D array with display info or None for empty positions.
        """
        grid = [[None for _ in range(4)] for _ in range(4)]
        for pos, mac in self._position_map.items():
            row, col = self.position_to_coords(pos)
            display = self._displays.get(mac)
            if display:
                grid[row][col] = display.to_dict()
        return grid


# Singleton instance
_registry: Optional[DisplayRegistry] = None


def get_registry() -> DisplayRegistry:
    """Get or create singleton DisplayRegistry instance."""
    global _registry
    if _registry is None:
        _registry = DisplayRegistry()
    return _registry
