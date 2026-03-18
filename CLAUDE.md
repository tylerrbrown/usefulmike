# UsefulMike

Real-time collaborative app where users fight over Mike's usefulness percentage via WebSockets.

## Tech Stack
- **Backend**: Python 3 + `websockets` 16.0 (only dependency), asyncio, SQLite
- **Frontend**: Vanilla HTML/CSS/JS, WebSocket API
- **Database**: SQLite with WAL mode (`usefulmike.db`)

## Running Locally
```bash
python app.py  # http://localhost:5051
```

## Port
- **5051** (configurable via `PORT` env var)

## Features
- Real-time WebSocket sync across all connected clients
- Fixed 1% increment per press
- Full-width vertical gauge bar with red→green color gradient, percentage centered inside
- Persistent value (SQLite)
- Connected user count
- Keyboard support (arrow keys, W/S)
- Auto-reconnect on disconnect

## Deployment (EC2)
```bash
git config --global --add safe.directory /opt/usefulmike
cd /opt/usefulmike && git pull && systemctl restart usefulmike
```

## WebSocket Protocol
| Direction | Message |
|-----------|---------|
| Client→Server | `{"action": "up"}` or `{"action": "down"}` |
| Server→Client | `{"type": "state", "value": N, "users": N}` |
| Server→Client | `{"type": "update", "value": N, "direction": "up"/"down", "users": N}` |
| Server→Client | `{"type": "users", "users": N}` |
