#!/usr/bin/env python3
"""UsefulMike — Real-time usefulness percentage battle via WebSockets."""

import asyncio
import json
import os
import sqlite3
import time

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
MAX_ACTIVITY = 100  # rows kept in activity table
FEED_LIMIT = 30     # entries sent to client on connect

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL,
            old_value INTEGER NOT NULL,
            new_value INTEGER NOT NULL,
            combo INTEGER NOT NULL DEFAULT 1,
            timestamp REAL NOT NULL
        )
    """)
    # Seed initial value if missing
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


def log_activity(direction, old_val, new_val, combo):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO activity (direction, old_value, new_value, combo, timestamp) VALUES (?,?,?,?,?)",
        (direction, old_val, new_val, combo, time.time()),
    )
    # Prune old entries
    conn.execute("""
        DELETE FROM activity WHERE id NOT IN (
            SELECT id FROM activity ORDER BY id DESC LIMIT ?
        )
    """, (MAX_ACTIVITY,))
    conn.commit()
    conn.close()


def get_recent_activity(limit=FEED_LIMIT):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT direction, old_value, new_value, combo, timestamp FROM activity ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# WebSocket state
# ---------------------------------------------------------------------------
clients = set()
combo_state = {}  # ws -> {"last_press": float, "combo": int}

# ---------------------------------------------------------------------------
# Combo logic
# ---------------------------------------------------------------------------

def compute_combo(ws):
    now = time.time()
    state = combo_state.get(id(ws))
    if state is None:
        combo_state[id(ws)] = {"last_press": now, "combo": 1}
        return 1

    gap = now - state["last_press"]
    if gap < 0.3:
        state["combo"] = min(state["combo"] + 1, 10)
    elif gap >= 1.0:
        state["combo"] = 1
    # else: keep current combo

    state["last_press"] = now
    return state["combo"]


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
        combo_state.pop(id(ws), None)


async def broadcast_users():
    await broadcast({"type": "users", "users": len(clients)})


# ---------------------------------------------------------------------------
# HTTP handler — serves index.html and static assets
# ---------------------------------------------------------------------------

INDEX_HTML = None

def load_index():
    global INDEX_HTML
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(html_path, "rb") as f:
        INDEX_HTML = f.read()


async def process_request(connection, request):
    """Intercept HTTP requests to serve the HTML page."""
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
    # All other paths proceed to WebSocket handshake
    return None


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------

async def handler(websocket):
    clients.add(websocket)
    combo_state[id(websocket)] = {"last_press": 0.0, "combo": 1}

    # Send current state + recent feed
    value = get_percentage()
    feed = get_recent_activity()
    await websocket.send(json.dumps({
        "type": "state",
        "value": value,
        "users": len(clients),
        "feed": feed,
    }))
    # Notify others about new user count
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

            combo = compute_combo(websocket)
            old_val = get_percentage()

            if action == "up":
                new_val = min(100, old_val + combo)
            else:
                new_val = max(0, old_val - combo)

            if new_val != old_val:
                set_percentage(new_val)
                log_activity(action, old_val, new_val, combo)

            await broadcast({
                "type": "update",
                "value": new_val,
                "oldValue": old_val,
                "delta": combo if action == "up" else -combo,
                "combo": combo,
                "direction": action,
                "users": len(clients),
            })
    except Exception:
        pass
    finally:
        clients.discard(websocket)
        combo_state.pop(id(websocket), None)
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
