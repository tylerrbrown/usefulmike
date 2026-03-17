#!/usr/bin/env python3
"""UsefulMike — Real-time usefulness percentage battle via WebSockets."""

import asyncio
import json
import os
import sqlite3

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 5051))
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usefulmike.db")
INITIAL_VALUE = 50

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        )
    """)
    cur = conn.execute("SELECT value FROM state WHERE key='percentage'")
    if cur.fetchone() is None:
        conn.execute("INSERT INTO state (key, value) VALUES ('percentage', ?)", (INITIAL_VALUE,))
    conn.commit()
    conn.close()


def get_percentage():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT value FROM state WHERE key='percentage'")
    val = cur.fetchone()[0]
    conn.close()
    return val


def set_percentage(value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE state SET value=? WHERE key='percentage'", (value,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# WebSocket state
# ---------------------------------------------------------------------------
clients = set()

# ---------------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------------

async def broadcast(message):
    data = json.dumps(message)
    dead = set()
    for ws in clients:
        try:
            await ws.send(data)
        except Exception:
            dead.add(ws)
    for ws in dead:
        clients.discard(ws)


async def broadcast_users():
    await broadcast({"type": "users", "users": len(clients)})


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

INDEX_HTML = None

def load_index():
    global INDEX_HTML
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(html_path, "rb") as f:
        INDEX_HTML = f.read()


async def process_request(connection, request):
    if request.path in ("/", "/index.html"):
        if INDEX_HTML is None:
            load_index()
        return Response(
            200, "OK",
            Headers([
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(INDEX_HTML))),
                ("Cache-Control", "no-cache"),
            ]),
            INDEX_HTML,
        )
    if request.path == "/favicon.ico":
        return Response(204, "No Content", Headers(), b"")
    return None


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------

async def handler(websocket):
    clients.add(websocket)

    value = get_percentage()
    await websocket.send(json.dumps({
        "type": "state",
        "value": value,
        "users": len(clients),
    }))
    await broadcast_users()

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action = msg.get("action")
            if action not in ("up", "down"):
                continue

            old_val = get_percentage()

            if action == "up":
                new_val = min(100, old_val + 1)
            else:
                new_val = max(0, old_val - 1)

            if new_val != old_val:
                set_percentage(new_val)

            await broadcast({
                "type": "update",
                "value": new_val,
                "direction": action,
                "users": len(clients),
            })
    except Exception:
        pass
    finally:
        clients.discard(websocket)
        await broadcast_users()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    init_db()
    load_index()
    print(f"UsefulMike running on http://{HOST}:{PORT}")
    async with serve(handler, HOST, PORT, process_request=process_request) as server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
