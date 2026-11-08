"""Local operator demo served alongside the serial bridge."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bridge import PUMPS

HTML = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AVON • Pump Control Deck</title><style>
:root{font-family:Inter,ui-sans-serif,system-ui;background:#0a1420;color:#e6f3f5}*{box-sizing:border-box}body{margin:0;padding:32px;max-width:1240px;margin:auto}
header{display:flex;justify-content:space-between;align-items:center;gap:20px;border-bottom:1px solid #315365;padding-bottom:22px}h1{font-size:clamp(27px,4vw,44px);letter-spacing:-.04em;margin:0}h2{margin:0 0 8px;font-size:26px}p{color:#9eb9c1}button{font:inherit;cursor:pointer;border:1px solid #62828c;border-radius:10px;padding:11px 16px;background:#183644;color:#eff}.reset{background:#182b35}.trip{background:#8c3430}.unavailable{background:#654c2b}.active{outline:2px solid #fff}button:disabled{opacity:.5;cursor:wait}button:hover{filter:brightness(1.2)}main{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:30px}.card{border:1px solid #315365;border-radius:18px;padding:23px;background:linear-gradient(160deg,#132b3a,#0e202c);box-shadow:0 15px 40px #0004}.meta{font-size:13px;letter-spacing:.12em;color:#72cfd4;text-transform:uppercase}.status{border-radius:9px;padding:8px 11px;display:inline-block;background:#254c52;margin:10px 0 18px}.buttons{display:flex;flex-wrap:wrap;gap:9px}.slider{display:block;margin:22px 0}input[type=range]{width:100%;accent-color:#63cbd1;margin-top:12px}.readout{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:20px 0;font-size:14px;color:#a9c5cc}.readout strong{color:#fff}pre{white-space:pre-wrap;word-break:break-all;font-size:11px;background:#091923;padding:10px;border-radius:8px;color:#8fb6bb}.banner{margin-top:15px;min-height:24px;color:#ffcda1}@media(max-width:850px){main{grid-template-columns:1fr}body{padding:18px}header{align-items:start;flex-direction:column}}</style>
<header><div><div class="meta">AVON AI · local hardware demo</div><h1>Pump control deck</h1><p>Three Arduino UNO R4 matrix displays • live simulation controls</p></div><button class="reset" onclick="action('reset-all')">Reset simulation</button></header><div id="message" class="banner"></div><main id="cards"></main>
<script>
const names={1:'P-201',2:'P-203',3:'P-204'},tanks={1:'T-101',2:'T-104',3:'T-104'};let busy=false, sliderTimer={};
async function request(url,options){const r=await fetch(url,options);let data=await r.json();if(!r.ok)throw Error(data.error||r.statusText);return data}
async function action(kind,dev,value){if(busy)return;busy=true;try{await request('/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,dev,value})});document.getElementById('message').textContent=`${kind} applied${dev?' to '+names[dev]:''}`;await refresh()}catch(e){document.getElementById('message').textContent=e.message}finally{busy=false}}
function wear(dev,value){document.getElementById('w'+dev).textContent=value+'%';clearTimeout(sliderTimer[dev]);sliderTimer[dev]=setTimeout(()=>action('wear',dev,Number(value)/100),250)}
async function refresh(){try{const s=await request('/status');document.getElementById('cards').innerHTML=Object.entries(names).map(([key,name])=>{let d=Number(key),p=s.state.pumps?.[name]||{},packet=s.packets?.[d]||{},link=s.links?.[d]||'offline',faults=s.state.faults||[],trip=faults.some(f=>f.type==='PUMP_TRIP'&&f.target===name&&f.active!==false),health=Math.round((p.health??1)*100),avail=p.available!==false;return `<section class="card"><div class="meta">Device ${d} · ${tanks[d]}</div><h2>${name}</h2><div class="status">${link} · ${p.run_state||'waiting'}</div><div class="buttons"><button class="trip ${trip?'active':''}" onclick="action('trip',${d})">${trip?'Clear trip':'Trip pump'}</button><button class="unavailable ${!avail?'active':''}" onclick="action('unavailable',${d})">${avail?'Make unavailable':'Restore availability'}</button></div><label class="slider">Wear health: <strong id="w${d}">${health}%</strong><input type="range" min="0" max="100" value="${health}" oninput="wear(${d},this.value)"></label><button class="reset" onclick="action('reset',${d})">Reset ${name}</button><div class="readout"><span>Effective health <strong>${Math.round((p.eff_health??1)*100)}%</strong></span><span>Tank level <strong>${packet.lvl??'—'} / ${packet.cap??'—'}</strong></span><span>Availability <strong>${avail?'Available':'Unavailable'}</strong></span><span>Matrix state <strong>${packet.state??'—'}</strong></span></div><div class="meta">Last serial packet</div><pre>${JSON.stringify(packet)}</pre></section>`}).join('');document.getElementById('message').textContent=s.backend_error||document.getElementById('message').textContent}catch(e){document.getElementById('message').textContent='Gateway unavailable: '+e.message}}
refresh();setInterval(()=>{if(!busy&&!document.querySelector('input[type=range]:active'))refresh()},1500);
</script></html>"""


