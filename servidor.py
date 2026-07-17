import os, asyncio, math, traceback, random, json
import motor.motor_asyncio
from datetime import datetime, timedelta
import socketio
from aiohttp import web


sio = socketio.AsyncServer(cors_allowed_origins='*', async_mode='aiohttp')
app = web.Application()
sio.attach(app)

W,H = 800,600
ATR_BOLA, ATR_JOG = 0.96, 0.85
G_SUP, G_INF = 200,400

salas = {}
jogadores_sala = {}
espectadores_sala = {}
torneios = {}



# 1. CONEXÃO COM O MONGODB (O Render vai ler isto das Variáveis de Ambiente)
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://onoob371_db_user:banana12345@cluster0.owtaogx.mongodb.net/?appName=Cluster0")
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = mongo_client.futgraal_db # Nome do teu banco de dados

contas_global = {}
ranking_global = {'semana': '', 'artilheiros': {}, 'assistentes': {}, 'mvp': {}, 'jogos': {}, 'vitorias': {}, 'derrotas': {}, 'empates': {}}
logados = {}

def get_week_id():
    now = datetime.now()
    return now.strftime("%Y-W%U")

# 2. FUNÇÕES ASSÍNCRONAS QUE GRAVAM NA NUVEM
async def save_contas_db(data):
    try: await db.sistema.update_one({"_id": "contas"}, {"$set": {"json": data}}, upsert=True)
    except Exception as e: print("❌ Erro Mongo Contas:", e)

async def save_ranking_db(data):
    try: await db.sistema.update_one({"_id": "ranking"}, {"$set": {"json": data}}, upsert=True)
    except Exception as e: print("❌ Erro Mongo Ranking:", e)

# 3. PONTE INVISÍVEL (Para não ter de reescrever o resto do jogo todo)
# substitua suas funções atuais por essas
async def save_contas(data):
    try: 
        await db.sistema.update_one({"_id": "contas"}, {"$set": {"json": data}}, upsert=True)
        print("✅ Contas salvas")
    except Exception as e: 
        print("❌ Erro Mongo Contas:", e)

async def save_ranking(data):
    try: 
        await db.sistema.update_one({"_id": "ranking"}, {"$set": {"json": data}}, upsert=True)
        print("✅ Ranking salvo")
    except Exception as e: 
        print("❌ Erro Mongo Ranking:", e)

async def init_mongodb():
    global contas_global, ranking_global
    print("📡 A ligar ao MongoDB Atlas...")
    try:
        doc_c = await db.sistema.find_one({"_id": "contas"})
        if doc_c: 
            contas_global = doc_c.get("json", {})
        else:
            # FORÇA CRIAR A COLEÇÃO NA PRIMEIRA VEZ
            print("Criando coleção contas pela primeira vez...")
            await db.sistema.update_one({"_id": "contas"}, {"$set": {"json": {}}}, upsert=True)

        doc_r = await db.sistema.find_one({"_id": "ranking"})
        if doc_r: 
            ranking_global = doc_r.get("json", {})
            if ranking_global.get('semana') != get_week_id():
                ranking_global = {'semana': get_week_id(), 'artilheiros': {}, 'assistentes': {}, 'mvp': {}, 'jogos': {}, 'vitorias': {}, 'derrotas': {}, 'empates': {}}
                await save_ranking_db(ranking_global)
        else:
            ranking_global['semana'] = get_week_id()
            print("Criando coleção ranking pela primeira vez...")
            await db.sistema.update_one({"_id": "ranking"}, {"$set": {"json": ranking_global}}, upsert=True)
            
        print("✅ MongoDB Conectado com Sucesso! Dados carregados.")
    except Exception as e:
        print("💀 ERRO CRÍTICO AO LIGAR MONGODB:", e)
        

def update_ranking_gol(nome, qtd=1):
    global ranking_global
    if not nome or nome=='BOT GK': return
    nome=nome.upper()[:12]
    ranking_global['artilheiros'][nome]=ranking_global['artilheiros'].get(nome,0)+qtd
    ranking_global['jogos'][nome]=ranking_global['jogos'].get(nome,0)+0
    asyncio.create_task(save_ranking(ranking_global))

def update_ranking_assist(nome, qtd=1):
    global ranking_global
    if not nome or nome=='BOT GK': return
    nome=nome.upper()[:12]
    ranking_global['assistentes'][nome]=ranking_global['assistentes'].get(nome,0)+qtd
    asyncio.create_task(save_ranking(ranking_global))

def update_ranking_mvp(nome, pontos=1):
    global ranking_global
    if not nome or nome=='BOT GK': return
    nome=nome.upper()[:12]
    ranking_global['mvp'][nome]=ranking_global['mvp'].get(nome,0)+pontos
    asyncio.create_task(save_ranking(ranking_global))

def update_ranking_jogo(nomes):
    global ranking_global
    for n in nomes:
        if not n or n=='BOT GK': continue
        n=n.upper()[:12]
        ranking_global['jogos'][n]=ranking_global['jogos'].get(n,0)+1
    asyncio.create_task(save_ranking(ranking_global))

def update_ranking_vitoria(nome, qtd=1):
    global ranking_global
    if not nome or nome=='BOT GK': return
    nome=nome.upper()[:12]
    if 'vitorias' not in ranking_global: ranking_global['vitorias']={}
    ranking_global['vitorias'][nome]=ranking_global['vitorias'].get(nome,0)+qtd
    asyncio.create_task(save_ranking(ranking_global))

def update_ranking_derrota(nome, qtd=1):
    global ranking_global
    if not nome or nome=='BOT GK': return
    nome=nome.upper()[:12]
    if 'derrotas' not in ranking_global: ranking_global['derrotas']={}
    ranking_global['derrotas'][nome]=ranking_global['derrotas'].get(nome,0)+qtd
    asyncio.create_task(save_ranking(ranking_global))

def update_ranking_empate(nome, qtd=1):
    global ranking_global
    if not nome or nome=='BOT GK': return
    nome=nome.upper()[:12]
    if 'empates' not in ranking_global: ranking_global['empates']={}
    ranking_global['empates'][nome]=ranking_global['empates'].get(nome,0)+qtd
    asyncio.create_task(save_ranking(ranking_global))

def update_ranking_resultados(jogo, vencedor):
    global ranking_global
    try:
        for sid,j in jogo['jogadores'].items():
            nome=j['nome']
            if not nome or nome=='BOT GK': continue
            if vencedor is None:
                update_ranking_empate(nome,1)
            elif j['equipa']==vencedor:
                update_ranking_vitoria(nome,1)
            else:
                update_ranking_derrota(nome,1)
    except Exception as e:
        print("Erro ranking resultados", e)


ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "futgraal123")  # troque aqui

async def index(request):
    p=os.path.join(os.path.dirname(__file__),'index.html')
    return web.FileResponse(p) if os.path.exists(p) else web.Response(text="index.html nao encontrado",status=404)
app.router.add_get('/', index)

# ============== ADMIN PAINEL COMPLETO ==============
def check_admin(request):
    # Verifica senha via ?key= ou header ou cookie simples
    key = request.query.get('key','') or request.headers.get('X-Admin-Key','')
    # Permite se não tem senha configurada ou se bate
    if key == ADMIN_PASSWORD:
        return True
    # Também aceita cookie
    if request.cookies.get('admin_key') == ADMIN_PASSWORD:
        return True
    return False

async def admin_page(request):
    # Serve painel HTML
    p=os.path.join(os.path.dirname(__file__),'admin.html')
    if os.path.exists(p):
        return web.FileResponse(p)
    # Se não existe admin.html, retorna versão inline
    html = open_admin_html()
    return web.Response(text=html, content_type='text/html')

