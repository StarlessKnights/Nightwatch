# AVON Arduino serial protocol v1

USB CDC serial at 115200 baud, 8-N-1. Gateway sends complete newline-terminated JSON packets at 5-10 Hz and after state changes. Maximum payload is 192 bytes. An Arduino accepts only `v:1` packets addressed to its compiled `dev` and replaces its entire local display snapshot on each valid message. Stale telemetry is hidden after 1500 ms.

## Device packets

Device 1 requires `v,seq,dev,lvl,cap,h,hh,p1,p2,al,il`.

Device 2 requires `v,seq,dev,flow,max,rf,dir,lim`; `al` is optional.

Device 3 requires `v,seq,dev,flow,max,tf,bp`; `al` is optional.

Pump codes: 0 stopped, 1 running, 2 starting, 3 degraded, 4 tripped, 5 unavailable. `rf` and `tf` are factors in thousandths. Alarm codes are 0 normal, 1 advisory, 2 high, 3 critical. Limiting codes: 0 none, 1 pipeline, 2 treatment, 3 tank volume. `dir` is -1 reverse display, 0 stopped, 1 forward.

The board emits `AVON|HELLO|v=1|dev=N|profile=...|fw=0.1.0` at startup. It does not emit operational commands. Invalid or oversized messages are ignored; parser errors briefly pulse the onboard LED. Wrong device/version packets are ignored.

The gateway maps existing `/ws/sim` fields as described in `PERSON_B_IMPLEMENTATION_PLAN.md`. It should map missing/unknown limiting causes to 0 and pump run states explicitly. For `bp`, send 1 when TRT intake is constrained or an associated pump is limited by treatment.
