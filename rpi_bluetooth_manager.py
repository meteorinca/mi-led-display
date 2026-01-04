"""
Raspberry Pi Bluetooth Manager for MI Matrix Display System
Handles BLE discovery, connection management, and auto-reconnection.
"""

import asyncio
import time
from typing import Dict, List, Optional, Callable
from bleak import BleakScanner, BleakClient, BleakError
from bleak.backends.device import BLEDevice

from display_registry import get_registry, DisplayState, DisplayInfo
from config_manager import get_config_manager

# MI Matrix Display BLE UUIDs
SERVICE_UUID = "0000ffd0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "0000ffd1-0000-1000-8000-00805f9b34fb"
DEVICE_NAME = "MI Matrix Display"


class BluetoothManager:
    """
    Manages Bluetooth connections to MI Matrix Displays.
    Supports multiple simultaneous connections for 4x4 grid.
    """
    
    def __init__(self):
        self.registry = get_registry()
        self.config = get_config_manager()
        self._clients: Dict[str, BleakClient] = {}  # MAC -> BleakClient
        self._scan_callback: Optional[Callable] = None
        self._running = False
        self._update_task: Optional[asyncio.Task] = None
    
    # ==================== Scanning ====================
    
    async def scan_for_displays(self, timeout: int = None) -> List[BLEDevice]:
        """
        Scan for MI Matrix Display devices.
        
        Args:
            timeout: Scan timeout in seconds (default from config)
            
        Returns:
            List of discovered BLEDevice objects
        """
        timeout = timeout or self.config.get_scan_timeout()
        found_devices: List[BLEDevice] = []
        
        def detection_callback(device: BLEDevice, advertisement_data):
            if device.name and DEVICE_NAME in device.name:
                if device not in found_devices:
                    found_devices.append(device)
                    print(f"Found: {device.name} [{device.address}]")
        
        print(f"Scanning for {DEVICE_NAME} devices ({timeout}s)...")
        scanner = BleakScanner(detection_callback)
        
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()
        
        # Register discovered devices
        for device in found_devices:
            await self.registry.register_display(
                mac_address=device.address,
                name=device.name or DEVICE_NAME
            )
            # Also save to config for persistence
            self.config.add_display(device.address, device.name)
        
        print(f"Found {len(found_devices)} display(s)")
        return found_devices
    
    async def quick_scan(self, known_address: str, timeout: int = 5) -> Optional[BLEDevice]:
        """
        Quick scan for a specific known device.
        Uses cached MAC address for faster reconnection.
        """
        found_device = None
        
        def detection_callback(device: BLEDevice, advertisement_data):
            nonlocal found_device
            if device.address.upper() == known_address.upper():
                found_device = device
        
        scanner = BleakScanner(detection_callback)
        await scanner.start()
        
        start_time = time.time()
        while found_device is None and (time.time() - start_time) < timeout:
            await asyncio.sleep(0.1)
        
        await scanner.stop()
        return found_device
    
    # ==================== Connection ====================
    
    async def connect(self, mac_address: str, retry_count: int = None) -> bool:
        """
        Connect to a display by MAC address.
        
        Args:
            mac_address: Bluetooth MAC address
            retry_count: Number of connection retries
            
        Returns:
            True if connected successfully
        """
        retry_count = retry_count or self.config.config.get("connection_retry_count", 3)
        
        await self.registry.set_state(mac_address, DisplayState.CONNECTING)
        
        for attempt in range(retry_count):
            try:
                print(f"Connecting to {mac_address} (attempt {attempt + 1}/{retry_count})...")
                
                # Create client
                client = BleakClient(mac_address)
                await client.connect()
                
                if client.is_connected:
                    self._clients[mac_address] = client
                    await self.registry.set_state(mac_address, DisplayState.CONNECTED)
                    await self.registry.set_client(mac_address, client)
                    print(f"Connected to {mac_address}")
                    return True
                    
            except BleakError as e:
                print(f"Connection attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(1)
        
        await self.registry.set_state(
            mac_address, 
            DisplayState.ERROR, 
            f"Failed after {retry_count} attempts"
        )
        return False
    
    async def disconnect(self, mac_address: str) -> None:
        """Disconnect from a display."""
        if mac_address in self._clients:
            client = self._clients[mac_address]
            try:
                await client.disconnect()
            except BleakError:
                pass
            del self._clients[mac_address]
        
        await self.registry.set_state(mac_address, DisplayState.DISCONNECTED)
        print(f"Disconnected from {mac_address}")
    
    async def disconnect_all(self) -> None:
        """Disconnect from all displays."""
        for mac_address in list(self._clients.keys()):
            await self.disconnect(mac_address)
    
    def is_connected(self, mac_address: str) -> bool:
        """Check if display is connected."""
        client = self._clients.get(mac_address)
        return client is not None and client.is_connected
    
    # ==================== Commands ====================
    
    async def send_command(self, mac_address: str, data: bytes) -> bool:
        """
        Send raw command to display.
        
        Args:
            mac_address: Target display
            data: Raw command bytes
            
        Returns:
            True if sent successfully
        """
        client = self._clients.get(mac_address)
        if not client or not client.is_connected:
            return False
        
        try:
            await client.write_gatt_char(CHARACTERISTIC_UUID, data)
            return True
        except BleakError as e:
            print(f"Send failed to {mac_address}: {e}")
            await self.registry.set_state(mac_address, DisplayState.ERROR, str(e))
            return False
    
    async def initialize_display(self, mac_address: str) -> bool:
        """Send initialization commands to enter graffiti mode."""
        init_commands = [
            bytes.fromhex("bc00010155"),  # Power on
            bytes.fromhex("bc000d0d55"),  # Enter graffiti mode
        ]
        
        for cmd in init_commands:
            if not await self.send_command(mac_address, cmd):
                return False
            await asyncio.sleep(0.05)
        
        return True
    
    async def send_pixel(self, mac_address: str, 
                         pixel_index: int, r: int, g: int, b: int) -> bool:
        """
        Send single pixel update to display.
        
        Args:
            mac_address: Target display
            pixel_index: Pixel position (0-255)
            r, g, b: Color values (0-255)
        """
        end_index = (pixel_index + 1) % 256
        if pixel_index == 0:
            end_index = 0xFF
        
        command = bytearray([
            0xBC, 0x01, 0x01, 0x00,
            pixel_index,
            r & 0xFF, g & 0xFF, b & 0xFF,
            end_index,
            0x55
        ])
        
        return await self.send_command(mac_address, command)
    
    async def send_full_image(self, mac_address: str, 
                              pixels: List[tuple]) -> bool:
        """
        Send full 16x16 image to display using block transfer.
        
        Args:
            mac_address: Target display
            pixels: List of 256 (r, g, b) tuples
        """
        if len(pixels) != 256:
            return False
        
        # Start image transfer
        await self.send_command(mac_address, bytes.fromhex("bc0ff1080855"))
        await asyncio.sleep(0.002)
        
        # Send 8 blocks of 32 pixels each
        for block_index in range(8):
            start = block_index * 32
            block_pixels = pixels[start:start + 32]
            
            # Build block command
            header = bytearray([0xBC, 0x0F, (block_index + 1) & 0xFF])
            pixel_data = bytearray()
            for (r, g, b) in block_pixels:
                pixel_data.extend([r & 0xFF, g & 0xFF, b & 0xFF])
            
            command = header + pixel_data + bytearray([0x55])
            
            if not await self.send_command(mac_address, command):
                return False
            await asyncio.sleep(0.025)
        
        # End image transfer
        await self.send_command(mac_address, bytes.fromhex("bc0ff2080955"))
        
        return True
    
    # ==================== Update Loop ====================
    
    async def start_update_loop(self) -> None:
        """Start background task that sends pending updates to displays."""
        self._running = True
        self._update_task = asyncio.create_task(self._update_loop())
    
    async def stop_update_loop(self) -> None:
        """Stop the background update loop."""
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
    
    async def _update_loop(self) -> None:
        """
        Background loop that sends pending pixel updates to displays.
        Processes displays sequentially (1 per interval for 4x4 grid support).
        """
        interval_ms = self.config.get_update_interval()
        
        while self._running:
            dirty_displays = self.registry.get_dirty_displays()
            
            for display in dirty_displays:
                if not self.is_connected(display.mac_address):
                    continue
                
                # Send full image
                success = await self.send_full_image(
                    display.mac_address, 
                    display.pixel_buffer
                )
                
                if success:
                    self.registry.clear_dirty_flag(display.mac_address)
                
                # Wait between display updates (1 second default)
                await asyncio.sleep(interval_ms / 1000.0)
            
            # If no dirty displays, just wait a bit
            if not dirty_displays:
                await asyncio.sleep(0.1)
    
    # ==================== Auto-Reconnect ====================
    
    async def monitor_connections(self) -> None:
        """Monitor and auto-reconnect disconnected displays."""
        while self._running:
            for display in self.registry.get_all_displays():
                if display.state == DisplayState.CONNECTED:
                    # Check if still connected
                    client = self._clients.get(display.mac_address)
                    if not client or not client.is_connected:
                        await self.registry.set_state(
                            display.mac_address, 
                            DisplayState.DISCONNECTED
                        )
                        # Try to reconnect
                        await self.connect(display.mac_address)
            
            await asyncio.sleep(5)  # Check every 5 seconds


# Singleton instance
_manager: Optional[BluetoothManager] = None


def get_bluetooth_manager() -> BluetoothManager:
    """Get or create singleton BluetoothManager instance."""
    global _manager
    if _manager is None:
        _manager = BluetoothManager()
    return _manager


# ==================== CLI for testing ====================

async def main():
    """Test the Bluetooth manager."""
    manager = get_bluetooth_manager()
    
    # Scan for devices
    devices = await manager.scan_for_displays(timeout=10)
    
    if not devices:
        print("No displays found.")
        return
    
    # Connect to first device
    device = devices[0]
    connected = await manager.connect(device.address)
    
    if connected:
        # Initialize and send test pattern
        await manager.initialize_display(device.address)
        
        # Create rainbow test pattern
        pixels = []
        for y in range(16):
            for x in range(16):
                pixels.append((x * 16, y * 16, 128))
        
        await manager.send_full_image(device.address, pixels)
        print("Test pattern sent!")
        
        await asyncio.sleep(5)
        await manager.disconnect(device.address)


if __name__ == "__main__":
    asyncio.run(main())
