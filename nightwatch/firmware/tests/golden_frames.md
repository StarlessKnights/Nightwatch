# Visual golden-frame review

Coordinate diagrams use `#` for lit red LED and `.` for off. Rows are top to bottom, columns left to right. Animated profiles have multiple phases, so these are shape expectations rather than a single frozen full-frame bitmap.

## Orientation

The `corners` PlatformIO environment must light these positions in order: `(0,0)`, `(11,0)`, `(11,7)`, `(0,7)`. If the physical matrix differs, adjust the single mapping in `Framebuffer::pack()` and rerun this check.

All three devices use the same pump renderer with the assignment compiled into the environment.

- Device 1 is dedicated to P-201.
- Device 2 is dedicated to P-203.
- Device 3 is dedicated to P-204.
- Normal states: animated water waves filled from the bottom to `lvl / cap`, with a moving crest and occasional droplets.
- Tripped (`state:4`) or effective health `w < 500`: alternate between the live level waves and a caution triangle with an exclamation mark. The exclamation has a dark gap on its third pixel.
- Unavailable (`available:0` or `state:5`): solid simple X, with priority over caution.
