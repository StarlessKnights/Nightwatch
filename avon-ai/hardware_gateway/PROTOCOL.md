# Gateway / Arduino protocol

The canonical serial contract and fixtures are in [`../hardware/protocol`](../hardware/protocol). The gateway emits newline-delimited JSON at 115200 baud, ten packets per second per assigned board:

```json
{"v":1,"seq":1,"dev":1,"pump":"P-201","state":1,"w":1000,"available":1,"lvl":600,"cap":1000}
```

Device 1 is P-201 and displays T-101 level. Device 2 is P-203 and Device 3 is P-204; both display T-104 level. Effective health (`eff_health`) determines `w`. The firmware holds a trip triangle, alternates waves and triangle below 50% health, and holds an X when unavailable. Unavailable wins over trip. The gateway selects each serial link by the firmware HELLO identity, independent of port order.
