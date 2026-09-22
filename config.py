"""Persistent bridge configuration.

The installer (Inno Setup) asks for IP + printer name and writes
``config.ini`` to a location that survives Velopack updates:

* Windows: ``%ProgramData%\\OdooPrinter\\config.ini``
* Linux/CI: ``$XDG_CONFIG_HOME/odoo-printer/config.ini`` or ``~/.config``

Priority: config.ini > environment variables > built-in defaults.
"""

from __future__ import annotations

import configparser
import ipaddress
import os
from dataclasses import dataclass

APP_ID = "OdooPrinter"
SERVICE_NAME = "OdooPrinter"
CONFIG_FILENAME = "config.ini"
LOG_FILENAME = "bridge.log"

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5000
DEFAULT_PRINTER_NAME = "POS-80"
DEFAULT_PRINTER_WIDTH_DOTS = 576
DEFAULT_RASTER_SCALE_X = 1.0
DEFAULT_RASTER_SCALE_Y = 1.50
DEFAULT_END_BLANK_LINES = 2
DEFAULT_UPDATE_URL = os.getenv(
    "ODOO_PRINTER_UPDATE_URL",
    "https://github.com/anomalyco/python-odoo-script/releases/latest/download",
)
DEFAULT_UPDATE_INTERVAL_HOURS = 4.0


def config_dir() -> str:
    program_data = os.getenv("PROGRAMDATA")
    if program_data:  # Windows service location, survives Velopack updates.
        return os.path.join(program_data, APP_ID)
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return os.path.join(xdg, "odoo-printer")
    return os.path.join(os.path.expanduser("~"), ".config", "odoo-printer")


def config_path() -> str:
    return os.path.join(config_dir(), CONFIG_FILENAME)


def log_path() -> str:
    return os.path.join(config_dir(), LOG_FILENAME)


@dataclass
class BridgeConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    printer_name: str = DEFAULT_PRINTER_NAME
    printer_width_dots: int = DEFAULT_PRINTER_WIDTH_DOTS
    raster_scale_x: float = DEFAULT_RASTER_SCALE_X
    raster_scale_y: float = DEFAULT_RASTER_SCALE_Y
    end_blank_lines: int = DEFAULT_END_BLANK_LINES
    update_url: str = DEFAULT_UPDATE_URL
    update_interval_hours: float = DEFAULT_UPDATE_INTERVAL_HOURS


def validate_host(host: str) -> str:
    """Accept '0.0.0.0' or any valid IPv4/IPv6 address. Raises ValueError."""
    value = (host or "").strip()
    if not value:
        raise ValueError("IP cannot be empty")
    try:
        ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(f"Invalid IP address: {value!r}") from exc
    return value


def validate_printer_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        raise ValueError("Printer name cannot be empty")
    return value


def load_config(path: str | None = None) -> BridgeConfig:
    """Load config.ini (if present) and apply env overrides."""
    cfg = BridgeConfig()
    ini_path = path or config_path()

    parser = configparser.ConfigParser()
    if ini_path and os.path.isfile(ini_path):
        parser.read(ini_path, encoding="utf-8")
        section = parser["bridge"] if "bridge" in parser else {}
        cfg.host = section.get("host", cfg.host)
        cfg.port = int(section.get("port", cfg.port))
        cfg.printer_name = section.get("printer_name", cfg.printer_name)
        cfg.printer_width_dots = int(
            section.get("printer_width_dots", cfg.printer_width_dots)
        )
        cfg.raster_scale_x = float(
            section.get("raster_scale_x", cfg.raster_scale_x)
        )
        cfg.raster_scale_y = float(
            section.get("raster_scale_y", cfg.raster_scale_y)
        )
        cfg.end_blank_lines = int(
            section.get("end_blank_lines", cfg.end_blank_lines)
        )
        cfg.update_url = section.get("update_url", cfg.update_url)
        cfg.update_interval_hours = float(
            section.get("update_interval_hours", cfg.update_interval_hours)
        )

    # Env overrides (useful for dev / docker).
    if os.getenv("POS_BIND_IP"):
        cfg.host = os.getenv("POS_BIND_IP", cfg.host)
    if os.getenv("POS_PORT"):
        cfg.port = int(os.getenv("POS_PORT", cfg.port))
    if os.getenv("POS_PRINTER_NAME"):
        cfg.printer_name = os.getenv("POS_PRINTER_NAME", cfg.printer_name)
    if os.getenv("POS_PRINTER_WIDTH_DOTS"):
        cfg.printer_width_dots = int(
            os.getenv("POS_PRINTER_WIDTH_DOTS", cfg.printer_width_dots)
        )
    if os.getenv("POS_RASTER_SCALE_X"):
        cfg.raster_scale_x = float(
            os.getenv("POS_RASTER_SCALE_X", cfg.raster_scale_x)
        )
    if os.getenv("POS_RASTER_SCALE_Y"):
        cfg.raster_scale_y = float(
            os.getenv("POS_RASTER_SCALE_Y", cfg.raster_scale_y)
        )
    if os.getenv("POS_END_BLANK_LINES"):
        cfg.end_blank_lines = int(
            os.getenv("POS_END_BLANK_LINES", cfg.end_blank_lines)
        )
    if os.getenv("ODOO_PRINTER_UPDATE_URL"):
        cfg.update_url = os.getenv(
            "ODOO_PRINTER_UPDATE_URL", cfg.update_url
        )

    return cfg


def save_config(cfg: BridgeConfig, path: str | None = None) -> str:
    """Validate and persist config.ini. Returns the path written."""
    cfg.host = validate_host(cfg.host)
    cfg.printer_name = validate_printer_name(cfg.printer_name)
    if not 1 <= cfg.port <= 65535:
        raise ValueError("Port must be 1-65535")

    ini_path = path or config_path()
    os.makedirs(os.path.dirname(ini_path), exist_ok=True)
    parser = configparser.ConfigParser()
    parser["bridge"] = {
        "host": cfg.host,
        "port": str(cfg.port),
        "printer_name": cfg.printer_name,
        "printer_width_dots": str(cfg.printer_width_dots),
        "raster_scale_x": str(cfg.raster_scale_x),
        "raster_scale_y": str(cfg.raster_scale_y),
        "end_blank_lines": str(cfg.end_blank_lines),
        "update_url": cfg.update_url,
        "update_interval_hours": str(cfg.update_interval_hours),
    }
    with open(ini_path, "w", encoding="utf-8") as fh:
        parser.write(fh)
    return ini_path
