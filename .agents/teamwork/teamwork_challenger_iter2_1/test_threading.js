const LINK_TIMEOUT_MS = 1500;
const LOOP_INTERVAL_MS = 100;
const PROBE_DURATION_MS = 2500;
const SIMULATION_DURATION_MS = 10000;

console.log('=== TEST CASE A: Synchronous _try_connect() ===');
{
  let now = 0;
  let com1LastPacket = 0;
  let maxLoopDuration = 0;
  let watchdogTrips = 0;
  let lastReconnectAttempt = -10000;
  const cooldown = 3000;

  for (let tick = 0; tick < SIMULATION_DURATION_MS / LOOP_INTERVAL_MS; tick++) {
    const loopStart = now;
    // Attempt reconnect on offline ports synchronously
    if (now - lastReconnectAttempt >= cooldown) {
      // Synchronous blocking probe
      lastReconnectAttempt = now;
      now += PROBE_DURATION_MS; // blocks main loop for 2500 ms
    }
    
    // Transmit to online devices
    const loopDuration = now - loopStart;
    if (loopDuration > maxLoopDuration) maxLoopDuration = loopDuration;

    // Check watchdog on online device COM1
    if (com1LastPacket > 0 && (now - com1LastPacket) > LINK_TIMEOUT_MS) {
      watchdogTrips++;
      console.log(`[WATCHDOG TRIP] COM1 starved! Interval: ${now - com1LastPacket} ms > ${LINK_TIMEOUT_MS} ms at t=${now} ms`);
    }
    com1LastPacket = now;
    now += LOOP_INTERVAL_MS;
  }
  console.log(`Case A Summary: Max Loop Time = ${maxLoopDuration} ms, Watchdog Trips = ${watchdogTrips}\n`);
}

console.log('=== TEST CASE B: Asynchronous Worker Thread ===');
{
  let now = 0;
  let com1LastPacket = 0;
  let maxLoopDuration = 0;
  let watchdogTrips = 0;
  let lastReconnectAttempt = -10000;
  let workerBusyUntil = -1;
  const cooldown = 3000;

  for (let tick = 0; tick < SIMULATION_DURATION_MS / LOOP_INTERVAL_MS; tick++) {
    const loopStart = now;
    
    // Check offline port non-blocking
    if (now - lastReconnectAttempt >= cooldown) {
      if (now >= workerBusyUntil) {
        // Dispatch to background thread
        lastReconnectAttempt = now;
        workerBusyUntil = now + PROBE_DURATION_MS; // Runs in background thread!
      }
    }

    // Packet transmission time is immediate (< 0.2 ms mock I/O)
    const txTime = 0.15; // 0.15 ms
    const loopDuration = txTime;
    if (loopDuration > maxLoopDuration) maxLoopDuration = loopDuration;

    // Check watchdogs on COM1
    if (com1LastPacket > 0 && (now - com1LastPacket) > LINK_TIMEOUT_MS) {
      watchdogTrips++;
      console.log(`[WATCHDOG TRIP] COM1 starved! Interval: ${now - com1LastPacket} ms`);
    }
    com1LastPacket = now;
    now += LOOP_INTERVAL_MS;
  }
  console.log(`Case B Summary: Max Loop Time = ${maxLoopDuration.toFixed(2)} ms (< 2.0 ms), Watchdog Trips = ${watchdogTrips}\n`);
}
