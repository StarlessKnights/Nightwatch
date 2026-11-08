# Hardware acceptance record

Do not mark a physical scenario passed until it has been run on all three boards through the Pi gateway. Record date, firmware revision, backend scenario, observed result, and pass/fail below.

| Scenario | Expected visual behavior | Result / notes |
|---|---|---|
| Scene 1 normal | T-104 60%; P-203 running; P-204 stopped; PL-1 flowing; treatment normal | Pending physical run |
| Scene 2 degraded | P-203 degraded; PL-1 slows; H/HH appears; standby start then recovery | Pending physical run |
| Scene 4 trip | Duty X; flow stops; standby pulse; flow resumes; second trip visible | Pending physical run |
| Scene 5 treatment constraint | TRT barrier/backflow; PL downstream limit marker | Pending physical run |
| Scene 6 interlock only | HH and interlock overlay remain visible with engine disabled | Pending physical run |
| Scene 3 unavailable | P-204 boxed X | Pending physical run |
| Scene 7 sensor fault | Alarm cue visible without implying matrix exposes transmitter details | Pending physical run |
| Link loss / reconnect | Broken-link cue after 1.5 s; fresh telemetry restores profile | Pending physical run |
| 10-minute soak | No freeze, reset, or corrupt frame | Pending physical run |
