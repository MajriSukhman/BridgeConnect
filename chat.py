#!/usr/bin/env python3
"""
LAN Chat — run on two computers on the same WiFi. No config needed.

Usage:
    python chat.py
    python chat.py YourName
"""

import socket, threading, sys, time, os

DISC_PORT  = 55123   # UDP discovery
CHAT_PORT  = 55124   # TCP chat  (separate port = no race condition)
BROADCAST  = "255.255.255.255"
BUFFER     = 4096


def get_local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"


# ── Discovery ─────────────────────────────────────────────────────────────────

def broadcaster(name, stop):
    """Sends UDP hellos every second until stop is set."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while not stop.is_set():
        try:
            s.sendto(f"HELLO:{name}".encode(), (BROADCAST, DISC_PORT))
        except Exception:
            pass
        time.sleep(1)
    s.close()


def find_peer(my_ip, name):
    """Blocks until another machine's hello is heard. Returns (peer_ip, peer_name)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass
    s.bind(("", DISC_PORT))
    s.settimeout(0.5)
    while True:
        try:
            data, addr = s.recvfrom(BUFFER)
            peer_ip = addr[0]
            if peer_ip == my_ip:
                continue
            msg = data.decode(errors="ignore")
            if msg.startswith("HELLO:"):
                peer_name = msg[6:].strip() or peer_ip
                s.close()
                return peer_ip, peer_name
        except socket.timeout:
            continue


# ── TCP handshake: BOTH sides listen + connect simultaneously ─────────────────
# Whichever connection succeeds first wins. This eliminates all timing issues.

def tcp_connect(peer_ip, result, stop):
    """Try to connect to peer. On success put socket in result[0]."""
    while not stop.is_set():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((peer_ip, CHAT_PORT))
            s.settimeout(None)
            if not stop.is_set():
                result[0] = ('connect', s)
                stop.set()
            else:
                s.close()
            return
        except Exception:
            pass
        time.sleep(0.5)


def tcp_listen(result, stop):
    """Listen for an incoming connection. On success put socket in result[1]."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass
    srv.bind(("", CHAT_PORT))
    srv.listen(1)
    srv.settimeout(0.5)
    while not stop.is_set():
        try:
            conn, _ = srv.accept()
            if not stop.is_set():
                result[1] = ('listen', conn)
                stop.set()
            else:
                conn.close()
            break
        except socket.timeout:
            continue
    srv.close()


def establish_connection(peer_ip):
    """
    Both sides run this. Returns a connected socket.
    No 'who is server' logic — race to connect, first wins.
    """
    result  = [None, None]   # [0]=connect winner, [1]=listen winner
    stop    = threading.Event()

    t_conn   = threading.Thread(target=tcp_connect, args=(peer_ip, result, stop), daemon=True)
    t_listen = threading.Thread(target=tcp_listen,  args=(result, stop),          daemon=True)

    t_conn.start()
    t_listen.start()
    t_conn.join()
    t_listen.join()

    # Return whichever succeeded
    return (result[0] or result[1])[1]


# ── Chat ──────────────────────────────────────────────────────────────────────

def receiver(conn, peer_name, stop):
    while not stop.is_set():
        try:
            data = conn.recv(BUFFER)
            if not data:
                print(f"\n  [{peer_name} disconnected]")
                stop.set()
                break
            msg = data.decode(errors="ignore").strip()
            if msg == "/quit":
                print(f"\n  [{peer_name} left the chat]")
                stop.set()
                break
            print(f"\r\033[K  {peer_name}: {msg}")
            print("  You: ", end="", flush=True)
        except Exception:
            if not stop.is_set():
                print("\n  [Connection lost]")
            stop.set()
            break


def chat_loop(conn, my_name, peer_name):
    stop = threading.Event()
    threading.Thread(target=receiver, args=(conn, peer_name, stop), daemon=True).start()

    print(f"\n  {'─'*40}")
    print(f"  Connected to {peer_name}!")
    print(f"  Type a message and press Enter. /quit to exit.")
    print(f"  {'─'*40}\n")

    try:
        while not stop.is_set():
            print("  You: ", end="", flush=True)
            line = sys.stdin.readline()
            if stop.is_set():
                break
            line = line.rstrip("\n")
            if line.lower() in ("/quit", "/exit", "/q"):
                try: conn.sendall(b"/quit")
                except: pass
                break
            if line:
                try:
                    conn.sendall(line.encode())
                except Exception:
                    print("  [Send failed]")
                    break
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        try: conn.close()
        except: pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    name   = (sys.argv[1] if len(sys.argv) > 1 else input("Your name: ").strip()) or "Anon"
    my_ip  = get_local_ip()

    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n  LAN Chat  •  {name}  •  {my_ip}")
    print(f"  Waiting for someone on the same WiFi…\n")

    # 1. Discover peer
    stop_bc = threading.Event()
    threading.Thread(target=broadcaster, args=(name, stop_bc), daemon=True).start()

    peer_ip, peer_name = find_peer(my_ip, name)
    stop_bc.set()
    print(f"  Found {peer_name} ({peer_ip}) — connecting…")

    # Small delay so both sides finish discovery before TCP starts
    time.sleep(0.5)

    # 2. Connect (both sides do this simultaneously — no server/client distinction)
    try:
        conn = establish_connection(peer_ip)
    except Exception as e:
        print(f"  Failed to connect: {e}")
        return

    # 3. Chat
    chat_loop(conn, name, peer_name)
    print("\n  Bye!\n")


if __name__ == "__main__":
    main()