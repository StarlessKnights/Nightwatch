// Empirical simulation of Modulino Knob push-switch debouncing

function simulatePress({ useDebounce, sampleIntervalMs = 10, pressDurationMs = 150, chatter = false }) {
  let targetDev = 1;
  let lastKnobPressed = false;
  let lastKnobSwitchMs = -1000;
  const switchEvents = [];

  for (let now = 0; now <= 400; now += sampleIntervalMs) {
    // Generate physical button state for a press starting at t=50ms lasting 150ms (until t=200ms)
    let currentPressed = false;
    if (now >= 50 && now <= 200) {
      currentPressed = true;
      // If chatter enabled, simulate 3 mechanical bounces during the first 25ms of press
      if (chatter && (now === 60 || now === 80)) {
        currentPressed = false; // brief open circuit bounce
      }
    }

    if (!useDebounce) {
      // Flawed original code: raw level check
      if (currentPressed) {
        targetDev = (targetDev % 3) + 1;
        switchEvents.push({ time: now, targetDev });
      }
    } else {
      // Remediated code: rising edge + 250 ms lockout
      if (currentPressed && !lastKnobPressed && (now - lastKnobSwitchMs >= 250)) {
        lastKnobSwitchMs = now;
        targetDev = (targetDev % 3) + 1;
        switchEvents.push({ time: now, targetDev });
      }
      lastKnobPressed = currentPressed;
    }
  }

  return { finalTarget: targetDev, switchEvents };
}

console.log('=== TEST 1: Un-debounced Switch (150 ms press, 10 ms ticks) ===');
const res1 = simulatePress({ useDebounce: false, chatter: false });
console.log(`Switch events count: ${res1.switchEvents.length}`);
console.log(`Final Target Device: ${res1.finalTarget} (Cycled through ${res1.switchEvents.length} increments!)`);

console.log('\n=== TEST 2: Remediated 250ms Lockout Switch (150 ms press, no chatter) ===');
const res2 = simulatePress({ useDebounce: true, chatter: false });
console.log(`Switch events count: ${res2.switchEvents.length}`);
console.log(`Events:`, res2.switchEvents);
console.log(`Final Target Device: ${res2.finalTarget} (Target accurately transitioned from 1 -> 2)`);

console.log('\n=== TEST 3: Remediated 250ms Lockout Switch with Mechanical Chatter ===');
const res3 = simulatePress({ useDebounce: true, chatter: true });
console.log(`Switch events count: ${res3.switchEvents.length}`);
console.log(`Events:`, res3.switchEvents);
console.log(`Final Target Device: ${res3.finalTarget} (Contact chatter cleanly filtered by 250ms lockout)`);

console.log('\n=== TEST 4: Intentional Rapid Double Click (t=50ms and t=350ms) ===');
{
  let targetDev = 1;
  let lastKnobPressed = false;
  let lastKnobSwitchMs = -1000;
  const switchEvents = [];

  for (let now = 0; now <= 600; now += 10) {
    // Click 1: 50..150ms, Click 2: 350..450ms
    let currentPressed = (now >= 50 && now <= 150) || (now >= 350 && now <= 450);
    if (currentPressed && !lastKnobPressed && (now - lastKnobSwitchMs >= 250)) {
      lastKnobSwitchMs = now;
      targetDev = (targetDev % 3) + 1;
      switchEvents.push({ time: now, targetDev });
    }
    lastKnobPressed = currentPressed;
  }
  console.log(`Switch events count: ${switchEvents.length}`);
  console.log(`Events:`, switchEvents);
  console.log(`Final Target Device: ${targetDev} (Both distinct clicks registered cleanly: 1 -> 2 -> 3)`);
}
