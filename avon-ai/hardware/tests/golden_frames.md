# Visual golden-frame review

Coordinate diagrams use `#` for lit red LED and `.` for off. Rows are top to bottom, columns left to right. Animated profiles have multiple phases, so these are shape expectations rather than a single frozen full-frame bitmap.

## Orientation

The `corners` PlatformIO environment must light these positions in order: `(0,0)`, `(11,0)`, `(11,7)`, `(0,7)`. If the physical matrix differs, adjust the single mapping in `Framebuffer::pack()` and rerun this check.

## Device 1

- Empty tank: visible side rails and bottom edge; no fill pixels.
- Half tank: four bottom rows filled between columns 1 and 2.
- H alarm: top tank row blinks at 2 Hz.
- HH/interlock: tank region alternates with an exclamation pattern; inlet bar appears on row 1.
- Pump states: stopped dash, running rotating vane, starting pulse, degraded stutter, trip X, unavailable boxed X.

## Device 2

- Zero flow: steady rails on rows 2 and 5, no particles.
- Positive flow: particles in rows 3 and 4 travel left to right; higher rate advances faster.
- Pipeline restriction: flashing neck at columns 5 and 6.
- Treatment limit: right barrier at columns 10 and 11.
- Tank-volume limit: inlet marker at column 0.

## Device 3

- Normal: incoming particles feed a changing vortex/drain motif at right.
- Backpressure: right-side flashing barrier and left-moving particles.
- Critical constrained state: occasional full-width alarm stripe.
