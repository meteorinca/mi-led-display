"""
Bluetooth Scanner for MI Matrix Display
Scan for displays and get their MAC addresses without needing Android app.
Run this on Raspberry Pi to discover displays.
"""

import asyncio
from bleak import BleakScanner

# Known identifiers for MI Matrix Display
DEVICE_NAME = "MI Matrix Display"
SERVICE_UUID = "0000ffd0-0000-1000-8000-00805f9b34fb"


async def scan_all_ble_devices(timeout: int = 10):
    """Scan for all BLE devices and show details."""
    print(f"Scanning for all BLE devices for {timeout} seconds...")
    print("-" * 60)
    
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    
    mi_displays = []
    other_devices = []
    
    for device, adv_data in devices.values():
        info = {
            "name": device.name or "Unknown",
            "address": device.address,
            "rssi": adv_data.rssi,
            "service_uuids": list(adv_data.service_uuids) if adv_data.service_uuids else []
        }
        
        # Check if it's an MI Matrix Display
        if device.name and DEVICE_NAME in device.name:
            mi_displays.append(info)
        else:
            other_devices.append(info)
    
    # Print MI Matrix Displays first (the ones we care about)
    print("\n=== MI MATRIX DISPLAYS FOUND ===")
    if mi_displays:
        for d in mi_displays:
            print(f"\n  Name: {d['name']}")
            print(f"  MAC Address: {d['address']}")
            print(f"  Signal (RSSI): {d['rssi']} dBm")
            if d['service_uuids']:
                print(f"  Services: {d['service_uuids']}")
    else:
        print("  No MI Matrix Displays found.")
        print("  Make sure the display is powered on and in pairing mode.")
    
    # Print other devices
    print(f"\n=== OTHER BLE DEVICES ({len(other_devices)}) ===")
    for d in sorted(other_devices, key=lambda x: x['rssi'], reverse=True)[:10]:
        print(f"  {d['name']:30} | {d['address']} | RSSI: {d['rssi']}")
    
    if len(other_devices) > 10:
        print(f"  ... and {len(other_devices) - 10} more devices")
    
    return mi_displays


async def detailed_scan(mac_address: str = None, timeout: int = 15):
    """
    Detailed scan for a specific device or all MI displays.
    Shows services and characteristics.
    """
    from bleak import BleakClient
    
    if not mac_address:
        # First find displays
        print("Finding MI Matrix Displays...")
        displays = await scan_all_ble_devices(timeout=10)
        if not displays:
            return
        mac_address = displays[0]['address']
        print(f"\nUsing first found display: {mac_address}")
    
    print(f"\nConnecting to {mac_address} for detailed scan...")
    
    try:
        async with BleakClient(mac_address, timeout=timeout) as client:
            if client.is_connected:
                print(f"Connected successfully!")
                print("\n=== SERVICES AND CHARACTERISTICS ===")
                
                for service in client.services:
                    print(f"\nService: {service.uuid}")
                    print(f"  Description: {service.description}")
                    
                    for char in service.characteristics:
                        props = ", ".join(char.properties)
                        print(f"    Characteristic: {char.uuid}")
                        print(f"      Properties: {props}")
                        print(f"      Handle: {char.handle}")
                
                # Specifically check for the FFD0/FFD1 we expect
                print("\n=== KEY UUIDS FOR MI MATRIX ===")
                print(f"  Expected Service: {SERVICE_UUID}")
                print(f"  Expected Characteristic: 0000ffd1-0000-1000-8000-00805f9b34fb")
                
            else:
                print("Failed to connect.")
                
    except Exception as e:
        print(f"Connection error: {e}")


async def continuous_scan(duration: int = 60):
    """
    Continuous scan that shows devices as they appear.
    Useful for finding displays that take time to advertise.
    """
    found_displays = {}
    
    def callback(device, adv_data):
        if device.name and DEVICE_NAME in device.name:
            if device.address not in found_displays:
                found_displays[device.address] = device
                print(f"\n*** FOUND MI DISPLAY ***")
                print(f"    Name: {device.name}")
                print(f"    MAC: {device.address}")
                print(f"    RSSI: {adv_data.rssi} dBm")
        else:
            # Print a dot for other devices to show scanning is active
            print(".", end="", flush=True)
    
    print(f"Continuous scanning for {duration} seconds...")
    print("Looking for MI Matrix Display devices...")
    print("(dots = other BLE devices detected)")
    
    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    await asyncio.sleep(duration)
    await scanner.stop()
    
    print(f"\n\nScan complete. Found {len(found_displays)} MI displays:")
    for addr, dev in found_displays.items():
        print(f"  {dev.name}: {addr}")
    
    return list(found_displays.keys())


def save_addresses(addresses: list, filename: str = "display_addresses.txt"):
    """Save found addresses to file for later use."""
    with open(filename, 'w') as f:
        for addr in addresses:
            f.write(f"{addr}\n")
    print(f"Saved {len(addresses)} addresses to {filename}")


if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("MI Matrix Display Bluetooth Scanner")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        
        if cmd == "detailed" and len(sys.argv) > 2:
            # Detailed scan of specific MAC
            asyncio.run(detailed_scan(sys.argv[2]))
        elif cmd == "continuous":
            # Long continuous scan
            duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
            asyncio.run(continuous_scan(duration))
        elif cmd == "help":
            print("""
Usage:
  python bt_scanner.py              - Quick scan (10 sec)
  python bt_scanner.py continuous   - Continuous scan (60 sec)
  python bt_scanner.py continuous 120 - Continuous scan for 120 sec
  python bt_scanner.py detailed AA:BB:CC:DD:EE:FF - Detailed scan of MAC
            """)
        else:
            print(f"Unknown command: {cmd}")
    else:
        # Default: quick scan
        displays = asyncio.run(scan_all_ble_devices(timeout=10))
        
        if displays:
            print("\n" + "=" * 60)
            print("TO USE THESE DISPLAYS:")
            print("=" * 60)
            for d in displays:
                print(f"  MAC Address: {d['address']}")
            print("\nCopy the MAC address and use with api_server.py:")
            print('  curl -X POST http://localhost:5000/displays/MAC/connect')
