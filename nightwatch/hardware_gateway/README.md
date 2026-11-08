# Three-pump Arduino gateway and demo

The tested firmware lives in [`../firmware`](../firmware). Flash `device_tank` to Device 1, `device_pipeline` to Device 2, and `device_treatment` to Device 3. The old `firmware_reference` project has been retired to avoid incompatible flashes.

From `nightwatch`, install `backend/requirements.txt` and `hardware_gateway/requirements-hw.txt`, then run the backend:

```sh
cd backend && python -m uvicorn app.main:app --port 8000
```

In another terminal:

```sh
cd nightwatch
python hardware_gateway/bridge.py --config hardware_gateway/config.json
```

Open `http://127.0.0.1:8090` for grouped Trip, Unavailable, Wear, and Reset controls. `--dry-run` runs the same control page without opening serial ports. In hardware mode the gateway fails loudly if `pyserial` or `websockets` is unavailable; it never silently simulates a connection. The gateway reads each board's `AVON|HELLO|v=2|dev=N|profile=...` greeting, broadcasts all node packets over every connected link, and lets firmware self-filter by its compiled device ID. It retries disconnected boards every three seconds. Backend state is streamed over `/ws/sim`; packets continue at 10 Hz while the simulation is paused.

On macOS, USB ports usually look like `/dev/cu.usbmodem...`. Stop any fixture sender or serial monitor before starting the bridge, since each port can be opened by one process at a time.
