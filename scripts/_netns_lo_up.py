"""Bring the loopback interface up inside a fresh network namespace (Linux only).

Used by verify_offline.py when ``ip`` is not installed. Equivalent to
``ip link set lo up``.
"""
import fcntl
import socket
import struct

SIOCGIFFLAGS, SIOCSIFFLAGS, IFF_UP = 0x8913, 0x8914, 0x1

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    ifreq = struct.pack("16sH14s", b"lo", 0, b"\0" * 14)
    flags = struct.unpack("16sH14s", fcntl.ioctl(s.fileno(), SIOCGIFFLAGS, ifreq))[1]
    fcntl.ioctl(s.fileno(), SIOCSIFFLAGS, struct.pack("16sH14s", b"lo", flags | IFF_UP, b"\0" * 14))