def open_admin_html():
    return '''
<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ADMIN - FutGraal</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@600;800&display=swap');
*{box-sizing:border-box;font-family:Montserrat,sans-serif}
body{margin:0;background:#0b0e0b;color:#fff;padding:16px}
h1{margin:0 0 12px;font-size:22px}
.card{background:#151515;border:1px solid #222;border-radius:12px;padding:14px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.stat{font-size:26px;font-weight:800;color:#00ffcc}
button{padding:8px 12px;border-radius:8px;border:none;font-weight:800;cursor:pointer}
.btn{ background:#00ffcc;color:#000 }
.btn-danger{ background:#ff3b30;color:#fff }
.btn-ghost{ background:#222;color:#fff;border:1px solid #333 }
input,select{background:#1f1f1f;border:1px solid #333;color:#fff;padding:8px 10px;border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:8px;border-bottom:1px solid #222;text-align:left}
th{color:#888;font-size:10px;letter-spacing:0.6px}
.badge{padding:2px 6px;border-radius:10px;font-size:10px;font-weight:800}
</style>
</head>
<body>
<h1>⚽ FUTGRAAL ADMIN</h1>
<div id="login-box" class="card" style="max-width:360px">
  <h3>Login Admin</h3>
  <p style="font-size:12px;opacity:0.6">Senha padrão: futgraal123 (troque em ADMIN_PASSWORD no servidor.py)</p>
  <input id="admin-pass" type="password" placeholder="Senha admin" style="width:100%;margin:8px 0">
  <button class="btn" onclick="loginAdmin()">Entrar</button>
  <div id="login-err" style="color:#ff7a7a;font-size:11px;margin-top:6px;display:none"></div>
</div>

<div id="painel" style="display:none">
  <div class="grid">
    <div class="card"><div>Total Contas</div><div id="stat-contas" class="stat">0</div></div>
    <div class="card"><div>Online Agora</div><div id="stat-online" class="stat">0</div></div>
    <div class="card"><div>Salas Ativas</div><div id="stat-salas" class="stat">0</div></div>
    <div class="card"><div>Partidas Jogando</div><div id="stat-jogando" class="stat">0</div></div>
  </div>

  <div class="card">
    <h3>🎮 Salas Ativas</h3>
    <div id="lista-salas-admin">Carregando...</div>
    <button class="btn-ghost" onclick="loadSalas()">Atualizar</button>
  </div>

  <div class="card">
    <h3>👥 Contas & Logados</h3>
    <div style="display:flex;gap:8px;margin-bottom:8px">
      <input id="busca-conta" placeholder="Buscar nick" oninput="filtrarContas()">
      <button class="btn-ghost" onclick="loadContas()">Atualizar</button>
    </div>
    <div style="overflow:auto;max-height:320px">
      <table><thead><tr><th>NICK</th><th>SENHA</th><th>STATUS</th><th>CRIADO</th><th>ULTIMO LOGIN</th><th>AÇÕES</th></tr></thead>
      <tbody id="tbody-contas"></tbody></table>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h3>🏆 Ranking</h3>
      <div id="ranking-preview" style="font-size:12px;max-height:200px;overflow:auto"></div>
      <div style="margin-top:8px;display:flex;gap:8px">
        <button class="btn-danger" onclick="resetRanking()">Resetar Semana</button>
        <button class="btn-ghost" onclick="loadRanking()">Atualizar</button>
      </div>
    </div>
    <div class="card">
      <h3>⚙️ Ações Rápidas</h3>
      <div style="display:flex;flex-direction:column;gap:8px">
        <button class="btn-danger" onclick="fecharTodasSalas()">Fechar Todas as Salas</button>
        <button class="btn-danger" onclick="kickTodos()">Kickar Todos Jogadores</button>
        <button class="btn-ghost" onclick="exportarContas()">Baixar contas.json</button>
        <button class="btn-ghost" onclick="exportarRanking()">Baixar ranking.json</button>
        <hr style="border-color:#222">
        <div style="font-size:11px;opacity:0.7">Criar conta manual</div>
        <div style="display:flex;gap:6px"><input id="new-nick" placeholder="NICK"><input id="new-senha" placeholder="SENHA"><button class="btn" onclick="criarContaManual()">Criar</button></div>
      </div>
    </div>
  </div>
</div>

<script>
let ADMIN_KEY = localStorage.getItem('admin_key') || '';
function headers(){ return {'X-Admin-Key': ADMIN_KEY, 'Content-Type':'application/json'} }
async function api(path, opts={}){
  opts.headers = {...headers(), ...(opts.headers||{})};
  const url = path + (path.includes('?')?'&':'?') + 'key='+encodeURIComponent(ADMIN_KEY);
  const r = await fetch(url, opts);
  if(r.status===401){ document.getElementById('login-box').style.display='block'; document.getElementById('painel').style.display='none'; throw 'unauthorized'; }
  return r;
}
function loginAdmin(){
  const p=document.getElementById('admin-pass').value;
  if(!p) return;
  ADMIN_KEY=p; localStorage.setItem('admin_key', p);
  document.cookie='admin_key='+p+';path=/';
  verificar();
}
async function verificar(){
  try{
    const r=await api('/admin/api/stats');
    if(!r.ok) throw 'fail';
    document.getElementById('login-box').style.display='none';
    document.getElementById('painel').style.display='block';
    loadAll();
  }catch(e){
    document.getElementById('login-err').style.display='block';
    document.getElementById('login-err').textContent='Senha incorreta ou servidor offline';
  }
}
async function loadAll(){ loadStats(); loadContas(); loadSalas(); loadRanking(); }
async function loadStats(){
  const r=await api('/admin/api/stats'); const j=await r.json();
  document.getElementById('stat-contas').textContent=j.total_contas;
  document.getElementById('stat-online').textContent=j.online;
  document.getElementById('stat-salas').textContent=j.salas;
  document.getElementById('stat-jogando').textContent=j.jogando;
}
let contasCache=[];
async function loadContas(){
  const r=await api('/admin/api/contas'); const j=await r.json();
  contasCache=j.contas;
  renderContas(j.contas);
}
function renderContas(lista){
  const tb=document.getElementById('tbody-contas'); tb.innerHTML='';
  const logados = lista.filter(c=>c.online).map(c=>c.nick);
  lista.forEach(c=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><b>${c.nick}</b></td><td><code style="background:#222;padding:2px 6px;border-radius:4px">${c.senha}</code></td><td>${c.online?'<span class=badge style=background:#00ffcc;color:#000>ONLINE</span>':'<span class=badge style=background:#333;color:#888>OFF</span>'}</td><td style="font-size:10px;opacity:0.6">${(c.criado||'').slice(0,10)}</td><td style="font-size:10px;opacity:0.6">${(c.ultimo||'').slice(0,19).replace('T',' ')}</td><td><button class="btn-ghost" style="padding:4px 6px;font-size:10px" onclick="editarSenha('${c.nick}')">Senha</button> <button class="btn-danger" style="padding:4px 6px;font-size:10px" onclick="deletarConta('${c.nick}')">Del</button> ${c.online?`<button class="btn-danger" style="padding:4px 6px;font-size:10px" onclick="kickNick('${c.nick}')">Kick</button>`:''}</td>`;
    tb.appendChild(tr);
  });
}
function filtrarContas(){
  const q=document.getElementById('busca-conta').value.toUpperCase();
  renderContas(contasCache.filter(c=>c.nick.includes(q)));
}
async function deletarConta(nick){
  if(!confirm('Deletar conta '+nick+' ?')) return;
  await api('/admin/api/contas/delete',{method:'POST', body:JSON.stringify({nick})});
  loadContas(); loadStats();
}
async function editarSenha(nick){
  const nova=prompt('Nova senha para '+nick+':');
  if(!nova) return;
  await api('/admin/api/contas/edit',{method:'POST', body:JSON.stringify({nick, senha:nova})});
  loadContas();
}
async function kickNick(nick){
  await api('/admin/api/jogadores/kick',{method:'POST', body:JSON.stringify({nick})});
  loadContas(); loadSalas(); loadStats();
}
async function criarContaManual(){
  const nick=document.getElementById('new-nick').value.toUpperCase().trim();
  const senha=document.getElementById('new-senha').value.trim();
  if(nick.length<3||senha.length<3){ alert('Nick e senha 3+ letras'); return; }
  await api('/admin/api/contas/create',{method:'POST', body:JSON.stringify({nick, senha})});
  document.getElementById('new-nick').value=''; document.getElementById('new-senha').value='';
  loadContas(); loadStats();
}

async function loadSalas(){
  const r=await api('/admin/api/salas'); const j=await r.json();
  const div=document.getElementById('lista-salas-admin');
  if(j.salas.length===0){ div.innerHTML='<span style=opacity:0.5>Nenhuma sala ativa</span>'; return; }
  div.innerHTML=j.salas.map(s=>`<div style="background:#111;border:1px solid #222;border-radius:8px;padding:8px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center"><div><b>${s.nome}</b> <span class=badge style=background:#222>${s.modo}</span> <span class=badge style="background:${s.estado==='jogando'?'#00ffcc':'#333'};color:${s.estado==='jogando'?'#000':'#fff'}">${s.estado.toUpperCase()}</span> <span style="font-size:11px;opacity:0.6">${s.qtd}/${s.max} - ${s.privacidade}</span><br><span style="font-size:11px;opacity:0.5">${s.jogadores.map(j=>j.nome+(j.posicao==='goleiro'?' 🧤':'')).join(', ')}</span></div><div style="display:flex;gap:4px"><button class="btn-danger" style="padding:4px 8px;font-size:10px" onclick="fecharSala('${s.nome}')">Fechar</button></div></div>`).join('');
}
async function fecharSala(nome){ if(!confirm('Fechar sala '+nome+' ?')) return; await api('/admin/api/salas/fechar',{method:'POST', body:JSON.stringify({nome})}); loadSalas(); loadStats(); }
async function fecharTodasSalas(){ if(!confirm('Fechar TODAS as salas?')) return; await api('/admin/api/salas/fechar_todas',{method:'POST'}); loadSalas(); loadStats(); }
async function kickTodos(){ if(!confirm('Kickar TODOS jogadores online?')) return; await api('/admin/api/jogadores/kick_todos',{method:'POST'}); loadSalas(); loadStats(); loadContas(); }

async function loadRanking(){
  const r=await api('/admin/api/ranking'); const j=await r.json();
  const div=document.getElementById('ranking-preview');
  const art=Object.entries(j.ranking.artilheiros||{}).sort((a,b)=>b[1]-a[1]).slice(0,8);
  div.innerHTML='<b>Artilheiros:</b><br>'+ (art.length? art.map(([n,g])=>`${n}: ${g} gols`).join('<br>') : '<span style=opacity:0.5>vazio</span>') + '<br><br>Semana: '+(j.ranking.semana||'?');
}
async function resetRanking(){ if(!confirm('Resetar ranking da semana?')) return; await api('/admin/api/ranking/reset',{method:'POST'}); loadRanking(); }

async function exportarContas(){ window.open('/admin/contas.json?key='+encodeURIComponent(ADMIN_KEY), '_blank'); }
async function exportarRanking(){ window.open('/admin/ranking.json?key='+encodeURIComponent(ADMIN_KEY), '_blank'); }

if(ADMIN_KEY) verificar();
</script>
</body>
</html>
    '''

