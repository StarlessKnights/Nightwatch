# AVON Arduino serial protocol v1 (pump nodes)

USB CDC serial is 115200 baud, 8-N-1. Send one newline-terminated JSON packet at 5–10 Hz. Each UNO accepts only packets with `v:1`, its compiled `dev`, and its assigned pump name.

## Fixed Arduino assignments

| PlatformIO environment | `dev` | Pump | Display |
|---|---:|---|---|
| `device_tank` | 1 | P-201 | dedicated P-201 status |
| `device_pipeline` | 2 | P-203 | dedicated P-203 status |
| `device_treatment` | 3 | P-204 | dedicated P-204 status |

The historical environment names are retained for PlatformIO compatibility; all three are now pump displays.

## Packet

```json
{"v":1,"seq":310,"dev":1,"pump":"P-201","state":1,"w":1000,"lvl":600,"cap":1000,"available":1}
```

- `state`: `0` stopped, `1` running, `2` starting, `3` degraded, `4` tripped, `5` unavailable.
- `w`: effective pump health/wear score in thousandths (`1000` = 100%, `500` = 50%). Strictly below `500` activates caution.
- `lvl` / `cap`: associated tank level and capacity. Normal operation renders animated waves filled from the bottom to this percentage.
- `available`: `0` means unavailable. Unavailable has priority over all other visual states.

## Visual priority

1. Unavailable (`available:0` or `state:5`): solid X.
2. Tripped (`state:4`) or `w < 500`: alternate between the live water waves and a caution triangle with exclamation mark.
3. Otherwise: live animated water waves at the reported level.

The board emits `AVON|HELLO|v=1|dev=N|profile=pump|fw=0.2.0-pump` at startup. Wrong pump names, device IDs, versions, malformed, or oversized packets are ignored; parser errors pulse the onboard LED. Telemetry goes stale after 1500 ms.
