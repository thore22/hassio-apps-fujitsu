"""Read and validate the add-on's LAN interface without changing host networking."""

import json
import os
from pathlib import Path
import re
import socket
import sys

DEFAULT_INTERFACE = "enp1s0"
OPTIONS_FILE = Path("/data/options.json")


def resolve_interface(options_file: Path = OPTIONS_FILE) -> str:
    # Keep AIRPLAY_INTERFACE for existing container-based installations.
    interface = os.environ.get("AIRPLAY_INTERFACE")
    if not interface:
        options = json.loads(options_file.read_text()) if options_file.exists() else {}
        if not isinstance(options, dict):
            raise ValueError("The app options must be a JSON object")
        interface = options.get("airplay_interface", DEFAULT_INTERFACE)
    # This name is embedded in shell, awk and libconfig generated files.
    # Restrict it to ordinary Linux interface names before interpolation.
    if not isinstance(interface, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,14}", interface):
        raise ValueError("airplay_interface must be a Linux interface name (1-15 letters, digits, _, . or -)")
    if interface == "lo":
        raise ValueError("airplay_interface must be a LAN interface, not loopback")
    try:
        socket.if_nametoindex(interface)
    except OSError as exc:
        available = ", ".join(name for _, name in socket.if_nameindex())
        raise ValueError(
            f"AirPlay interface '{interface}' does not exist; available: {available}. "
            "Set airplay_interface in the app Configuration tab and restart."
        ) from exc
    return interface


if __name__ == "__main__":
    try:
        print(resolve_interface())
    except (ValueError, OSError) as exc:
        print(f"[airplay2] Interface configuration error: {exc}", file=sys.stderr)
        sys.exit(1)