async def admin_api_stats(request):
    if not check_admin(request):
        return web.Response(status=401, text="Unauthorized - use ?key=sua_senha")
    total = len(contas_global)
    online = len(logados)
    salas_ativas = len(salas)
    jogando = sum(1 for s in salas.values() if s.get('config',{}).get('estado')=='jogando')
    return web.json_response({'total_contas': total, 'online': online, 'salas': salas_ativas, 'jogando': jogando})

async def admin_api_contas(request):
    if not check_admin(request):
        return web.Response(status=401, text="Unauthorized")
    lista=[]
    online_nicks = set(logados.values())
    for nick, dados in contas_global.items():
        lista.append({'nick': nick, 'senha': dados.get('senha',''), 'criado': dados.get('criado_em',''), 'ultimo': dados.get('ultimo_login',''), 'online': nick in online_nicks})
    return web.json_response({'contas': sorted(lista, key=lambda x: x['nick'])})

async def admin_api_contas_delete(request):
    if not check_admin(request): return web.Response(status=401)
    data = await request.json()
    nick = str(data.get('nick','')).upper()
    if nick in contas_global:
        del contas_global[nick]
        save_contas(contas_global)
        # kick se online
        for sid, n in list(logados.items()):
            if n==nick:
                logados.pop(sid, None)
                await sair_sala(sid)
                try: await sio.emit('logout_ok', {}, to=sid)
                except: pass
        return web.json_response({'ok': True})
    return web.json_response({'ok': False, 'msg': 'Conta não existe'}, status=404)

async def admin_api_contas_edit(request):
    if not check_admin(request): return web.Response(status=401)
    data = await request.json()
    nick = str(data.get('nick','')).upper()
    senha = str(data.get('senha','')).strip()
    if len(senha)<3: return web.json_response({'ok': False, 'msg': 'Senha curta'}, status=400)
    if nick in contas_global:
        contas_global[nick]['senha']=senha
        save_contas(contas_global)
        return web.json_response({'ok': True})
    return web.json_response({'ok': False}, status=404)

async def admin_api_contas_create(request):
    if not check_admin(request): return web.Response(status=401)
    data = await request.json()
    nick = str(data.get('nick','')).upper()[:12]
    senha = str(data.get('senha','')).strip()
    if len(nick)<3 or len(senha)<3: return web.json_response({'ok': False}, status=400)
    if nick in contas_global: return web.json_response({'ok': False, 'msg': 'Já existe'}, status=400)
    contas_global[nick]={'senha': senha, 'criado_em': datetime.now().isoformat(), 'ultimo_login': ''}
    save_contas(contas_global)
    return web.json_response({'ok': True})

async def admin_api_salas(request):
    if not check_admin(request): return web.Response(status=401)
    lista=[]
    for nome, jogo in salas.items():
        cfg=jogo.get('config',{})
        jogadores=[]
        for sid, j in jogo['jogadores'].items():
            jogadores.append({'sid': sid, 'nome': j['nome'], 'equipa': j['equipa'], 'posicao': j.get('posicao','linha')})
        lista.append({'nome': nome, 'modo': cfg.get('modo','3v3'), 'estado': cfg.get('estado','espera'), 'privacidade': cfg.get('privacidade','publica'), 'qtd': len(jogo['jogadores']), 'max': cfg.get('max_jogadores',6), 'jogadores': jogadores})
    return web.json_response({'salas': lista})

async def admin_api_salas_fechar(request):
    if not check_admin(request): return web.Response(status=401)
    data = await request.json()
    nome = str(data.get('nome','')).upper()
    if nome in salas:
        jogo=salas[nome]
        for sid in list(jogo['jogadores'].keys())+list(jogo['espectadores'].keys()):
            try: await sio.leave_room(sid, nome)
            except: pass
            jogadores_sala.pop(sid, None)
            espectadores_sala.pop(sid, None)
            try: await sio.emit('forcar_volta_lobby', {}, to=sid)
            except: pass
        del salas[nome]
        await enviar_lista_salas()
        return web.json_response({'ok': True})
    return web.json_response({'ok': False}, status=404)

async def admin_api_salas_fechar_todas(request):
    if not check_admin(request): return web.Response(status=401)
    for nome in list(salas.keys()):
        jogo=salas[nome]
        for sid in list(jogo['jogadores'].keys())+list(jogo['espectadores'].keys()):
            try: await sio.leave_room(sid, nome)
            except: pass
            jogadores_sala.pop(sid, None)
            espectadores_sala.pop(sid, None)
            try: await sio.emit('forcar_volta_lobby', {}, to=sid)
            except: pass
        del salas[nome]
    await enviar_lista_salas()
    return web.json_response({'ok': True})

async def admin_api_kick(request):
    if not check_admin(request): return web.Response(status=401)
    data = await request.json()
    nick = str(data.get('nick','')).upper()
    for sid, n in list(logados.items()):
        if n==nick:
            await sair_sala(sid)
            try: await sio.emit('forcar_volta_lobby', {}, to=sid)
            except: pass
    # Também kick por nome em salas
    for nome, jogo in salas.items():
        for sid, j in list(jogo['jogadores'].items()):
            if j['nome']==nick:
                await sair_sala(sid)
    await enviar_lista_salas()
    return web.json_response({'ok': True})

async def admin_api_kick_todos(request):
    if not check_admin(request): return web.Response(status=401)
    for sid in list(jogadores_sala.keys())+list(espectadores_sala.keys()):
        await sair_sala(sid)
        try: await sio.emit('forcar_volta_lobby', {}, to=sid)
        except: pass
    await enviar_lista_salas()
    return web.json_response({'ok': True})

async def admin_api_ranking(request):
    if not check_admin(request): return web.Response(status=401)
    return web.json_response({'ranking': ranking_global})

async def admin_api_ranking_reset(request):
    if not check_admin(request): return web.Response(status=401)
    global ranking_global
    ranking_global = {'semana': get_week_id(), 'artilheiros': {}, 'assistentes': {}, 'mvp': {}, 'jogos': {}, 'vitorias': {}, 'derrotas': {}, 'empates': {}}
    save_ranking(ranking_global)
    await sio.emit('ranking_atualizado', ranking_global)
    return web.json_response({'ok': True})

async def admin_contas_json(request):
    if not check_admin(request): return web.Response(status=401, text="Unauthorized - ?key=futgraal123")
    # Agora ele entrega os dados diretamente da memória (que veio do MongoDB)
    return web.json_response(contas_global)

async def admin_ranking_json(request):
    if not check_admin(request): return web.Response(status=401)
    # Entrega o ranking atualizado em tempo real da nuvem
    return web.json_response(ranking_global)

app.router.add_get('/admin', admin_page)
app.router.add_get('/admin/contas', admin_page)  # redireciona pro painel novo
app.router.add_get('/admin/contas.json', admin_contas_json)
app.router.add_get('/admin/ranking.json', admin_ranking_json)
app.router.add_get('/admin/api/stats', admin_api_stats)
app.router.add_get('/admin/api/contas', admin_api_contas)
app.router.add_post('/admin/api/contas/delete', admin_api_contas_delete)
app.router.add_post('/admin/api/contas/edit', admin_api_contas_edit)
app.router.add_post('/admin/api/contas/create', admin_api_contas_create)
app.router.add_get('/admin/api/salas', admin_api_salas)
app.router.add_post('/admin/api/salas/fechar', admin_api_salas_fechar)
app.router.add_post('/admin/api/salas/fechar_todas', admin_api_salas_fechar_todas)
app.router.add_post('/admin/api/jogadores/kick', admin_api_kick)
app.router.add_post('/admin/api/jogadores/kick_todos', admin_api_kick_todos)
app.router.add_get('/admin/api/ranking', admin_api_ranking)
app.router.add_post('/admin/api/ranking/reset', admin_api_ranking_reset)
# ============== FIM ADMIN ==============



async def enviar_lista_salas():
    lista=[]
    for nome,s in salas.items():
        cfg=s.get('config',{})
        lista.append({
            'nome':nome,
            'qtd':len(s['jogadores']),
            'max':cfg.get('max_jogadores',6),
            'modo':cfg.get('modo','3v3'),
            'estado':cfg.get('estado','espera'),
            'privacidade':cfg.get('privacidade','publica'),
            'goleiro':cfg.get('goleiro_bot',True),
            'timeA':cfg.get('nome_time_esq','CASA'),
            'timeB':cfg.get('nome_time_dir','FORA'),
            'estadio':cfg.get('estadio','grama'),
            'clima':cfg.get('clima','sol'),
            'tem_torneio': cfg.get('torneio_ativo',False)
        })
    await sio.emit('salas_atualizadas', lista)
    # envia ranking também
    await sio.emit('ranking_atualizado', ranking_global)

def tem_goleiro_humano(jogo, equipa):
    for j in jogo['jogadores'].values():
        if j['equipa']==equipa and j.get('posicao')=='goleiro':
            return True
    return False

def init_stats():
    return {
        'chutes': {'esquerda':0, 'direita':0},
        'chutes_no_gol': {'esquerda':0, 'direita':0},
        'defesas': {'esquerda':0, 'direita':0},
        'posse_esq_ticks': 0,
        'posse_dir_ticks': 0,
        'gols_jogadores': {},
        'assist_jogadores': {},
        'chutes_jogadores': {},
        'defesas_jogadores': {},
        'toques_recentes': []  # lista de {nome, equipa, time}
    }

