# Three-pump Arduino gateway and demo

The tested firmware lives in [`../hardware`](../hardware). Flash `device_tank` to P-201 (Device 1), `device_pipeline` to P-203 (Device 2), and `device_treatment` to P-204 (Device 3). The old `firmware_reference` project has been retired to avoid incompatible flashes.

From `avon-ai`, install `backend/requirements.txt` and `hardware_gateway/requirements-hw.txt`, then run the backend:

```sh
cd backend && python -m uvicorn app.main:app --port 8000
```

In another terminal:

```sh
cd avon-ai
python hardware_gateway/bridge.py --config hardware_gateway/config.json
```

Open `http://127.0.0.1:8090` for grouped Trip, Unavailable, Wear, and Reset controls for each pump. `--dry-run` runs the same control page without opening serial ports. The gateway reads each board's `AVON|HELLO|v=1|dev=N|profile=pump` greeting and sends each packet only to its assigned board. It retries disconnected boards every three seconds. Backend state is streamed over `/ws/sim`; packets continue at 10 Hz while the simulation is paused.

On macOS, USB ports usually look like `/dev/cu.usbmodem...`. Stop any fixture sender or serial monitor before starting the bridge, since each port can be opened by one process at a time.
