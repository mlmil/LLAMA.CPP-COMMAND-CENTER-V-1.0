from pathlib import Path
import os, signal, subprocess, threading
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

MODEL_DIR = Path(os.environ.get('MODEL_DIR', '/media/mikem/WorkDrive_A/Models'))
LLAMA = os.environ.get('LLAMA_SERVER', '/home/mikem/llama.cpp/build-rocm/bin/llama-server')
GPUS = [{'index': 0, 'name': 'RX 7900 XT', 'vram_gb': 20, 'port': 8081}, {'index': 1, 'name': 'RX 6600', 'vram_gb': 8, 'port': 8082}]
procs = {}
lock = threading.Lock()

app = FastAPI(title='GPU Command Center')

class Launch(BaseModel):
    model: str
    ctx: int = 8192
    threads: int = 8
    layers: int = 999
    batch: int = 512
    kv_offload: bool = False

class DatabasePath(BaseModel):
    path: str

def models():
    return [{'name': str(p.relative_to(MODEL_DIR)), 'path': str(p), 'size_gb': round(p.stat().st_size/1024**3, 2)}
            for p in MODEL_DIR.rglob('*.gguf') if p.is_file()]

@app.get('/api/models')
def get_models(): return models()

@app.post('/api/rescan')
def rescan(req: DatabasePath):
    global MODEL_DIR
    p = Path(req.path).expanduser().resolve()
    if not p.is_dir(): raise HTTPException(400, 'Directory does not exist on Orion')
    MODEL_DIR = p
    return {'model_dir': str(MODEL_DIR), 'models': models()}

@app.get('/api/gpus')
def get_gpus():
    out=[]
    for g in GPUS:
        p=procs.get(g['index'])
        out.append({**g, 'running': bool(p and p.poll() is None), 'pid': p.pid if p else None})
    return out

@app.get('/api/resources')
def resources():
    mem={}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value=line.split(':',1)
        mem[key]=int(value.split()[0])*1024
    total=mem.get('MemTotal',0)
    available=mem.get('MemAvailable',0)
    return {'ram_total': total, 'ram_used': total-available,
            'processes': {str(i): int(p.memory_info().rss) if p and p.poll() is None else 0
                          for i,p in procs.items()}}

@app.get('/api/gpu/{idx}/telemetry')
def telemetry(idx: int):
    if idx not in (0, 1): raise HTTPException(404, 'GPU not found')
    try:
        raw = subprocess.check_output(['amd-smi','monitor','-t','-p','-v','-u','-g',str(idx),'--json'], text=True, timeout=4)
        return {'gpu': idx, 'raw': raw}
    except Exception as e:
        return {'gpu': idx, 'error': str(e)}

@app.get('/api/gpu/{idx}/log')
def log(idx: int):
    p = Path(f'/tmp/gpu-command-center-{idx}.log')
    return {'lines': p.read_text(errors='replace').splitlines()[-12:] if p.exists() else []}

@app.post('/api/gpu/{idx}/launch')
def launch(idx: int, req: Launch):
    if idx not in (0,1): raise HTTPException(404, 'GPU not found')
    path=Path(req.model).resolve()
    if not path.is_file() or MODEL_DIR not in path.parents: raise HTTPException(400, 'Model must be inside model directory')
    with lock:
        old=procs.get(idx)
        if old and old.poll() is None: raise HTTPException(409, 'GPU is already running')
        g=GPUS[idx]
        env={**os.environ, 'ROCR_VISIBLE_DEVICES': str(idx), 'HIP_VISIBLE_DEVICES': str(idx)}
        cmd=[LLAMA, '--model', str(path), '--host', '0.0.0.0', '--port', str(g['port']), '-c', str(req.ctx), '-t', str(req.threads), '-ngl', str(req.layers), '-b', str(req.batch)]
        if req.kv_offload:
            cmd.append('--no-kv-offload')
        log=open(f'/tmp/gpu-command-center-{idx}.log','ab', buffering=0)
        procs[idx]=subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    return {'ok': True, 'pid': procs[idx].pid, 'port': g['port'], 'command': cmd}