def calcular_mvp(jogo):
    est=jogo.get('estatisticas') or init_stats()
    scores={}
    for nome,gols in est.get('gols_jogadores',{}).items():
        scores[nome]=scores.get(nome,0)+gols*10
    for nome,ast in est.get('assist_jogadores',{}).items():
        scores[nome]=scores.get(nome,0)+ast*7
    for nome,ch in est.get('chutes_jogadores',{}).items():
        scores[nome]=scores.get(nome,0)+ch*1
    for nome,df in est.get('defesas_jogadores',{}).items():
        scores[nome]=scores.get(nome,0)+df*5
    if not scores:
        return None
    # pega maior
    mvp_nome = max(scores, key=lambda k: scores[k])
    return {'nome': mvp_nome, 'pontos': scores[mvp_nome], 'scores': scores}

def sanitize_jogo_for_emit(jogo):
    # remove campos não serializáveis como set()
    try:
        return {
            'bola': jogo.get('bola'),
            'jogadores': jogo.get('jogadores'),
            'bots': jogo.get('bots'),
            'placar': jogo.get('placar'),
            'tempo_restante': jogo.get('tempo_restante'),
            'estado_partida': jogo.get('estado_partida'),
            'config': jogo.get('config'),
            'traves': jogo.get('traves'),
            'estatisticas': jogo.get('estatisticas'),
            'ultimo_toque': jogo.get('ultimo_toque'),
            'espectadores': jogo.get('espectadores'),
        }
    except:
        return jogo

def build_stats_payload(jogo):
    est=jogo.get('estatisticas') or init_stats()
    total=est.get('posse_esq_ticks',0)+est.get('posse_dir_ticks',0)
    if total < 2:
        posse_esq=50
        posse_dir=50
    else:
        posse_esq=round(est['posse_esq_ticks']/total*100)
        posse_dir=100-posse_esq
    mvp = calcular_mvp(jogo)
    return {
        'chutes': est.get('chutes', {'esquerda':0,'direita':0}),
        'chutes_no_gol': est.get('chutes_no_gol', {'esquerda':0,'direita':0}),
        'defesas': est.get('defesas', {'esquerda':0,'direita':0}),
        'posse': {'esquerda': posse_esq, 'direita': posse_dir},
        'gols_jogadores': est.get('gols_jogadores', {}),
        'assist_jogadores': est.get('assist_jogadores', {}),
        'chutes_jogadores': est.get('chutes_jogadores', {}),
        'defesas_jogadores': est.get('defesas_jogadores', {}),
        'mvp': mvp
    }

def criar_sala(nome, owner_sid, dados):
    modo=dados.get('modo','3v3')
    if modo not in ['1v1','3v3','torneio']: modo='3v3'
    max_j=2 if modo=='1v1' else 8 if modo=='torneio' else 6
    priv=dados.get('privacidade','publica')
    senha=str(dados.get('senha',''))[:8] if priv=='privada' else None
    goleiro=bool(dados.get('goleiro_bot',True))
    tempo_cfg=int(dados.get('tempo',180))
    if tempo_cfg not in [60,120,180,300,600]: tempo_cfg=180
    estadio=dados.get('estadio','grama')
    if estadio not in ['grama','areia','neve','rua','quadra']: estadio='grama'
    clima=dados.get('clima','sol')
    if clima not in ['sol','chuva','neblina','noite']: clima='sol'
    cor_esq=dados.get('cor_time_esq','#2e7d32')
    cor_dir=dados.get('cor_time_dir','#c62828')

    salas[nome]={
        'config':{
            'owner':owner_sid,
            'modo':modo,
            'max_jogadores':max_j,
            'privacidade':priv,
            'senha':senha,
            'goleiro_bot':goleiro,
            'estado':'espera',
            'nome_time_esq':str(dados.get('nome_time_esq','CASA')[:10].upper() or 'CASA'),
            'nome_time_dir':str(dados.get('nome_time_dir','FORA')[:10].upper() or 'FORA'),
            'tempo_cfg':tempo_cfg,
            'estadio':estadio,
            'clima':clima,
            'cor_time_esq':cor_esq,
            'cor_time_dir':cor_dir,
            'torneio_ativo': False,
            'torneio': None
        },
        'bola':{'x':400,'y':300,'vx':0,'vy':0,'raio':10,'fogo':0},
        'jogadores':{},
        'espectadores':{},
        'bots':{},
        'mutados': set(),
        'placar':{'esquerda':0,'direita':0},
        'tempo_restante':tempo_cfg,
        'estado_partida':'espera',
        'penalti':None,
        'traves':[{'x':8,'y':200,'r':9},{'x':8,'y':400,'r':9},{'x':792,'y':200,'r':9},{'x':792,'y':400,'r':9}],
        'estatisticas': init_stats(),
        'ultimo_toque': None
    }
    return salas[nome]

def criar_bots(jogo):
    if not jogo['config'].get('goleiro_bot'):
        jogo['bots']={}
        return
    bots={}
    if not tem_goleiro_humano(jogo,'esquerda'):
        bots['bot_esq']={'x':35,'y':300,'vx':0,'vy':0,'raio':20,'equipa':'esquerda','cor1':'#666','cor2':'#000','nome':'BOT GK','stamina':100,'posicao':'goleiro'}
    if not tem_goleiro_humano(jogo,'direita'):
        bots['bot_dir']={'x':765,'y':300,'vx':0,'vy':0,'raio':20,'equipa':'direita','cor1':'#666','cor2':'#000','nome':'BOT GK','stamina':100,'posicao':'goleiro'}
    jogo['bots']=bots

def reiniciar_posicoes(jogo):
    b=jogo['bola']; b['x'],b['y'],b['vx'],b['vy'],b['fogo']=400,300,0,0,0
    idx_e=idx_d=0
    for sid,j in jogo['jogadores'].items():
        if j.get('posicao')=='goleiro':
            j['x']=50 if j['equipa']=='esquerda' else 750
            j['y']=300
        else:
            if j['equipa']=='esquerda':
                j['x']=160+ (idx_e%2)*40
                j['y']=200+ idx_e*70
                idx_e+=1
            else:
                j['x']=640- (idx_d%2)*40
                j['y']=200+ idx_d*70
                idx_d+=1
        j['vx']=j['vy']=0; j['stamina']=100
        # reseta gols contra no inicio da partida (mantem se quiser levar pra proxima, mas vamos resetar)
        j['gols_contra']=0
    if 'bot_esq' in jogo['bots']: jogo['bots']['bot_esq'].update({'x':35,'y':300,'vx':0,'vy':0})
    if 'bot_dir' in jogo['bots']: jogo['bots']['bot_dir'].update({'x':765,'y':300,'vx':0,'vy':0})
    jogo['ultimo_toque']=None
    if 'estatisticas' in jogo and 'toques_recentes' in jogo['estatisticas']:
        jogo['estatisticas']['toques_recentes']=[]

async def processo_golo(nome_sala, equipa_gol):
    jogo=salas.get(nome_sala)
    if not jogo: return
    est=jogo.get('estatisticas')
    if not est:
        est=init_stats()
        jogo['estatisticas']=est
    ultimo=jogo.get('ultimo_toque')
    assist_nome=None
    is_gol_contra=False
    # detecta gol contra
    if ultimo and ultimo.get('equipa')!=equipa_gol:
        is_gol_contra=True

    # calcula assistencia: penultimo toque do mesmo time (só se não for contra)
    toques = est.get('toques_recentes',[])
    if len(toques)>=2 and not is_gol_contra:
        if ultimo:
            for t in reversed(toques[:-1]):
                if t['equipa']==equipa_gol and t['nome']!=ultimo.get('nome') and (datetime.now() - datetime.fromisoformat(t['time'])).total_seconds() < 4:
                    assist_nome=t['nome']
                    break

    if is_gol_contra and ultimo:
        # GOL CONTRA - conta pro time que fez o gol, mas marca contra pro jogador
        nome_jog=ultimo.get('nome','DESCONHECIDO')
        sid_jog=ultimo.get('sid')
        # incrementa contador de gols contra no jogador
        if sid_jog and sid_jog in jogo['jogadores']:
            jogo['jogadores'][sid_jog]['gols_contra']=jogo['jogadores'][sid_jog].get('gols_contra',0)+1
            gc=jogo['jogadores'][sid_jog]['gols_contra']
            await sio.emit('nova_mensagem', {'nome':'VAR','mensagem': f"⚠️ {nome_jog} fez gol contra! ({gc}/3)",'cor':'#ff3b30'}, room=nome_sala)
            if gc>=3:
                # transforma em espectador (anti-troll)
                try:
                    jog=jogo['jogadores'].pop(sid_jog)
                    jogo['espectadores'][sid_jog]={'nome':jog['nome'],'cor1':jog['cor1']}
                    jogadores_sala.pop(sid_jog, None)
                    espectadores_sala[sid_jog]=nome_sala
                    await sio.enter_room(sid_jog, nome_sala)
                    await sio.emit('voce_e_espectador', {'espectador':True,'motivo':'3 gols contra - anti-troll'}, to=sid_jog)
                    await sio.emit('nova_mensagem', {'nome':'SISTEMA','mensagem': f"🚫 {nome_jog} virou espectador por 3 gols contra!",'cor':'#ffea00'}, room=nome_sala)
                except Exception as e:
                    print("Erro anti-troll contra", e)
        # mesmo sendo contra, conta gol pro placar (já vai contar abaixo) e não conta como gol pro artilheiro
        est['gols_jogadores'][f"{nome_jog} (GC)"]=est['gols_jogadores'].get(f"{nome_jog} (GC)",0)+1
    else:
        if ultimo and ultimo.get('equipa')==equipa_gol:
            nome_jog=ultimo.get('nome','DESCONHECIDO')
            est['gols_jogadores'][nome_jog]=est['gols_jogadores'].get(nome_jog,0)+1
            update_ranking_gol(nome_jog,1)
            if assist_nome:
                est['assist_jogadores'][assist_nome]=est['assist_jogadores'].get(assist_nome,0)+1
                update_ranking_assist(assist_nome,1)

    est['chutes_no_gol'][equipa_gol]+=1
    jogo['placar'][equipa_gol]+=1
    jogo['estado_partida']='comemorando'
    await sio.emit('evento_golo', {'equipa':equipa_gol,'tipo':'gol_contra' if is_gol_contra else 'normal','goleador':ultimo.get('nome') if ultimo else '','assist':assist_nome,'gol_contra':is_gol_contra}, room=nome_sala)
    await sio.emit('estado_jogo', sanitize_jogo_for_emit(jogo), room=nome_sala)
    await asyncio.sleep(1.5)
    await asyncio.sleep(1.5)
    if nome_sala in salas:
        jogo=salas[nome_sala]
        if jogo['tempo_restante']<=0:
            jogo['estado_partida']='fim_jogo'
            jogo['config']['estado']='fim'
            vencedor=None
            if jogo['placar']['esquerda']>jogo['placar']['direita']:
                vencedor='esquerda'
            elif jogo['placar']['direita']>jogo['placar']['esquerda']:
                vencedor='direita'
            payload_stats=build_stats_payload(jogo)
            nomes=[j['nome'] for j in jogo['jogadores'].values()]
            update_ranking_jogo(nomes)
            update_ranking_resultados(jogo, vencedor)
            if payload_stats.get('mvp'):
                update_ranking_mvp(payload_stats['mvp']['nome'], payload_stats['mvp']['pontos'])
            if jogo['config'].get('torneio_ativo') and jogo['config'].get('torneio'):
                await processar_torneio_gol(nome_sala, vencedor)
                return
            await sio.emit('fim_jogo', {
                'vencedor':vencedor,
                'placar':jogo['placar'],
                'nome_time_esq':jogo['config']['nome_time_esq'],
                'nome_time_dir':jogo['config']['nome_time_dir'],
                'estatisticas': payload_stats,
                'empate': vencedor is None,
                'cor_time_esq': jogo['config']['cor_time_esq'],
                'cor_time_dir': jogo['config']['cor_time_dir']
            }, room=nome_sala)
            await sio.emit('ranking_atualizado', ranking_global, room=nome_sala)
        else:
            reiniciar_posicoes(jogo)
            jogo['estado_partida']='jogando'

