"""
Configuration Manager for MI Matrix Display System
Handles persistent storage of device addresses and grid configuration.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

# Default config location
DEFAULT_CONFIG_PATH = Path.home() / ".mi_matrix_displays" / "config.json"


class ConfigManager:
    """Manages configuration and device address storage for MI Matrix Displays."""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.config: Dict = self._load_config()
    
    def _ensure_config_dir(self) -> None:
        """Create config directory if it doesn't exist."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self) -> Dict:
        """Load configuration from JSON file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return self._default_config()
    
    def _default_config(self) -> Dict:
        """Return default configuration structure."""
        return {
            "grid": {
                "rows": 4,
                "cols": 4,
                "enabled": False  # Start with single-display mode
            },
            "displays": {},  # MAC address -> display info
            "scan_timeout": 20,
            "connection_retry_count": 3,
            "update_interval_ms": 1000  # 1 second per display
        }
    
    def save(self) -> None:
        """Save current configuration to file."""
        self._ensure_config_dir()
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    # Display Management
    def add_display(self, mac_address: str, name: str = "", 
                    grid_position: Optional[int] = None) -> None:
        """
        Add or update a display in the configuration.
        
        Args:
            mac_address: Bluetooth MAC address
            name: Display name (default: auto-generated)
            grid_position: Position in 4x4 grid (0-15), None for unassigned
        """
        if not name:
            name = f"Display_{len(self.config['displays'])}"
        
        self.config["displays"][mac_address] = {
            "name": name,
            "grid_position": grid_position,
            "last_seen": None
        }
        self.save()
    
    def remove_display(self, mac_address: str) -> bool:
        """Remove a display from configuration."""
        if mac_address in self.config["displays"]:
            del self.config["displays"][mac_address]
            self.save()
            return True
        return False
    
    def get_display(self, mac_address: str) -> Optional[Dict]:
        """Get display info by MAC address."""
        return self.config["displays"].get(mac_address)
    
    def get_all_displays(self) -> Dict[str, Dict]:
        """Get all configured displays."""
        return self.config["displays"]
    
    def get_display_by_position(self, position: int) -> Optional[str]:
        """Get MAC address of display at grid position."""
        for mac, info in self.config["displays"].items():
            if info.get("grid_position") == position:
                return mac
        return None
    
    def set_grid_position(self, mac_address: str, position: int) -> bool:
        """
        Assign display to grid position (0-15 for 4x4 grid).
        
        Args:
            mac_address: Display MAC address
            position: Grid position (0-15)
        """
        if position < 0 or position > 15:
            return False
        
        # Clear any existing display at this position
        for mac, info in self.config["displays"].items():
            if info.get("grid_position") == position:
                info["grid_position"] = None
        
        if mac_address in self.config["displays"]:
            self.config["displays"][mac_address]["grid_position"] = position
            self.save()
            return True
        return False
    
    # Grid Settings
    def enable_grid_mode(self, enabled: bool = True) -> None:
        """Enable or disable 4x4 grid mode."""
        self.config["grid"]["enabled"] = enabled
        self.save()
    
    def is_grid_mode_enabled(self) -> bool:
        """Check if grid mode is enabled."""
        return self.config["grid"]["enabled"]
    
    def get_grid_dimensions(self) -> tuple:
        """Get grid dimensions (rows, cols)."""
        return (self.config["grid"]["rows"], self.config["grid"]["cols"])
    
    # Timing Settings
    def get_update_interval(self) -> int:
        """Get update interval in milliseconds."""
        return self.config.get("update_interval_ms", 1000)
    
    def set_update_interval(self, ms: int) -> None:
        """Set update interval in milliseconds."""
        self.config["update_interval_ms"] = max(100, ms)  # Min 100ms
        self.save()
    
    def get_scan_timeout(self) -> int:
        """Get BLE scan timeout in seconds."""
        return self.config.get("scan_timeout", 20)


# Singleton instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get or create singleton ConfigManager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