def backend(api_url, method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = Request(api_url + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=3) as response:
        return json.load(response)


def perform_action(api_url, payload):
    kind = payload.get("kind")
    if kind == "reset-all":
        return backend(api_url, "POST", "/api/sim/reset")
    dev = payload.get("dev")
    if type(dev) is not int or dev not in PUMPS:
        raise ValueError("Unknown device")
    pump = PUMPS[dev]
    snapshot = backend(api_url, "GET", "/api/network")["snapshot"]["state"]
    faults = [f for f in snapshot["faults"] if f["target"] == pump and f.get("active", True)]
    if kind == "trip":
        trips = [f for f in faults if f["type"] == "PUMP_TRIP"]
        return backend(api_url, "DELETE", f"/api/faults/{trips[0]['id']}") if trips else backend(api_url, "POST", "/api/faults", {"type": "PUMP_TRIP", "target": pump, "params": {}})
    if kind == "unavailable":
        available = snapshot["pumps"][pump]["available"]
        return backend(api_url, "PATCH", f"/api/assets/{pump}", {"available": not available})
    if kind == "wear":
        value = payload.get("value")
        if type(value) not in (float, int) or not 0 <= value <= 1:
            raise ValueError("Wear must be between 0 and 1")
        return backend(api_url, "PATCH", f"/api/assets/{pump}", {"health": value})
    if kind == "reset":
        for fault in faults:
            if fault["type"] in ("PUMP_TRIP", "PUMP_DEGRADE", "PUMP_UNAVAILABLE"):
                backend(api_url, "DELETE", f"/api/faults/{fault['id']}")
        return backend(api_url, "PATCH", f"/api/assets/{pump}", {"health": 1.0, "available": True})
    raise ValueError("Unknown action")


def start_demo_server(port, api_url, bus, state, packets):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, content, mime="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if self.path == "/":
                return self.send(200, HTML.encode(), "text/html; charset=utf-8")
            if self.path == "/status":
                links = {str(d): "offline" for d in PUMPS}
                for link in bus.links.values():
                    if link.is_online and link.device_id:
                        links[str(link.device_id)] = link.port
                response = {"state": state, "packets": packets, "links": links, "backend_error": None}
                return self.send(200, json.dumps(response).encode())
            self.send(404, b'{}')

        def do_POST(self):
            if self.path != "/action":
                return self.send(404, b'{}')
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 4096:
                    raise ValueError("Request too large")
                payload = json.loads(self.rfile.read(length))
                result = perform_action(api_url, payload)
                self.send(200, json.dumps(result).encode())
            except (ValueError, KeyError, HTTPError, URLError) as exc:
                self.send(400, json.dumps({"error": str(exc)}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