async def processar_torneio_gol(nome_sala, vencedor):
    jogo=salas.get(nome_sala)
    if not jogo: return
    torneio=jogo['config'].get('torneio')
    if not torneio: return
    # encontra partida atual
    rodada_atual=torneio['rodada_atual']
    partida_idx=torneio['partida_atual_idx']
    if rodada_atual >= len(torneio['chaves']):
        return
    partida=torneio['chaves'][rodada_atual][partida_idx]
    # define vencedor do confronto
    if vencedor=='esquerda':
        partida['vencedor']=partida['timeA']
        partida['placar']=f"{jogo['placar']['esquerda']}-{jogo['placar']['direita']}"
    elif vencedor=='direita':
        partida['vencedor']=partida['timeB']
        partida['placar']=f"{jogo['placar']['esquerda']}-{jogo['placar']['direita']}"
    else:
        # empate no torneio = prorrogação ou pênaltis - escolhe aleatório pro MVP
        partida['vencedor']=random.choice([partida['timeA'],partida['timeB']])
        partida['placar']=f"{jogo['placar']['esquerda']}-{jogo['placar']['direita']} (P)"
    # avança
    torneio['partida_atual_idx']+=1
    payload_stats=build_stats_payload(jogo)
    await sio.emit('fim_jogo_torneio', {
        'vencedor_partida': partida['vencedor'],
        'placar': jogo['placar'],
        'estatisticas': payload_stats,
        'torneio': torneio,
        'partida': partida
    }, room=nome_sala)
    # verifica se rodada acabou
    if torneio['partida_atual_idx'] >= len(torneio['chaves'][rodada_atual]):
        # monta próxima rodada
        vencedores=[p['vencedor'] for p in torneio['chaves'][rodada_atual] if p.get('vencedor')]
        if len(vencedores)==1:
            # campeão
            torneio['campeao']=vencedores[0]
            torneio['estado']='finalizado'
            await sio.emit('torneio_finalizado', {'campeao': vencedores[0], 'torneio': torneio}, room=nome_sala)
            # volta lobby
            jogo['estado_partida']='fim_jogo'
            jogo['config']['estado']='fim'
            return
        else:
            nova_rodada=[]
            for i in range(0,len(vencedores),2):
                if i+1 < len(vencedores):
                    nova_rodada.append({'timeA': vencedores[i], 'timeB': vencedores[i+1], 'vencedor': None, 'placar': ''})
            torneio['chaves'].append(nova_rodada)
            torneio['rodada_atual']+=1
            torneio['partida_atual_idx']=0
    # prepara próxima partida
    if torneio['estado']!='finalizado':
        prox = torneio['chaves'][torneio['rodada_atual']][torneio['partida_atual_idx']]
        jogo['config']['nome_time_esq']=prox['timeA']
        jogo['config']['nome_time_dir']=prox['timeB']
        jogo['placar']={'esquerda':0,'direita':0}
        jogo['tempo_restante']=jogo['config']['tempo_cfg']
        jogo['estado_partida']='espera'
        jogo['config']['estado']='espera'
        reiniciar_posicoes(jogo)
        await sio.emit('torneio_atualizado', {'torneio': torneio, 'proxima': prox}, room=nome_sala)
        await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=nome_sala)

async def loop_tempo():
    while True:
        try:
            for nome,jogo in list(salas.items()):
                if jogo['config']['estado']=='jogando' and jogo['estado_partida']=='jogando':
                    if jogo['tempo_restante'] > 0:
                        jogo['tempo_restante'] -= 1
                    if jogo['tempo_restante'] <= 0:
                        jogo['estado_partida']='fim_jogo'
                        jogo['config']['estado']='fim'
                        vencedor=None
                        if jogo['placar']['esquerda']>jogo['placar']['direita']:
                            vencedor='esquerda'
                        elif jogo['placar']['direita']>jogo['placar']['esquerda']:
                            vencedor='direita'
                        payload_stats=build_stats_payload(jogo)
                        nomes=[j['nome'] for j in jogo['jogadores'].values()]
                        update_ranking_jogo(nomes)
                        update_ranking_resultados(jogo, vencedor)
                        if payload_stats.get('mvp'):
                            update_ranking_mvp(payload_stats['mvp']['nome'], payload_stats['mvp']['pontos'])
                        if jogo['config'].get('torneio_ativo') and jogo['config'].get('torneio'):
                            await processar_torneio_gol(nome, vencedor)
                        else:
                            await sio.emit('fim_jogo', {
                                'vencedor':vencedor,
                                'placar':jogo['placar'],
                                'nome_time_esq':jogo['config']['nome_time_esq'],
                                'nome_time_dir':jogo['config']['nome_time_dir'],
                                'estatisticas': payload_stats,
                                'empate': vencedor is None,
                                'cor_time_esq': jogo['config']['cor_time_esq'],
                                'cor_time_dir': jogo['config']['cor_time_dir']
                            }, room=nome)
                            await sio.emit('ranking_atualizado', ranking_global, room=nome)
                        await enviar_lista_salas()
        except Exception as e:
            print(f"ERRO TEMPO {e}")
            traceback.print_exc()
        await asyncio.sleep(1)

