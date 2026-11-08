/* eslint-disable no-unused-expressions -- Playwright CLI evaluates this function expression. */
// With the app running, open a dedicated session and run:
// playwright-cli -s=flow-test open http://localhost:5173
// playwright-cli -s=flow-test run-code --filename=avon-ai/frontend/tests/flow-animation.js
// playwright-cli -s=flow-test close
async page => {
  const network = await page.evaluate(async () => (await fetch('/api/network')).json())
  const snapshot = network.snapshot
  for (const group of ['sources', 'pumps', 'pipelines']) {
    for (const asset of Object.values(snapshot.state[group])) asset.flow = 100
  }
  // Mock telemetry rather than advancing or changing the shared simulation.
  await page.route('**/api/network', route => route.fulfill({ json: network }))
  let socket
  await page.routeWebSocket('**/ws/sim', ws => {
    socket = ws
    ws.send(JSON.stringify({ ...snapshot, type: 'sync' }))
  })
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.reload()
  const path = page.locator('.flow-live .react-flow__edge-path').first()
  await path.waitFor()
  // Allow initial node measurements and fitView to settle before capturing identity.
  await page.waitForTimeout(600)
  const previous = await path.evaluateHandle(element => ({
    element, animation: element.getAnimations()[0], time: element.getAnimations()[0].currentTime,
  }))
  for (let i = 0; i < 4; i++) {
    await page.waitForTimeout(180)
    socket.send(JSON.stringify({
      ...snapshot, type: 'tick', history: [], new_events: [],
      state: { ...snapshot.state, t_min: snapshot.state.t_min + i + 1 },
    }))
  }
  await page.waitForTimeout(100)
  await path.evaluate((element, before) => {
    if (element !== before.element) throw new Error('Telemetry replaced the edge path')
    const animation = element.getAnimations()[0]
    if (animation !== before.animation) throw new Error('Telemetry restarted the animation')
    if (animation.currentTime <= before.time) throw new Error('Flow animation did not advance')
    const frames = animation.effect.getKeyframes()
    const period = getComputedStyle(element).strokeDasharray.split(',').reduce((sum, n) => sum + parseFloat(n), 0)
    const distance = parseFloat(frames.at(-1).strokeDashoffset) - parseFloat(frames[0].strokeDashoffset)
    if (distance !== -period) throw new Error('Flow loop does not cover one full dash period')
  }, previous)
  await previous.dispose()
  await page.emulateMedia({ reducedMotion: 'reduce' })
  if (await path.evaluate(el => getComputedStyle(el).animationName) !== 'none') {
    throw new Error('Flow animation ignores reduced motion')
  }
}
