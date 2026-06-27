#!/usr/bin/env python3
"""
LAN Chat Client — connect to whoever is running server.py.
Usage:
    python client.py <server-ip>
    python client.py <server-ip> YourName
"""

import socket, threading, sys, os

PORT   = 55124
BUFFER = 4096


def receiver(conn, stop):
    while not stop.is_set():
        try:
            data = conn.recv(BUFFER)
            if not data:
                print("\n  [Server closed the connection]")
                stop.set()
                break
            msg = data.decode(errors="ignore").strip()
            print(f"\r\033[K{msg}")
            print("  You: ", end="", flush=True)
        except Exception:
            if not stop.is_set():
                print("\n  [Disconnected]")
            stop.set()
            break


def main():
    if len(sys.argv) < 2:
        server_ip = input("  Server IP: ").strip()
    else:
        server_ip = sys.argv[1]

    if len(sys.argv) >= 3:
        name = sys.argv[2]
    else:
        name = input("  Your name: ").strip() or "Anon"

    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n  ╔══════════════════════════════════════╗")
    print(f"  ║        LAN Chat — CLIENT             ║")
    print(f"  ╚══════════════════════════════════════╝")
    print(f"\n  Connecting to {server_ip}:{PORT} as {name}…")

    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.connect((server_ip, PORT))
    except Exception as e:
        print(f"\n  Could not connect: {e}")
        print(f"  Make sure server.py is running on {server_ip}\n")
        return

    # Send name first
    conn.sendall(name.encode())

    stop = threading.Event()
    threading.Thread(target=receiver, args=(conn, stop), daemon=True).start()

    print(f"  Type /quit to leave.\n")
    print(f"  {'─'*40}\n")

    try:
        while not stop.is_set():
            print("  You: ", end="", flush=True)
            line = sys.stdin.readline().rstrip("\n")
            if stop.is_set():
                break
            if line.lower() in ("/quit", "/exit", "/q"):
                conn.sendall(b"/quit")
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

    print("\n  Bye!\n")


if __name__ == "__main__":
    main()