async def loop_fisica():
    print("Motor V4.0 - MVP + Ranking + Torneio + Clima")
    while True:
        try:
            for nome_sala,jogo in list(salas.items()):
                estado=jogo['config']['estado']
                part=jogo['estado_partida']
                if estado=='espera' or part in ['comemorando','fim_jogo']:
                    # FIX: não spamma estado_espera 60x por segundo - só a cada 0.8s
                    now_ts = asyncio.get_event_loop().time()
                    if 'last_espera_emit' not in jogo or now_ts - jogo['last_espera_emit'] > 0.8:
                        jogo['last_espera_emit'] = now_ts
                        await sio.emit('estado_jogo', sanitize_jogo_for_emit(jogo), room=nome_sala)
                        await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo.get('espectadores',{})}, room=nome_sala)
                    continue
                if 'estatisticas' not in jogo:
                    jogo['estatisticas']=init_stats()
                b=jogo['bola']
                if b['x'] < W/2 - 10:
                    jogo['estatisticas']['posse_esq_ticks']+=1
                elif b['x'] > W/2 + 10:
                    jogo['estatisticas']['posse_dir_ticks']+=1
                else:
                    jogo['estatisticas']['posse_esq_ticks']+=0.5
                    jogo['estatisticas']['posse_dir_ticks']+=0.5
                for bot in jogo.get('bots',{}).values():
                    bola=jogo['bola']
                    alvo_y=max(G_SUP+15, min(G_INF-15, bola['y']))
                    bot['vy']+=(alvo_y-bot['y'])*0.14; bot['vy']*=0.84; bot['y']+=bot['vy']
                    base_x=35 if bot['equipa']=='esquerda' else 765
                    if (bot['equipa']=='esquerda' and bola['x']<260) or (bot['equipa']=='direita' and bola['x']>540):
                        alvo_x=bola['x']*0.22+base_x*0.78
                    else:
                        alvo_x=base_x
                    bot['vx']+=(alvo_x-bot['x'])*0.11; bot['vx']*=0.84; bot['x']+=bot['vx']
                    if math.hypot(bola['x']-bot['x'], bola['y']-bot['y'])<32:
                        ang=0 if bot['equipa']=='esquerda' else math.pi
                        ang+=random.uniform(-0.3,0.3)
                        bola['vx']=math.cos(ang)*11; bola['vy']=math.sin(ang)*11
                        if (bot['equipa']=='esquerda' and bola['x']<120) or (bot['equipa']=='direita' and bola['x']>680):
                            if G_SUP-30 <= bola['y'] <= G_INF+30:
                                jogo['estatisticas']['defesas'][bot['equipa']]+=1
                for j in jogo['jogadores'].values():
                    # --- NOVO: TEMPORIZADOR DO EMOTE ---
                    if j.get('emote_timer', 0) > 0:
                        j['emote_timer'] -= 1
                        if j['emote_timer'] <= 0:
                            j['emote'] = ""
                    acel=2.2 if (j.get('boost') and j['stamina']>0) else 1.1
                    if j.get('boost') and j['stamina']>0: j['stamina']-=1.6
                    elif j['stamina']<100: j['stamina']+=0.55
                    j['stamina']=max(0,min(100,j['stamina']))
                    j['vx']+=j.get('input_x',0)*acel; j['vy']+=j.get('input_y',0)*acel
                    j['vx']*=ATR_JOG; j['vy']*=ATR_JOG
                    j['x']=max(j['raio'], min(W-j['raio'], j['x']+j['vx']))
                    j['y']=max(j['raio'], min(H-j['raio'], j['y']+j['vy']))
                sids=list(jogo['jogadores'].keys())
                for i in range(len(sids)):
                    for k in range(i+1,len(sids)):
                        p1,p2=jogo['jogadores'][sids[i]], jogo['jogadores'][sids[k]]
                        dx,dy=p1['x']-p2['x'], p1['y']-p2['y']; d=math.hypot(dx,dy); sm=p1['raio']+p2['raio']
                        if d<sm and d>0:
                            nx,ny=dx/d, dy/d; ov=sm-d
                            p1['x']+=nx*ov/2; p1['y']+=ny*ov/2; p2['x']-=nx*ov/2; p2['y']-=ny*ov/2
                b=jogo['bola']; b['x']+=b['vx']; b['y']+=b['vy']; b['vx']*=ATR_BOLA; b['vy']*=ATR_BOLA
                if abs(b['vx'])<0.1: b['vx']=0
                if abs(b['vy'])<0.1: b['vy']=0
                if b['fogo']>0: b['fogo']-=1
                for sid_key, ent in jogo['jogadores'].items():
                    dx,dy=b['x']-ent['x'], b['y']-ent['y']; d=math.hypot(dx,dy); dm=ent['raio']+b['raio']
                    if d<dm and d>0:
                        nx,ny=dx/d, dy/d; b['vx']+=nx*1.7; b['vy']+=ny*1.7; b['x']+=nx*(dm-d); b['y']+=ny*(dm-d)
                        # registra toque
                        jogo['ultimo_toque']={'equipa':ent['equipa'],'sid':sid_key,'nome':ent['nome']}
                        est=jogo['estatisticas']
                        est['toques_recentes'].append({'nome':ent['nome'],'equipa':ent['equipa'],'time':datetime.now().isoformat()})
                        if len(est['toques_recentes'])>8:
                            est['toques_recentes']=est['toques_recentes'][-8:]
                        if ent.get('posicao')=='goleiro':
                            if (ent['equipa']=='esquerda' and b['x']<130) or (ent['equipa']=='direita' and b['x']>670):
                                if G_SUP-30 <= b['y'] <= G_INF+30:
                                    if abs(b['vx'])>2:
                                        jogo['estatisticas']['defesas'][ent['equipa']]+=1
                                        est['defesas_jogadores'][ent['nome']]=est['defesas_jogadores'].get(ent['nome'],0)+1
                for bot_id, bot_ent in jogo.get('bots',{}).items():
                    dx,dy=b['x']-bot_ent['x'], b['y']-bot_ent['y']; d=math.hypot(dx,dy); dm=bot_ent['raio']+b['raio']
                    if d<dm and d>0:
                        nx,ny=dx/d, dy/d; b['vx']+=nx*1.7; b['vy']+=ny*1.7; b['x']+=nx*(dm-d); b['y']+=ny*(dm-d)
                for tr in jogo['traves']:
                    dx,dy=b['x']-tr['x'], b['y']-tr['y']; d=math.hypot(dx,dy); dm=tr['r']+b['raio']
                    if d<dm and d>0:
                        nx,ny=dx/d, dy/d
                        b['vx']=nx*abs(b['vx'])*0.85+nx*3; b['vy']=ny*abs(b['vy'])*0.85+ny*3
                        b['x']+=nx*(dm-d); b['y']+=ny*(dm-d)
                        await sio.emit('evento_som','trave', room=nome_sala)
                rb=b['raio']
                if b['x']-rb<=0:
                    if G_SUP<=b['y']<=G_INF:
                        await sio.emit('evento_golo', {'equipa':'direita','tipo':'normal'}, room=nome_sala)
                        asyncio.create_task(processo_golo(nome_sala,'direita'))
                    else:
                        b['x'],b['vx']=rb, b['vx']*-0.8
                elif b['x']+rb>=W:
                    if G_SUP<=b['y']<=G_INF:
                        await sio.emit('evento_golo', {'equipa':'esquerda','tipo':'normal'}, room=nome_sala)
                        asyncio.create_task(processo_golo(nome_sala,'esquerda'))
                    else:
                        b['x'],b['vx']=W-rb, b['vx']*-0.8
                if b['y']-rb<=0: b['y'],b['vy']=rb, b['vy']*-0.8
                elif b['y']+rb>=H: b['y'],b['vy']=H-rb, b['vy']*-0.8
                await sio.emit('estado_jogo', sanitize_jogo_for_emit(jogo), room=nome_sala)
        except Exception as e:
            print(e); traceback.print_exc()
        await asyncio.sleep(1/60)

@sio.event
async def connect(sid,environ): 
    await enviar_lista_salas()
    await sio.emit('ranking_atualizado', ranking_global, to=sid)
    if sid in logados:
        await sio.emit('login_ok', {'nick': logados[sid]}, to=sid)

@sio.event
async def login(sid, dados):
    try:
        nick = str(dados.get('nick','') or dados.get('nome','')).strip().upper()[:12]
        senha = str(dados.get('senha','')).strip()
        if len(nick) < 3:
            await sio.emit('login_erro', {'msg': 'Nick precisa ter 3+ letras'}, to=sid); return
        if len(senha) < 3:
            await sio.emit('login_erro', {'msg': 'Senha precisa ter 3+ letras'}, to=sid); return
        for s, n in list(logados.items()):
            if n == nick and s != sid:
                logados.pop(s, None)
                await sair_sala(s)
        if nick not in contas_global:
            await sio.emit('login_erro', {'msg': f'Conta {nick} não existe! Vá em CRIAR CONTA.'}, to=sid); return
        if contas_global[nick].get('senha') != senha:
            await sio.emit('login_erro', {'msg': 'Senha incorreta!'}, to=sid); return
        logados[sid] = nick
        contas_global[nick]['ultimo_login'] = datetime.now().isoformat()
        await save_contas_db(contas_global)
        await sio.emit('login_ok', {'nick': nick}, to=sid)
        print(f"[LOGIN] {nick} logou - SID {sid}")
        await enviar_lista_salas()
    except Exception as e:
        print(f"Erro login: {e}"); traceback.print_exc()
        await sio.emit('login_erro', {'msg': 'Erro interno no login'}, to=sid)

@sio.event
async def criar_conta(sid, dados):
    try:
        nick = str(dados.get('nick','') or dados.get('nome','')).strip().upper()[:12]
        senha = str(dados.get('senha','')).strip()
        if len(nick) < 3:
            await sio.emit('login_erro', {'msg': 'Nick precisa ter 3+ letras'}, to=sid); return
        if len(senha) < 3:
            await sio.emit('login_erro', {'msg': 'Senha precisa ter 3+ letras'}, to=sid); return
        if nick in contas_global:
            await sio.emit('login_erro', {'msg': f'Nick {nick} já existe! Vá em ENTRAR pra logar.'}, to=sid); return
        for s, n in list(logados.items()):
            if n == nick and s != sid:
                logados.pop(s, None)
                await sair_sala(s)
        contas_global[nick] = {'senha': senha, 'criado_em': datetime.now().isoformat(), 'ultimo_login': datetime.now().isoformat()}
        await save_contas_db(contas_global)
        logados[sid] = nick
        await sio.emit('login_ok', {'nick': nick, 'novo': True}, to=sid)
        print(f"[CRIAR CONTA] {nick} criada - SID {sid}")
        await enviar_lista_salas()
    except Exception as e:
        print(f"Erro criar conta: {e}"); traceback.print_exc()
        await sio.emit('login_erro', {'msg': 'Erro ao criar conta'}, to=sid)

