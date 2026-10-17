"""Small LAN-only HTTP remote for browsing and queueing songs."""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        address = sock.getsockname()[0]
        sock.close()
        return address
    except OSError:
        return "127.0.0.1"


class RemoteServer:
    def __init__(self, db, queue_callback, queue_count_callback=None, control_callback=None,
                 status_callback=None, queue_snapshot_callback=None, queue_action_callback=None,
                 host="0.0.0.0", port=8765):
        self.db = db
        self.queue_callback = queue_callback
        self.queue_count_callback = queue_count_callback or (lambda: 0)
        self.control_callback = control_callback or (lambda action: None)
        self.status_callback = status_callback or (lambda: {})
        self.queue_snapshot_callback = queue_snapshot_callback or (lambda: {"current": None, "upcoming": []})
        self.queue_action_callback = queue_action_callback or (lambda action, uid: None)
        self.host, self.port = host, port
        self.httpd = None
        self.thread = None
        self._clients = {}
        self._clients_lock = threading.Lock()

    @property
    def url(self):
        return f"http://{local_ip()}:{self.port}/"

    def start(self):
        db, callback, server = self.db, self.queue_callback, self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, body, status=200, content_type="text/html; charset=utf-8"):
                with server._clients_lock:
                    server._clients[self.client_address[0]] = time.monotonic()
                data = body.encode("utf-8") if isinstance(body, str) else body
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/api/songs":
                    query = parse_qs(parsed.query)
                    search = query.get("q", [""])[0]
                    offset = max(0, int(query.get("offset", [0])[0]))
                    limit = min(40, max(1, int(query.get("limit", [30])[0])))
                    shuffle_param = query.get("shuffle", ["1"])[0]
                    shuffle = shuffle_param not in ("0", "false", "no")
                    try:
                        seed = int(query.get("seed", [""])[0])
                    except (ValueError, TypeError):
                        seed = None
                    songs = db.list_remote_songs(search=search, limit=limit, offset=offset, shuffle=shuffle, seed=seed)
                    payload = [{"number": s["song_number"], "id": s["id"],
                                "title": s["title"] or s["filename"],
                                "artist": s["artist"] or "", "format": s["format"] or ""}
                               for s in songs]
                    self._send(json.dumps({"songs": payload, "more": len(songs) == limit}),
                               content_type="application/json; charset=utf-8")
                    return
                if parsed.path.startswith("/api/song-info/"):
                    try:
                        song = db.get_song_by_number(int(parsed.path.rsplit("/", 1)[1]))
                    except (ValueError, TypeError):
                        song = None
                    if song:
                        body = {"ok": True, "title": song["title"] or song["filename"],
                                "artist": song["artist"] or ""}
                    else:
                        body = {"ok": False}
                    self._send(json.dumps(body), content_type="application/json; charset=utf-8")
                    return
                if parsed.path == "/api/queue":
                    self._send(json.dumps(server.queue_snapshot_callback()),
                               content_type="application/json; charset=utf-8")
                    return
                if parsed.path == "/api/status":
                    status = server.status_callback() or {}
                    status.update({"queued": server.queue_count_callback(),
                                   "devices": server.connected_devices()})
                    self._send(json.dumps(status),
                               content_type="application/json; charset=utf-8")
                    return
                if parsed.path.startswith("/api/song-number/"):
                    try:
                        number = int(parsed.path.rsplit("/", 1)[1])
                        song = db.get_song_by_number(number)
                        if not song:
                            raise ValueError
                        callback(song)
                        self._send(json.dumps({
                            "ok": True,
                            "title": song.get("title") or song.get("filename") or "",
                            "artist": song.get("artist") or "",
                            "number": number
                        }), content_type="application/json; charset=utf-8")
                    except (ValueError, TypeError):
                        self._send(json.dumps({"ok": False, "error": "Song number not found"}), 404,
                                   "application/json; charset=utf-8")
                    return
                if parsed.path == "/logo.png":
                    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons", "logo.png")
                    if os.path.exists(logo_path):
                        with open(logo_path, "rb") as f:
                            self._send(f.read(), content_type="image/png")
                        return
                    self._send("Not found", 404, "text/plain; charset=utf-8")
                    return
                if parsed.path not in ("/", "/songs", "/queue"):
                    self._send("Not found", 404, "text/plain; charset=utf-8")
                    return
                self._send(PAGE)

            def do_POST(self):
                parsed = urlparse(self.path)
                if parsed.path.startswith("/api/queue-action/"):
                    try:
                        _, _, _, action, uid = parsed.path.split("/")
                        if action not in ("play", "remove", "up", "down", "next"):
                            raise ValueError
                        server.queue_action_callback(action, int(uid))
                        self._send(json.dumps({"ok": True}), content_type="application/json; charset=utf-8")
                    except (ValueError, TypeError):
                        self._send(json.dumps({"ok": False, "error": "Invalid queue action"}), 400,
                                   "application/json; charset=utf-8")
                    return
                if parsed.path.startswith("/api/control/"):
                    action = parsed.path.rsplit("/", 1)[1]
                    if action not in ("next", "pause"):
                        self._send(json.dumps({"ok": False, "error": "Unknown control"}), 400,
                                   "application/json; charset=utf-8")
                        return
                    server.control_callback(action)
                    self._send(json.dumps({"ok": True}), content_type="application/json; charset=utf-8")
                    return
                if parsed.path.startswith("/api/song-number/"):
                    try:
                        number = int(parsed.path.rsplit("/", 1)[1])
                        song = db.get_song_by_number(number)
                        if not song:
                            raise ValueError
                        callback(song)
                        self._send(json.dumps({
                            "ok": True,
                            "title": song.get("title") or song.get("filename") or "",
                            "artist": song.get("artist") or "",
                            "number": number
                        }), content_type="application/json; charset=utf-8")
                    except (ValueError, TypeError):
                        self._send(json.dumps({"ok": False, "error": "Song number not found"}), 404,
                                   "application/json; charset=utf-8")
                    return
                if not parsed.path.startswith("/api/queue/"):
                    self._send("Not found", 404, "text/plain; charset=utf-8")
                    return
                try:
                    song_id = int(parsed.path.rsplit("/", 1)[1])
                    song = db.get_song(song_id)
                    if not song:
                        raise ValueError("Song not found")
                    callback(song)
                    self._send(json.dumps({
                        "ok": True,
                        "title": song.get("title") or song.get("filename") or "",
                        "artist": song.get("artist") or ""
                    }), content_type="application/json; charset=utf-8")
                except (ValueError, TypeError):
                    self._send(json.dumps({"ok": False, "error": "Song not found"}), 404,
                               "application/json; charset=utf-8")

            def log_message(self, *_):
                pass

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="karaoke-remote", daemon=True)
        self.thread.start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    def connected_devices(self):
        """Return the number of recently active remote client addresses."""
        with self._clients_lock:
            cutoff = time.monotonic() - 30.0
            self._clients = {ip: seen for ip, seen in self._clients.items() if seen >= cutoff}
            return len(self._clients)