@app.post('/api/gpu/{idx}/stop')
def stop(idx: int):
    p=procs.get(idx)
    if not p or p.poll() is not None: return {'ok': True, 'running': False}
    os.killpg(p.pid, signal.SIGTERM)
    return {'ok': True, 'running': False}

@app.get('/', response_class=HTMLResponse)
def index():
    p = Path(__file__).parent / 'index.html'
    html = p.read_text()
    html = html.replace('grid-template-columns:340px 1fr 1fr', 'grid-template-columns:var(--rail,340px) 1fr 1fr')
    html = html.replace('let models=[],selected=null,assigned=[null,null],running=[false,false];', 'let models=[],selected=null,assigned=[null,null],running=[false,false],pids=[null,null];')
    html = html.replace('running=gs.map(x=>x.running);draw();', 'running=gs.map(x=>x.running);pids=gs.map(x=>x.pid);draw();')
    html = html.replace('<div class="meta">MODEL · ${models.find(x=>x.path===m)?.size_gb||0} GB on disk</div><div class="meta amber">PID · ${pids[i]||"—"}</div>', '<div class="meta">MODEL · ${models.find(x=>x.path===m)?.size_gb||0} GB on disk</div>')
    html = html.replace('.status{float:right}', '.status{float:right}.green{color:#39ff88;text-shadow:0 0 8px #39ff8866}')
    html = html.replace("class=\"status ${running[i]?'amber':''}\"", "class=\"status ${running[i]?'green':''}\"")
    html = html.replace('<span class="status ${running[i]?\'green\':\'\'}">■ ${running[i]?\'RUNNING\':\'STOPPED\'}</span>', '<span class="status ${running[i]?\'green\':\'\'}">■ ${running[i]?\'RUNNING\':\'STOPPED\'}<br><small style="font:10px JetBrains Mono;color:#c7cad0">PID · ${pids[i]||"—"}</small></span>')
    html = html.replace('async function launch(i){await api(\'/api/gpu/\'+i+\'/launch\',{method:\'POST\',headers:{\'content-type\':\'application/json\'},body:JSON.stringify({model:assigned[i]})});running[i]=true;draw()}', 'async function launch(i){await api(\'/api/gpu/\'+i+\'/launch\',{method:\'POST\',headers:{\'content-type\':\'application/json\'},body:JSON.stringify({model:assigned[i]})});let gs=await api(\'/api/gpus\');running=gs.map(x=>x.running);pids=gs.map(x=>x.pid);draw()}')
    html = html.replace('async function stopGpu(i){await api(\'/api/gpu/\'+i+\'/stop\',{method:\'POST\'});running[i]=false;draw()}', 'async function stopGpu(i){await api(\'/api/gpu/\'+i+\'/stop\',{method:\'POST\'});let gs=await api(\'/api/gpus\');running=gs.map(x=>x.running);pids=gs.map(x=>x.pid);draw()}')
    html = html.replace('setInterval(async()=>{let g=await api(\'/api/gpus\');running=g.map(x=>x.running);draw()},3000)', 'setInterval(async()=>{try{let gs=await api("/api/gpus"),ss=document.querySelectorAll(".status");gs.forEach((g,i)=>{let s=ss[i];if(!s)return;s.className="status "+(g.running?"green":"");s.innerHTML="■ "+(g.running?"RUNNING":"STOPPED")+"<br><small style=\'font:10px JetBrains Mono;color:#c7cad0\'>PID · "+(g.pid||"—")+"</small>"})}catch(e){}},3000)')
    html = html.replace('class="outline">⚙ MODEL DATABASE', 'class="outline" onclick="toggleDb()">⚙ MODEL DATABASE')
    drawer = '<div id="db" style="display:none;background:#17191c;border-bottom:1px solid #2a2d32;padding:20px 32px"><div class="mono">MODEL DATABASE LOCATION</div><input id="dbpath" value="'+str(MODEL_DIR)+'" style="margin-top:8px;width:70%;background:#0e0f11;border:1px solid #2a2d32;color:#f2efe6;padding:12px;font:14px JetBrains Mono"><button class="outline" onclick="rescan()">RESCAN</button><span id="dbmsg" class="mono"></span></div>'
    html = html.replace('<main class="grid">', drawer+'<main class="grid">', 1)
    html = html.replace('</body></html>', '<div id="resizeRail" style="position:fixed;top:64px;bottom:0;left:335px;width:10px;cursor:col-resize;z-index:20"></div>\n<script>(function(){let r=document.getElementById("resizeRail"),w=+localStorage.getItem("railWidth")||340;function set(v){w=Math.max(240,Math.min(640,v));document.documentElement.style.setProperty("--rail",w+"px");r.style.left=(w-5)+"px";localStorage.setItem("railWidth",w)}set(w);r.onpointerdown=e=>{r.setPointerCapture(e.pointerId);r.onpointermove=x=>set(x.clientX);r.onpointerup=()=>{r.onpointermove=null}}})();(function(){function restore(){document.querySelectorAll(".gpu").forEach((p,i)=>p.querySelectorAll(".params input").forEach((x,j)=>{let v=localStorage.getItem("gpu"+i+"param"+j);if(v!==null)x.value=v}))}document.addEventListener("input",e=>{if(e.target.closest(".gpu .params")){let p=e.target.closest(".gpu"),i=[...document.querySelectorAll(".gpu")].indexOf(p),j=[...p.querySelectorAll(".params input")].indexOf(e.target);localStorage.setItem("gpu"+i+"param"+j,e.target.value)}});new MutationObserver(restore).observe(document.querySelector(".grid"),{childList:true,subtree:true});restore()})();async function telemetry(){for(let i=0;i<2;i++){try{let d=await fetch("/api/gpu/"+i+"/telemetry").then(x=>x.json()),v=JSON.parse(d.raw)[0],m=document.querySelectorAll("#gpu"+i+" .metric strong");if(m.length){m[0].textContent=(v.hotspot_temperature?.value??"—")+"°";m[1].textContent=((v.vram_used?.value??0)/1024).toFixed(1)+" GB";m[2].textContent=(v.power_usage?.value??"—")+" W";m[3].textContent=v.gfx?.value??"—"}}catch(e){}}}telemetry();setInterval(telemetry,2000);</script></body></html>')
    html = html.replace('</body></html>', '<script>function toggleDb(){let x=document.getElementById("db");x.style.display=x.style.display==="none"?"block":"none"}async function rescan(){let p=document.getElementById("dbpath").value,m=await fetch("/api/rescan",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({path:p})});let d=await m.json();document.getElementById("dbmsg").textContent=d.model_dir||d.detail||"";if(m.ok){models=d.models;draw()}}function fmt(b){return (b/1073741824).toFixed(1)+" GB"}async function resources(){try{let d=await fetch("/api/resources").then(x=>x.json()),x=document.getElementById("resourceReadout");if(!x){x=document.createElement("div");x.id="resourceReadout";x.style="position:fixed;right:24px;bottom:20px;background:#17191c;border:1px solid #2a2d32;padding:12px 16px;color:#c7cad0;font:11px JetBrains Mono;z-index:30;line-height:1.7";document.body.appendChild(x)}x.innerHTML="RAM "+fmt(d.ram_used)+" / "+fmt(d.ram_total)+"<br>GPU 0 process RAM "+fmt(d.processes["0"]||0)+"<br>GPU 1 process RAM "+fmt(d.processes["1"]||0)}catch(e){}}resources();setInterval(resources,2000)</script></body></html>')
    return html

@app.get('/design', response_class=HTMLResponse)
def design():
    p = Path(__file__).parent / 'design' / 'GPU Command Center.dc.html'
    if not p.exists(): raise HTTPException(404, 'Design handoff is not installed')
    return p.read_text()