@sio.event
async def entrar_jogo(sid,dados):
    try:
        if sid not in logados:
            await sio.emit('erro_entrada', {'msg': 'Faça login primeiro! Crie conta na tela inicial'}, to=sid); return
        nick_logado = logados[sid]
        nome_sala=str(dados.get('sala','GERAL')).upper()[:12]
        nome_jog = nick_logado[:10].upper()
        senha_t=str(dados.get('senha',''))
        posicao=dados.get('posicao','linha')
        if posicao not in ['linha','goleiro']: posicao='linha'
        for s_id, j in list((salas.get(nome_sala, {}).get('jogadores', {})).items()):
            if j.get('nome') == nome_jog and s_id != sid:
                await sio.emit('erro_entrada', {'msg': f'Nick {nome_jog} já está na sala!'}, to=sid); return
        if nome_sala not in salas:
            jogo=criar_sala(nome_sala,sid,dados)
            await sio.enter_room(sid,nome_sala); jogadores_sala[sid]=nome_sala
            jogo['jogadores'][sid]={'nome':nome_jog,'cor1':dados.get('cor1','#fff'),'cor2':dados.get('cor2','#000'),'x':200,'y':300,'vx':0,'vy':0,'input_x':0,'input_y':0,'raio':22 if posicao=='goleiro' else 20,'equipa':'esquerda','stamina':100,'boost':False,'posicao':posicao,'gols_contra':0}
            await sio.emit('voce_e_dono', {'dono':True}, to=sid)
            await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=nome_sala)
            await enviar_lista_salas(); return
        jogo=salas[nome_sala]; cfg=jogo['config']
        if cfg['privacidade']=='privada' and cfg.get('senha') and cfg['senha']!=senha_t:
            await sio.emit('erro_entrada', {'msg':'Senha incorreta!'}, to=sid); return
        if len(jogo['jogadores'])>=cfg['max_jogadores']:
            await sio.enter_room(sid,nome_sala); espectadores_sala[sid]=nome_sala
            jogo['espectadores'][sid]={'nome':nome_jog,'cor1':dados.get('cor1','#fff')}
            await sio.emit('voce_e_espectador', {'espectador':True}, to=sid)
            await sio.emit('estado_espera', {'config':cfg,'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=nome_sala)
            await sio.emit('partida_iniciada', {}, to=sid)
            await enviar_lista_salas(); return
        qtd_e=sum(1 for j in jogo['jogadores'].values() if j['equipa']=='esquerda')
        qtd_d=sum(1 for j in jogo['jogadores'].values() if j['equipa']=='direita')
        equipa='esquerda' if qtd_e<=qtd_d else 'direita'
        await sio.enter_room(sid,nome_sala); jogadores_sala[sid]=nome_sala
        jogo['jogadores'][sid]={'nome':nome_jog,'cor1':dados.get('cor1','#fff'),'cor2':dados.get('cor2','#000'),'x':600 if equipa=='direita' else 200,'y':300,'vx':0,'vy':0,'input_x':0,'input_y':0,'raio':22 if posicao=='goleiro' else 20,'equipa':equipa,'stamina':100,'boost':False,'posicao':posicao,'gols_contra':0}
        await sio.emit('voce_e_dono', {'dono':cfg['owner']==sid}, to=sid)
        await sio.emit('estado_espera', {'config':cfg,'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=nome_sala)
        if cfg['estado'] in ['jogando']: await sio.emit('partida_iniciada', {}, to=sid)
        await enviar_lista_salas()
    except Exception as e: print(e); traceback.print_exc()

@sio.event
async def iniciar_partida(sid, dados=None):
    if sid not in jogadores_sala: return
    nome=jogadores_sala[sid]; jogo=salas.get(nome)
    if not jogo or jogo['config']['owner']!=sid: await sio.emit('erro_entrada', {'msg':'So dono inicia!'}, to=sid); return
    if len(jogo['jogadores']) < 2:
        await sio.emit('erro_entrada', {'msg':'Precisa de 2 jogadores ou mais pra começar!'}, to=sid)
        await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=nome)
        return
    jogo['config']['estado']='jogando'; jogo['estado_partida']='jogando'; jogo['tempo_restante']=jogo['config']['tempo_cfg']; jogo['placar']={'esquerda':0,'direita':0}
    jogo['estatisticas']=init_stats()
    jogo['ultimo_toque']=None
    criar_bots(jogo); reiniciar_posicoes(jogo)
    await sio.emit('partida_iniciada', {}, room=nome); await enviar_lista_salas()

@sio.event
async def atualizar_config(sid, dados):
    if sid not in jogadores_sala: return
    nome=jogadores_sala[sid]; jogo=salas.get(nome)
    if not jogo or jogo['config']['owner']!=sid: return
    if jogo['config']['estado'] not in ['espera','fim']: return
    if 'nome_time_esq' in dados: jogo['config']['nome_time_esq']=str(dados['nome_time_esq'])[:10].upper() or 'CASA'
    if 'nome_time_dir' in dados: jogo['config']['nome_time_dir']=str(dados['nome_time_dir'])[:10].upper() or 'FORA'
    if 'tempo_cfg' in dados:
        try: t=int(dados['tempo_cfg']); 
        except: t=180
        if t in [60,120,180,300,600]:
            jogo['config']['tempo_cfg']=t
            jogo['tempo_restante']=t
    if 'estadio' in dados and dados['estadio'] in ['grama','areia','neve','rua','quadra']:
        jogo['config']['estadio']=dados['estadio']
    if 'clima' in dados and dados['clima'] in ['sol','chuva','neblina','noite']:
        jogo['config']['clima']=dados['clima']
    if 'cor_time_esq' in dados:
        jogo['config']['cor_time_esq']=dados['cor_time_esq']
    if 'cor_time_dir' in dados:
        jogo['config']['cor_time_dir']=dados['cor_time_dir']
    if 'goleiro_bot' in dados:
        jogo['config']['goleiro_bot']=bool(dados['goleiro_bot'])
    if 'modo' in dados and dados['modo'] in ['1v1','3v3']:
        jogo['config']['modo']=dados['modo']
        jogo['config']['max_jogadores']=2 if dados['modo']=='1v1' else 6
    await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=nome)
    await enviar_lista_salas()

@sio.event
async def criar_torneio(sid, dados):
    if sid not in jogadores_sala: return
    nome=jogadores_sala[sid]; jogo=salas.get(nome)
    if not jogo or jogo['config']['owner']!=sid: return
    times=dados.get('times',[])
    # filtra vazios e limita 4 ou 8
    times=[t[:10].upper() for t in times if t.strip()][:8]
    if len(times) < 4:
        await sio.emit('erro_entrada', {'msg':'Precisa 4 ou 8 times!'}, to=sid); return
    # ajusta para potência de 2
    if len(times) not in [4,8]:
        # completa até 4 ou 8
        if len(times) <=4:
            times=times[:4]
        else:
            times=times[:8]
    random.shuffle(times)
    chaves=[]
    primeira=[]
    for i in range(0,len(times),2):
        primeira.append({'timeA': times[i], 'timeB': times[i+1], 'vencedor': None, 'placar': ''})
    chaves.append(primeira)
    torneio={
        'times': times,
        'chaves': chaves,
        'rodada_atual': 0,
        'partida_atual_idx': 0,
        'estado': 'andamento',
        'campeao': None
    }
    jogo['config']['torneio']=torneio
    jogo['config']['torneio_ativo']=True
    jogo['config']['nome_time_esq']=primeira[0]['timeA']
    jogo['config']['nome_time_dir']=primeira[0]['timeB']
    await sio.emit('torneio_atualizado', {'torneio': torneio, 'proxima': primeira[0]}, room=nome)
    await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=nome)

@sio.event
async def trocar_equipa(sid, dados=None):
    if sid not in jogadores_sala: return
    jogo=salas.get(jogadores_sala[sid])
    if not jogo or sid not in jogo['jogadores'] or jogo['config']['estado']!='espera': return
    j=jogo['jogadores'][sid]; j['equipa']='direita' if j['equipa']=='esquerda' else 'esquerda'
    await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=jogadores_sala[sid])

@sio.event
async def trocar_posicao(sid, dados=None):
    if sid not in jogadores_sala: return
    jogo=salas.get(jogadores_sala[sid])
    if not jogo or sid not in jogo['jogadores'] or jogo['config']['estado']!='espera': return
    j=jogo['jogadores'][sid]
    j['posicao']='goleiro' if j.get('posicao')=='linha' else 'linha'
    j['raio']=22 if j['posicao']=='goleiro' else 20
    await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=jogadores_sala[sid])

@sio.event
async def sair_sala(sid, dados=None):
    if sid in jogadores_sala:
        nome=jogadores_sala[sid]; jogo=salas.get(nome)
        if jogo and sid in jogo['jogadores']:
            del jogo['jogadores'][sid]
            if 'mutados' in jogo and sid in jogo['mutados']:
                jogo['mutados'].discard(sid)
            if jogo['config']['owner']==sid and jogo['jogadores']:
                novo=list(jogo['jogadores'].keys())[0]; jogo['config']['owner']=novo; await sio.emit('voce_e_dono', {'dono':True}, to=novo)
            if not jogo['jogadores'] and not jogo['espectadores']: del salas[nome]
            else: await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=nome)
        await sio.leave_room(sid,nome); del jogadores_sala[sid]; await enviar_lista_salas()
    elif sid in espectadores_sala:
        nome=espectadores_sala[sid]; jogo=salas.get(nome)
        if jogo and sid in jogo['espectadores']: del jogo['espectadores'][sid]
        if jogo and 'mutados' in jogo and sid in jogo['mutados']:
            jogo['mutados'].discard(sid)
        await sio.leave_room(sid,nome); del espectadores_sala[sid]

@sio.event
async def logout(sid, dados=None):
    if sid in logados:
        print(f"[LOGOUT] {logados[sid]}")
        del logados[sid]
    await sair_sala(sid)
    await sio.emit('logout_ok', {}, to=sid)

@sio.event
async def disconnect(sid):
    if sid in logados:
        print(f"[DISCONNECT] {logados[sid]} - mantém conta mas remove da sala")
        del logados[sid]
    await sair_sala(sid)