PAGE = """<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Remote</title>
<style>
*{box-sizing:border-box}
html,body{margin:0;width:100%;min-width:0;overflow-x:clip}
body{font-family:system-ui,-apple-system,sans-serif;background:#151722;color:#fff;padding:16px 16px 78px}
.page{width:100%;max-width:720px;margin:auto}
.card{background:#202334;border-radius:12px;padding:14px;margin-bottom:14px}
h1{font-size:24px;margin:0 0 14px}
.muted,.status{color:#aeb3c5;font-size:13px}
.status{color:#75c7ff;min-height:20px;margin:6px 0}
.status:empty{min-height:0;margin:0}
button{background:#2878db;color:#fff;border:0;border-radius:9px;padding:11px 15px;font-weight:700;font-size:15px;cursor:pointer}
button:active{opacity:0.85}
.alt{background:#34384d}
.controls{display:flex;gap:10px}
.controls button{flex:1}
.number,.search{width:100%;padding:13px;border-radius:9px;border:1px solid #45495d;background:#25283a;color:#fff;font-size:16px}
.number{font-size:22px;text-align:center}
.search{text-align:left;padding-left:14px;padding-right:14px}
.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}
.pad button{font-size:20px;padding:13px}
.song{display:flex;align-items:center;gap:12px;width:100%;border-bottom:1px solid #303345;padding:13px 0}
.meta{min-width:0;flex:1}
.title,.artist{overflow-wrap:anywhere}
.title{font-weight:700}
.artist{color:#aeb3c5;font-size:13px;margin-top:2px}
.num{color:#75c7ff;min-width:34px;font-weight:700;font-size:14px}
.bottom{position:fixed;bottom:0;left:0;right:0;width:100%;display:flex;background:#202334;border-top:1px solid #3a3e53;padding:8px;gap:8px;z-index:20}
.bottom a{flex:1;text-align:center;color:#fff;text-decoration:none;padding:10px;border-radius:8px;font-weight:600}
.bottom a.active{background:#2878db}
.sticky{position:sticky;top:0;z-index:15;background:#151722;padding:10px 0 12px;box-shadow:0 6px 14px rgba(21,23,34,0.95)}
.qitem{flex-wrap:wrap}
.qbtns{display:flex;gap:6px;margin-left:auto}
.qbtns button{padding:9px 12px;font-size:14px}
.danger{background:#b9384a}
button:disabled{opacity:0.35}
.preview{text-align:center;min-height:42px;margin-top:10px}
.modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(10,12,18,0.78);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:20px;z-index:100;animation:fadeIn .15s ease}
.modal{background:#202334;border:1px solid #3a3e53;border-radius:16px;padding:24px 20px;width:100%;max-width:340px;text-align:center;box-shadow:0 12px 32px rgba(0,0,0,0.6);animation:popIn .2s cubic-bezier(0.175,0.885,0.32,1.275)}
.modal-icon{width:50px;height:50px;border-radius:50%;background:#1d4029;color:#38d368;display:inline-flex;align-items:center;justify-content:center;font-size:26px;font-weight:700;margin-bottom:12px}
.modal-title{font-size:18px;font-weight:700;margin-bottom:6px;color:#fff}
.modal-song{color:#75c7ff;font-weight:600;font-size:16px;margin:8px 0 3px;overflow-wrap:anywhere}
.modal-artist{color:#aeb3c5;font-size:14px;margin-bottom:18px}
.modal-close{width:100%;padding:12px;background:#2878db;color:#fff;border:0;border-radius:10px;font-size:16px;font-weight:700;cursor:pointer}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes popIn{from{transform:scale(0.88);opacity:0}to{transform:scale(1);opacity:1}}
</style></head><body><div class="page" id="app"></div>
<nav class="bottom"><a id="remoteNav" href="/">Remote</a><a id="songsNav" href="/songs">Songs</a><a id="queueNav" href="/queue">Queue</a></nav>
<script>
const app=document.getElementById('app');
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function showModal(title,artist,number){closeModal();let numText=number?(' #'+number):'';let d=document.createElement('div');d.id='qModal';d.className='modal-overlay';d.innerHTML=`<div class="modal"><div class="modal-icon">&#10003;</div><div class="modal-title">Added to Queue!</div><div class="modal-song">${esc(title||('Song'+numText))}</div>${artist?`<div class="modal-artist">${esc(artist)}</div>`:''}<button class="modal-close" onclick="closeModal()">OK</button></div>`;d.onclick=e=>{if(e.target===d)closeModal()};document.body.appendChild(d)}
function showConfirm(title,song,artist,confirmText,onConfirm,danger){closeModal();let d=document.createElement('div');d.id='qModal';d.className='modal-overlay';let iconBg=danger?'#441d24':'#1d344d';let iconColor=danger?'#ff5c6c':'#75c7ff';let icon=danger?'&#10005;':(confirmText.toLowerCase().includes('play')?'&#9654;':'&#65291;');d.innerHTML=`<div class="modal"><div class="modal-icon" style="background:${iconBg};color:${iconColor}">${icon}</div><div class="modal-title">${esc(title)}</div>${song?`<div class="modal-song">${esc(song)}</div>`:''}${artist?`<div class="modal-artist">${esc(artist)}</div>`:''}<div class="controls" style="margin-top:16px;gap:10px"><button class="alt" onclick="closeModal()">Cancel</button><button class="${danger?'danger':''}" id="modalConfirmBtn">${esc(confirmText)}</button></div></div>`;d.onclick=e=>{if(e.target===d)closeModal()};document.body.appendChild(d);document.getElementById('modalConfirmBtn').onclick=()=>{closeModal();onConfirm()}}
function closeModal(){let m=document.getElementById('qModal');if(m)m.remove()}
window.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
async function status(){let a=await fetch('/api/status').then(r=>r.json());let n=document.getElementById('now');if(n)n.textContent=a.title||'Nothing playing';let st=document.getElementById('state');if(st)st.textContent=(a.state||'stopped')+' · '+a.queued+' queued · '+a.devices+' device(s) connected';let p=document.getElementById('pause');if(p)p.textContent=a.state==='playing'?'Pause':'Play'}
async function control(a){await fetch('/api/control/'+a,{method:'POST'});status()}
async function queueNumber(){let n=document.getElementById('number').value;if(!n)return;let btn=document.getElementById('queueNumber');if(btn)btn.disabled=true;try{let a=await fetch('/api/song-number/'+n,{method:'POST'}).then(r=>r.json());if(a.ok){let t=a.title||(document.getElementById('pvTitle')?document.getElementById('pvTitle').textContent:('Song #'+n));let art=a.artist||(document.getElementById('pvArtist')?document.getElementById('pvArtist').textContent:'');showModal(t,art,n);document.getElementById('number').value='';document.getElementById('result').textContent='Song '+n+' queued.';preview()}else{document.getElementById('result').textContent=a.error||'Song not found'}status()}finally{if(btn)btn.disabled=false}}
function digit(n){let i=document.getElementById('number');if(n==='clear')i.value='';else if(n==='back')i.value=i.value.slice(0,-1);else if(i.value.length<5)i.value+=n;preview()}
let pv=0;async function preview(){let n=document.getElementById('number').value,t=document.getElementById('pvTitle'),a=document.getElementById('pvArtist'),id=++pv;document.getElementById('result').textContent='';if(!n){t.textContent='';a.textContent='';return}let r=await fetch('/api/song-info/'+n).then(r=>r.json()).catch(()=>({ok:false}));if(id!==pv)return;if(r.ok){t.textContent=r.title;a.textContent=r.artist||'Unknown singer';t.className='title'}else{t.textContent='No song with number '+n;a.textContent='';t.className='muted'}}
let offset=0,loading=false,more=true,songSeed=Math.floor(Math.random()*2000000000);
async function loadSongs(reset){if(loading||(!more&&!reset))return;if(reset){offset=0;more=true;document.getElementById('songs').innerHTML=''}loading=true;let q=encodeURIComponent(document.getElementById('search').value);let a=await fetch('/api/songs?q='+q+'&offset='+offset+'&limit=30&seed='+songSeed).then(r=>r.json());a.songs.forEach(s=>{let e=document.createElement('div');e.className='song';e.innerHTML='<span class="num">'+s.number+'</span><div class="meta"><div class="title">'+esc(s.title)+'</div><div class="artist">'+esc(s.artist||s.format)+'</div></div><button class="queue-btn">Queue</button>';e.querySelector('.queue-btn').onclick=()=>showConfirm('Add to Queue?',s.title,s.artist,'Add to Queue',()=>queueSong(s.id));document.getElementById('songs').appendChild(e)});offset+=a.songs.length;more=a.more;document.getElementById('empty').style.display=offset?'none':'block';loading=false}
async function queueSong(id){let a=await fetch('/api/queue/'+id,{method:'POST'}).then(r=>r.json());if(a.ok){showModal(a.title,a.artist);document.getElementById('listStatus').textContent='Added to queue.'}else{document.getElementById('listStatus').textContent=a.error||'Queue failed'}status()}
function remotePage(){app.innerHTML=`<h1>Remote</h1><div class="card"><div class="muted">Now playing</div><div class="title" id="now">Nothing playing</div><div class="status" id="state"></div><div class="controls"><button class="alt" id="pause">Play</button><button id="next">Next</button></div></div><div class="card"><div class="muted">Queue by song number</div><input class="number" id="number" readonly inputmode="numeric" placeholder="Song number"><div class="preview"><div id="pvTitle"></div><div class="artist" id="pvArtist"></div></div><div class="pad"><button data-digit="1">1</button><button data-digit="2">2</button><button data-digit="3">3</button><button data-digit="4">4</button><button data-digit="5">5</button><button data-digit="6">6</button><button data-digit="7">7</button><button data-digit="8">8</button><button data-digit="9">9</button><button class="alt" data-digit="clear">Clear</button><button data-digit="0">0</button><button class="alt" data-digit="back">Back</button></div><button style="width:100%;margin-top:10px" id="queueNumber">Queue song</button><div class="status" id="result"></div></div>`;document.getElementById('remoteNav').className='active';document.getElementById('pause').onclick=()=>control('pause');document.getElementById('next').onclick=()=>control('next');document.getElementById('queueNumber').onclick=queueNumber;document.querySelectorAll('[data-digit]').forEach(b=>b.onclick=()=>digit(b.dataset.digit));status()}
function songsPage(){songSeed=Math.floor(Math.random()*2000000000);app.innerHTML=`<h1>Songs</h1><div class="sticky"><input class="search" id="search" placeholder="Search songs…" autocomplete="off"><div class="status" id="listStatus"></div></div><div id="songs"></div><div id="empty" class="muted" style="display:none;margin-top:16px">No songs found.</div><div id="sentinel" style="height:30px"></div>`;document.getElementById('songsNav').className='active';document.getElementById('search').oninput=()=>{clearTimeout(window.st);window.st=setTimeout(()=>loadSongs(true),180)};new IntersectionObserver(e=>{if(e[0].isIntersecting)loadSongs(false)}).observe(document.getElementById('sentinel'));loadSongs(true);status()}
async function loadQueue(){let el=document.getElementById('qlist');if(!el)return;let q=await fetch('/api/queue').then(r=>r.json());let n=document.getElementById('now');if(n)n.textContent=q.current?q.current.title+(q.current.artist?' - '+q.current.artist:''):'Nothing playing';let up=q.upcoming,last=up.length-1;document.getElementById('qcount').textContent=up.length+' song(s) waiting';el.innerHTML=up.map((s,i)=>`<div class="song qitem" data-uid="${s.uid}" data-title="${esc(s.title)}" data-artist="${esc(s.artist||'')}"><span class="num">${i+1}</span><div class="meta"><div class="title">${esc(s.title)}</div><div class="artist">${esc(s.artist||'')}</div></div><div class="qbtns"><button class="alt" data-act="up" data-uid="${s.uid}" ${i===0?'disabled':''}>&#9650;</button><button class="alt" data-act="down" data-uid="${s.uid}" ${i===last?'disabled':''}>&#9660;</button><button data-act="play" data-uid="${s.uid}">Play</button><button class="danger" data-act="remove" data-uid="${s.uid}">&#10005;</button></div></div>`).join('')||'<div class="muted" style="margin-top:16px">Queue is empty. Add songs from the Songs tab.</div>'}
async function queueClick(e){let b=e.target.closest('button[data-act]');if(!b)return;let act=b.dataset.act,uid=b.dataset.uid;let row=b.closest('.qitem');let title=row?row.dataset.title:'';let artist=row?row.dataset.artist:'';if(act==='play'){showConfirm('Play this song now?',title,artist,'Play Now',async()=>{await fetch('/api/queue-action/play/'+uid,{method:'POST'});setTimeout(()=>{loadQueue();status()},200)});return}if(act==='remove'){showConfirm('Remove from queue?',title,artist,'Remove',async()=>{await fetch('/api/queue-action/remove/'+uid,{method:'POST'});setTimeout(()=>{loadQueue();status()},200)},true);return}b.disabled=true;await fetch('/api/queue-action/'+act+'/'+uid,{method:'POST'});setTimeout(()=>{loadQueue();status()},200)}
function queuePage(){app.innerHTML=`<h1>Queue</h1><div class="card"><div class="muted">Now playing</div><div class="title" id="now">Nothing playing</div><div class="status" id="state"></div><div class="controls"><button class="alt" id="pause">Play</button><button id="next">Next</button></div></div><div class="muted" id="qcount"></div><div id="qlist"></div>`;document.getElementById('queueNav').className='active';document.getElementById('pause').onclick=()=>control('pause');document.getElementById('next').onclick=async()=>{await control('next');setTimeout(loadQueue,200)};document.getElementById('qlist').onclick=queueClick;loadQueue();status();setInterval(loadQueue,3000)}
if(location.pathname==='/songs')songsPage();else if(location.pathname==='/queue')queuePage();else remotePage();setInterval(status,5000);
</script></body></html>"""
