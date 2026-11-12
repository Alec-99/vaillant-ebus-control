"""Whitelisted, read-only localhost ebusd TCP diagnostics. No write API."""
from __future__ import annotations
import socket

ALLOWED = {"FlowTemp", "ReturnTemp", "FlowTempDesired", "Flame", "WP",
           "Statenumber", "ModulationDesired", "RemainingBoilerblocktime"}


def request(command: str, host: str = "127.0.0.1", port: int = 8888) -> str:
    if command not in ALLOWED:
        raise ValueError("Unapproved ebusd request")
    with socket.create_connection((host, port), timeout=2.0) as connection:
        connection.settimeout(2.0)
        connection.sendall(f"read -c bai {command}\n".encode("ascii"))
        chunks = []
        size = 0
        while size < 4096:
            part = connection.recv(min(512, 4096 - size))
            if not part:
                break
            chunks.append(part)
            size += len(part)
            if b"\n" in part:
                break
        return b"".join(chunks).decode("utf-8", errors="replace").strip()


def safe_value(command: str, raw: str) -> str | None:
    if command not in ALLOWED:
        raise ValueError("Unapproved register")
    value = raw.split(";")[0].strip()
    if not value or value.startswith("ERR:") or "cutoff" in raw or raw == "-":
        return None
    return value
