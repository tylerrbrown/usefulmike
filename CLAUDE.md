# UsefulMike

Real-time collaborative app where users fight over Mike's usefulness percentage via WebSockets.

## Tech Stack
- **Backend**: Python 3 + `websockets` library (only dependency), asyncio, SQLite
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
- Variable-speed combo system: rapid pressing accelerates increment (1% → up to 10%)
- Vertical gauge bar with red→green color gradient
- Persistent value + activity feed (SQLite)
- Connected user count
- Keyboard support (arrow keys, W/S)
- Auto-reconnect on disconnect

## Deployment (EC2)
```bash
# Copy to server
scp -r . ec2:/opt/usefulmike/

# Install dependency
pip3 install websockets

# Enable service
sudo cp usefulmike.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now usefulmike

# HAProxy backend needed:
#   backend web-usefulmike
#       server usefulmike 127.0.0.1:5051 check fall 3 rise 1
```

## WebSocket Protocol
| Direction | Message |
|-----------|---------|
| Client→Server | `{"action": "up"}` or `{"action": "down"}` |
| Server→Client | `{"type": "state", "value": N, "users": N, "feed": [...]}` |
| Server→Client | `{"type": "update", "value": N, "oldValue": N, "delta": N, "combo": N, "direction": "up"/"down", "users": N}` |
| Server→Client | `{"type": "users", "users": N}` |

## Combo System
- Gap < 300ms between presses: combo increments (max 10)
- Gap 300ms–1s: combo holds
- Gap > 1s: combo resets to 1
- Increment = combo level (so x5 combo = 5% per press)