@sio.event
async def mover(sid,dados):
    if sid in jogadores_sala:
        jogo=salas.get(jogadores_sala[sid])
        if not jogo or sid not in jogo['jogadores']: return
        if jogo['estado_partida'] not in ['jogando']: return
        j=jogo['jogadores'][sid]
        if dados.get('dx')==0 and dados.get('dy')==0: j['input_x']=j['input_y']=j['vx']=j['vy']=0
        else: j['input_x']=float(dados.get('dx',0)); j['input_y']=float(dados.get('dy',0))

@sio.event
async def correr(sid,dados):
    if sid in jogadores_sala:
        j=salas.get(jogadores_sala[sid])
        if j and sid in j['jogadores']: j['jogadores'][sid]['boost']=bool(dados.get('ativo',False))

@sio.event
async def chutar(sid, dados=None):
    if sid not in jogadores_sala: return
    n=jogadores_sala[sid]; j=salas.get(n)
    if not j or sid not in j['jogadores']: return
    if j['estado_partida'] not in ['jogando']: return
    jog=j['jogadores'][sid]; b=j['bola']
    if math.hypot(b['x']-jog['x'], b['y']-jog['y'])>70: return
    forca=float(dados.get('forca',0.7)) if dados else 0.7
    forca=max(0.15,min(1.0,forca))
    potencia=8+forca*12
    if forca>0.92: b['fogo']=45
    ang=math.atan2(b['y']-jog['y'], b['x']-jog['x'])
    ang+=random.uniform(-0.25,0.25)*(1-forca)
    b['vx']=math.cos(ang)*potencia; b['vy']=math.sin(ang)*potencia
    if 'estatisticas' not in j:
        j['estatisticas']=init_stats()
    equipa=jog['equipa']
    j['estatisticas']['chutes'][equipa]+=1
    j['estatisticas']['chutes_jogadores'][jog['nome']]=j['estatisticas']['chutes_jogadores'].get(jog['nome'],0)+1
    if (equipa=='esquerda' and jog['x']>420) or (equipa=='direita' and jog['x']<380):
        if G_SUP-40 <= b['y'] <= G_INF+40:
            j['estatisticas']['chutes_no_gol'][equipa]+=1
    j['ultimo_toque']={'equipa':equipa,'sid':sid,'nome':jog['nome']}
    await sio.emit('evento_som','chute', room=n)
    if forca>0.9: await sio.emit('evento_som','chute_forte', room=n)

@sio.event
async def chat_mensagem(sid,dados):
    sala=jogadores_sala.get(sid) or espectadores_sala.get(sid)
    if not sala: return
    j=salas.get(sala)
    if not j: return
    # anti-troll mute check
    if 'mutados' in j and sid in j['mutados']:
        await sio.emit('nova_mensagem',{'nome':'SISTEMA','mensagem':'🔇 Você está mutado pelo dono!','cor':'#ff3b30'}, to=sid)
        return
    nome='?'
    cor='#fff'
    if sid in j['jogadores']: nome=j['jogadores'][sid]['nome']; cor=j['jogadores'][sid]['cor1']
    elif sid in j['espectadores']: nome=j['espectadores'][sid]['nome']+' (ESP)'; cor='#aaa'
    msg=str(dados.get('mensagem',''))[:42]
    if msg: await sio.emit('nova_mensagem',{'nome':nome,'mensagem':msg,'cor':cor}, room=sala)

@sio.event
async def get_perfil(sid,dados):
    try:
        nome=str(dados.get('nome','')).upper()[:12]
        if not nome:
            return
        perfil={
            'nome': nome,
            'gols': ranking_global.get('artilheiros',{}).get(nome,0),
            'assist': ranking_global.get('assistentes',{}).get(nome,0),
            'jogos': ranking_global.get('jogos',{}).get(nome,0),
            'vitorias': ranking_global.get('vitorias',{}).get(nome,0),
            'derrotas': ranking_global.get('derrotas',{}).get(nome,0),
            'empates': ranking_global.get('empates',{}).get(nome,0),
            'mvp': ranking_global.get('mvp',{}).get(nome,0),
        }
        # calcula aproveitamento
        total = perfil['vitorias']+perfil['derrotas']+perfil['empates']
        if total>0:
            perfil['aproveitamento']=round(perfil['vitorias']/total*100)
        else:
            perfil['aproveitamento']=0
        await sio.emit('perfil_dados', perfil, to=sid)
    except Exception as e:
        print("Erro get_perfil", e)

@sio.event
async def kickar_jogador(sid,dados):
    try:
        if sid not in jogadores_sala: return
        sala=jogadores_sala[sid]
        jogo=salas.get(sala)
        if not jogo or jogo['config']['owner']!=sid: 
            await sio.emit('erro_entrada', {'msg':'Só o dono pode kickar!'}, to=sid)
            return
        target_sid=dados.get('sid') or dados.get('target')
        if not target_sid: return
        if target_sid not in jogo['jogadores']: return
        if target_sid==sid: return
        nome_kick=jogo['jogadores'][target_sid]['nome']
        # remove da sala
        del jogo['jogadores'][target_sid]
        await sio.leave_room(target_sid, sala)
        if target_sid in jogadores_sala:
            del jogadores_sala[target_sid]
        await sio.emit('forcar_volta_lobby', {'motivo': f'Kickado pelo dono {jogo["jogadores"][sid]["nome"]}'}, to=target_sid)
        await sio.emit('nova_mensagem', {'nome':'SISTEMA','mensagem': f'👢 {nome_kick} foi kickado pelo dono!','cor':'#ff3b30'}, room=sala)
        await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=sala)
        await enviar_lista_salas()
    except Exception as e:
        print("Erro kick", e)

@sio.event
async def mutar_jogador(sid,dados):
    try:
        if sid not in jogadores_sala: return
        sala=jogadores_sala[sid]
        jogo=salas.get(sala)
        if not jogo or jogo['config']['owner']!=sid:
            return
        target_sid=dados.get('sid') or dados.get('target')
        if not target_sid: return
        if 'mutados' not in jogo:
            jogo['mutados']=set()
        if target_sid in jogo['mutados']:
            jogo['mutados'].remove(target_sid)
            await sio.emit('nova_mensagem', {'nome':'SISTEMA','mensagem': f'🔊 {jogo["jogadores"].get(target_sid,{}).get("nome","Jogador")} foi desmutado!','cor':'#00ffcc'}, room=sala)
            await sio.emit('mutado_status', {'sid':target_sid,'mutado':False}, room=sala)
        else:
            jogo['mutados'].add(target_sid)
            await sio.emit('nova_mensagem', {'nome':'SISTEMA','mensagem': f'🔇 {jogo["jogadores"].get(target_sid,{}).get("nome","Jogador")} foi mutado pelo dono!','cor':'#ffea00'}, room=sala)
            await sio.emit('mutado_status', {'sid':target_sid,'mutado':True}, room=sala)
    except Exception as e:
        print("Erro mutar", e)


@sio.event
async def voltar_sala_espera(sid):
    sala = jogadores_sala.get(sid) or espectadores_sala.get(sid)
    if not sala or sala not in salas:
        # permite voltar mesmo se sid não está mais mapeado (caso tenha disconnect)
        # tenta achar pela sala da mensagem anterior - já coberto
        return
    jogo = salas[sala]
    # se torneio ativo, não reseta, vai pra próxima partida
    if jogo['config'].get('torneio_ativo') and jogo['config'].get('torneio') and jogo['config']['torneio']['estado']!='finalizado':
        await sio.emit('forcar_volta_lobby', room=sala)
        await sio.emit('estado_jogo', sanitize_jogo_for_emit(jogo), room=sala)
        await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=sala)
        return
    jogo['estado_partida'] = 'espera'
    if 'config' in jogo:
        jogo['config']['estado'] = 'espera'
        jogo['config']['torneio_ativo']=False
        jogo['config']['torneio']=None
    jogo['placar'] = {'esquerda': 0, 'direita': 0}
    jogo['tempo_restante'] = jogo.get('config', {}).get('tempo_cfg', 180)
    jogo['estatisticas']=init_stats()
    jogo['ultimo_toque']=None
    reiniciar_posicoes(jogo)
    await sio.emit('forcar_volta_lobby', room=sala)
    await sio.emit('estado_jogo', sanitize_jogo_for_emit(jogo), room=sala)
    await sio.emit('estado_espera', {'config':jogo['config'],'jogadores':jogo['jogadores'],'espectadores':jogo['espectadores']}, room=sala)
    await enviar_lista_salas()

@sio.event
async def mandar_emote(sid, dados):
    if sid in jogadores_sala:
        jogo = salas.get(jogadores_sala[sid])
        if jogo and sid in jogo['jogadores']:
            # Pega o emote e define um temporizador de ~2 segundos (120 frames a 60fps)
            jogo['jogadores'][sid]['emote'] = str(dados.get('emote', ''))[:2]
            jogo['jogadores'][sid]['emote_timer'] = 120

async def start(app):
    print("🚀 Iniciando a ligação ao MongoDB...")
    await init_mongodb() # <-- Espera o Banco de Dados carregar primeiro!
    app['f']=asyncio.create_task(loop_fisica())
    app['t']=asyncio.create_task(loop_tempo())
app.on_startup.append(start)
if __name__=='__main__':
    p=int(os.environ.get("PORT",8080)); print(f"V4.0 MVP+RANKING+TORNEIO+CLIMA http://localhost:{p}"); web.run_app(app,port=p,host='0.0.0.0')
