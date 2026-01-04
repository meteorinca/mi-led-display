"""
Matrix Controller for MI Matrix Display System
High-level interface for display operations with command queuing.
"""

import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import time

from display_registry import get_registry, DisplayInfo, DisplayState
from rpi_bluetooth_manager import get_bluetooth_manager


class CommandType(Enum):
    """Types of display commands."""
    SET_PIXEL = "set_pixel"
    SET_IMAGE = "set_image"
    CLEAR = "clear"
    POWER_ON = "power_on"
    POWER_OFF = "power_off"


@dataclass
class DisplayCommand:
    """A queued command for a display."""
    command_type: CommandType
    mac_address: str
    data: Dict
    timestamp: float
    priority: int = 0  # Higher = more urgent


class MatrixController:
    """
    High-level controller for MI Matrix Displays.
    Provides simple API for pixel/image operations with command batching.
    """
    
    def __init__(self):
        self.registry = get_registry()
        self.bt_manager = get_bluetooth_manager()
        self._command_queue: asyncio.Queue[DisplayCommand] = asyncio.Queue()
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
    
    # ==================== Lifecycle ====================
    
    async def start(self) -> None:
        """Start the controller and background processing."""
        self._running = True
        self._processor_task = asyncio.create_task(self._process_commands())
        await self.bt_manager.start_update_loop()
    
    async def stop(self) -> None:
        """Stop the controller."""
        self._running = False
        await self.bt_manager.stop_update_loop()
        if self._processor_task:
            self._processor_task.cancel()
    
    # ==================== Discovery & Connection ====================
    
    async def scan(self, timeout: int = 10) -> List[Dict]:
        """
        Scan for available displays.
        
        Returns:
            List of display info dicts
        """
        devices = await self.bt_manager.scan_for_displays(timeout)
        return [
            {"address": d.address, "name": d.name}
            for d in devices
        ]
    
    async def connect_display(self, mac_address: str, 
                               grid_position: Optional[int] = None) -> bool:
        """
        Connect to a display and optionally assign grid position.
        
        Args:
            mac_address: Bluetooth MAC address
            grid_position: Grid position (0-15) for 4x4 layout
        """
        # Register in registry
        await self.registry.register_display(
            mac_address=mac_address,
            grid_position=grid_position
        )
        
        # Connect via Bluetooth
        success = await self.bt_manager.connect(mac_address)
        
        if success:
            # Initialize display
            await self.bt_manager.initialize_display(mac_address)
        
        return success
    
    async def disconnect_display(self, mac_address: str) -> None:
        """Disconnect from a display."""
        await self.bt_manager.disconnect(mac_address)
    
    def get_displays(self) -> List[Dict]:
        """Get all registered displays with their status."""
        return [d.to_dict() for d in self.registry.get_all_displays()]
    
    def get_display(self, mac_address: str) -> Optional[Dict]:
        """Get single display info."""
        display = self.registry.get_display(mac_address)
        return display.to_dict() if display else None
    
    def get_display_by_position(self, position: int) -> Optional[Dict]:
        """Get display at grid position."""
        display = self.registry.get_display_by_position(position)
        return display.to_dict() if display else None
    
    # ==================== Pixel Operations ====================
    
    def set_pixel(self, mac_address: str, x: int, y: int,
                  r: int, g: int, b: int) -> bool:
        """
        Set a single pixel on a display.
        Updates buffer; actual send happens in update loop.
        
        Args:
            mac_address: Target display
            x, y: Pixel coordinates (0-15)
            r, g, b: Color values (0-255)
        """
        return self.registry.set_pixel(mac_address, x, y, r, g, b)
    
    def set_pixel_by_position(self, position: int, x: int, y: int,
                               r: int, g: int, b: int) -> bool:
        """Set pixel on display at grid position."""
        display = self.registry.get_display_by_position(position)
        if display:
            return self.registry.set_pixel(display.mac_address, x, y, r, g, b)
        return False
    
    def set_image(self, mac_address: str, 
                  pixels: List[Tuple[int, int, int]]) -> bool:
        """
        Set full 16x16 image on a display.
        
        Args:
            mac_address: Target display
            pixels: List of 256 (r, g, b) tuples in row-major order
        """
        return self.registry.set_image(mac_address, pixels)
    
    def set_image_by_position(self, position: int,
                               pixels: List[Tuple[int, int, int]]) -> bool:
        """Set image on display at grid position."""
        display = self.registry.get_display_by_position(position)
        if display:
            return self.registry.set_image(display.mac_address, pixels)
        return False
    
    def clear_display(self, mac_address: str) -> bool:
        """Clear display to black."""
        black_pixels = [(0, 0, 0)] * 256
        return self.registry.set_image(mac_address, black_pixels)
    
    def fill_display(self, mac_address: str, r: int, g: int, b: int) -> bool:
        """Fill display with solid color."""
        color_pixels = [(r, g, b)] * 256
        return self.registry.set_image(mac_address, color_pixels)
    
    # ==================== Direct Send (Bypass Buffer) ====================
    
    async def send_pixel_now(self, mac_address: str, x: int, y: int,
                              r: int, g: int, b: int) -> bool:
        """Send single pixel immediately (for real-time drawing)."""
        if not self.bt_manager.is_connected(mac_address):
            return False
        
        pixel_index = y * 16 + x
        return await self.bt_manager.send_pixel(mac_address, pixel_index, r, g, b)
    
    async def send_image_now(self, mac_address: str,
                              pixels: List[Tuple[int, int, int]]) -> bool:
        """Send full image immediately."""
        if not self.bt_manager.is_connected(mac_address):
            return False
        
        return await self.bt_manager.send_full_image(mac_address, pixels)
    
    # ==================== Grid Operations ====================
    
    def get_grid_status(self) -> List[List[Optional[Dict]]]:
        """Get 4x4 grid status."""
        return self.registry.get_grid_status()
    
    def assign_to_grid(self, mac_address: str, position: int) -> bool:
        """Assign display to grid position (0-15)."""
        display = self.registry.get_display(mac_address)
        if display and 0 <= position <= 15:
            asyncio.create_task(
                self.registry.register_display(
                    mac_address=mac_address,
                    grid_position=position
                )
            )
            return True
        return False
    
    # ==================== Command Processing ====================
    
    async def _process_commands(self) -> None:
        """Process queued commands."""
        while self._running:
            try:
                command = await asyncio.wait_for(
                    self._command_queue.get(), 
                    timeout=0.1
                )
                await self._execute_command(command)
            except asyncio.TimeoutError:
                continue
    
    async def _execute_command(self, cmd: DisplayCommand) -> None:
        """Execute a single command."""
        mac = cmd.mac_address
        
        if cmd.command_type == CommandType.SET_PIXEL:
            await self.send_pixel_now(
                mac, 
                cmd.data["x"], cmd.data["y"],
                cmd.data["r"], cmd.data["g"], cmd.data["b"]
            )
        elif cmd.command_type == CommandType.SET_IMAGE:
            await self.send_image_now(mac, cmd.data["pixels"])
        elif cmd.command_type == CommandType.CLEAR:
            await self.send_image_now(mac, [(0, 0, 0)] * 256)
        elif cmd.command_type == CommandType.POWER_ON:
            await self.bt_manager.send_command(mac, bytes.fromhex("bcff01ff55"))
        elif cmd.command_type == CommandType.POWER_OFF:
            await self.bt_manager.send_command(mac, bytes.fromhex("bcff00ff55"))


# Singleton instance
_controller: Optional[MatrixController] = None


def get_controller() -> MatrixController:
    """Get or create singleton MatrixController instance."""
    global _controller
    if _controller is None:
        _controller = MatrixController()
    return _controller
