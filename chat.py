"""
LAN Chat — just run this on two computers on the same WiFi.
No setup, no config, no internet needed.

Usage:
    python chat.py
    python chat.py YourName
"""

import socket
import threading
import sys
import time
import os

# ── Config ────────────────────────────────────────────────────────────────────
PORT        = 55123          # same on both sides
BROADCAST   = "255.255.255.255"
DISCOVER_IN = 2              # seconds to wait for a peer
BUFFER      = 4096
# ─────────────────────────────────────────────────────────────────────────────


def get_local_ip():
    """Best-effort: find the LAN IP (not 127.0.0.1)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"


def clear():
    os.system("cls" if os.name == "nt" else "clear")


# ── Discovery (UDP broadcast) ─────────────────────────────────────────────────

def broadcast_presence(name: str, stop_event: threading.Event):
    """Keeps broadcasting 'I am here' until a peer is found."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        while not stop_event.is_set():
            try:
                s.sendto(f"HELLO:{name}".encode(), (BROADCAST, PORT))
            except Exception:
                pass
            time.sleep(1)


def listen_for_peer(my_ip: str, name: str) -> tuple[str, str]:
    """
    Returns (peer_ip, peer_name) of the first OTHER machine that says hello.
    Also responds to their hellos so they can find us.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind(("", PORT))
        s.settimeout(0.5)
        while True:
            try:
                data, addr = s.recvfrom(BUFFER)
                msg = data.decode(errors="ignore")
                peer_ip = addr[0]
                if peer_ip == my_ip:          # ignore our own broadcast
                    continue
                if msg.startswith("HELLO:"):
                    peer_name = msg[6:] or peer_ip
                    # Reply immediately so the other side can find us too
                    s.sendto(f"HELLO:{name}".encode(), (peer_ip, PORT))
                    return peer_ip, peer_name
            except socket.timeout:
                continue


# ── TCP chat ──────────────────────────────────────────────────────────────────

def receive_messages(conn: socket.socket, peer_name: str, stop_event: threading.Event):
    """Background thread: print incoming messages."""
    while not stop_event.is_set():
        try:
            data = conn.recv(BUFFER)
            if not data:
                print(f"\n[{peer_name} disconnected]")
                stop_event.set()
                break
            msg = data.decode(errors="ignore").strip()
            # Move cursor up, print peer message, reprint prompt
            print(f"\r\033[K{peer_name}: {msg}")
            print("You: ", end="", flush=True)
        except Exception:
            if not stop_event.is_set():
                print(f"\n[Connection lost]")
            stop_event.set()
            break


def chat_loop(conn: socket.socket, my_name: str, peer_name: str):
    """Main send/receive loop."""
    stop = threading.Event()
    t = threading.Thread(target=receive_messages, args=(conn, peer_name, stop), daemon=True)
    t.start()

    print(f"\n{'─'*45}")
    print(f"  Connected to {peer_name}!  Type and press Enter.")
    print(f"  Type /quit  to leave.")
    print(f"{'─'*45}\n")

    try:
        while not stop.is_set():
            print("You: ", end="", flush=True)
            line = sys.stdin.readline()
            if stop.is_set():
                break
            line = line.rstrip("\n")
            if line.lower() in ("/quit", "/exit", "/q"):
                conn.sendall(b"/quit")
                break
            if line:
                try:
                    conn.sendall(line.encode())
                except Exception:
                    print("[Send failed — connection lost]")
                    break
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        try:
            conn.close()
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    name = sys.argv[1] if len(sys.argv) > 1 else input("Your name: ").strip() or "Anon"
    my_ip = get_local_ip()

    clear()
    print(f"\n  LAN Chat  •  {name}  •  {my_ip}")
    print("  Looking for someone on the same WiFi…\n")

    # ── Phase 1: discover a peer ──────────────────────────────────────────────
    stop_broadcast = threading.Event()
    broadcaster = threading.Thread(
        target=broadcast_presence, args=(name, stop_broadcast), daemon=True
    )
    broadcaster.start()

    peer_ip, peer_name = listen_for_peer(my_ip, name)
    stop_broadcast.set()

    print(f"  Found {peer_name} at {peer_ip} — connecting…")

    # ── Phase 2: establish TCP (lower IP = server) ────────────────────────────
    am_server = my_ip < peer_ip      # deterministic: one side listens, other connects

    conn: socket.socket | None = None

    if am_server:
        # We listen; the other side will connect to us
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("", PORT))
            srv.listen(1)
            srv.settimeout(10)
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                print("  Timed out waiting for TCP connection. Try again.")
                return
    else:
        # We connect to them; give the server a moment to start listening
        time.sleep(0.3)
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        for attempt in range(10):
            try:
                conn.connect((peer_ip, PORT))
                break
            except ConnectionRefusedError:
                time.sleep(0.5)
        else:
            print("  Could not connect. Try again.")
            return

    # ── Phase 3: chat ─────────────────────────────────────────────────────────
    try:
        chat_loop(conn, name, peer_name)
    finally:
        conn.close()

    print("\n  Bye!\n")


if __name__ == "__main__":
    main()