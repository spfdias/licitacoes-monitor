import json


def render_painel(items: list[dict]) -> str:
    data_json = json.dumps(items, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Painel de Licitações de TI - Central Informática</title>
<style>
  :root {{
    --bg: #0f172a; --card: #1e293b; --border: #334155; --text: #e2e8f0;
    --muted: #94a3b8; --accent: #38bdf8; --accent2: #22c55e; --warn: #f59e0b; --danger: #ef4444;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; background: var(--bg); color: var(--text); }}
  header {{ padding: 24px 32px 12px; border-bottom: 1px solid var(--border); display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap; }}
  header h1 {{ margin: 0 0 4px; font-size: 22px; }}
  header p {{ margin: 0; color: var(--muted); font-size: 13px; }}
  header a {{ color: var(--accent); font-size: 13px; text-decoration:none; white-space:nowrap; }}
  .cards {{ display:flex; gap:16px; padding: 20px 32px; flex-wrap: wrap; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; min-width: 160px; }}
  .card .num {{ font-size: 26px; font-weight: 700; color: var(--accent); }}
  .card .lbl {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
  .controls {{ display:flex; gap:12px; padding: 0 32px 16px; flex-wrap: wrap; align-items:center; }}
  .controls input, .controls select {{ background: var(--card); border: 1px solid var(--border); color: var(--text); padding: 8px 12px; border-radius: 8px; font-size: 13px; }}
  .controls input {{ flex: 1; min-width: 220px; }}
  .quickbtn {{ background: #0369a1; border:1px solid var(--accent); color: #fff; padding: 8px 14px; border-radius: 8px; font-size: 13px; cursor: pointer; }}
  .quickbtn:hover {{ background: var(--accent); }}
  table {{ width: calc(100% - 64px); margin: 0 32px 40px; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; padding: 10px 12px; border-bottom: 2px solid var(--border); color: var(--muted); font-weight: 600; position: sticky; top:0; background: var(--bg); }}
  td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  tr:hover td {{ background: rgba(56,189,248,0.05); }}
  tr.urgente-1 td {{ background: rgba(239,68,68,0.12); }}
  tr.urgente-5 td {{ background: rgba(245,158,11,0.10); }}
  .uf {{ display:inline-block; background: var(--card); border:1px solid var(--border); border-radius:6px; padding:2px 8px; font-size:11px; color: var(--accent); }}
  .uf.ro {{ border-color: var(--accent2); color: var(--accent2); font-weight:700; }}
  tr.ro td {{ background: rgba(34,197,94,0.08); }}
  .val {{ color: var(--accent2); font-weight:600; white-space: nowrap; }}
  .obj {{ max-width: 480px; }}
  .prazo-1 {{ color: var(--danger); font-weight:700; }}
  .prazo-5 {{ color: var(--warn); font-weight:600; }}
  a.lk {{ color: var(--accent); text-decoration: none; font-size:12px; }}
  a.lk:hover {{ text-decoration: underline; }}
  .empty {{ padding: 12px; color: var(--muted); }}
  footer {{ padding: 16px 32px 40px; color: var(--muted); font-size: 12px; border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<header>
  <div>
    <h1>Painel de Licitações de TI</h1>
    <p>Rastreado automaticamente pelo agente Juliana a partir da API pública do PNCP — TI, telefonia IP/PABX/SIP trunk, STFC e Firewall de Próxima Geração (NGFW).</p>
  </div>
  <a href="/dashboard">&laquo; configurações</a>
</header>

<div class="cards">
  <div class="card"><div class="num" id="cTotal">0</div><div class="lbl">licitações rastreadas</div></div>
  <div class="card"><div class="num" id="cValor">R$ 0</div><div class="lbl">valor estimado somado</div></div>
  <div class="card"><div class="num" id="cUF">0</div><div class="lbl">estados com oportunidades</div></div>
  <div class="card"><div class="num" id="cUrgente">0</div><div class="lbl">encerram em até 5 dias</div></div>
  <div class="card"><div class="num" id="cRO">0</div><div class="lbl">licitações em Rondônia (RO)</div></div>
</div>

<div class="controls">
  <input id="busca" type="text" placeholder="Buscar por órgão, objeto ou município...">
  <select id="filtroUF"><option value="">Todos os estados</option></select>
  <select id="ordenar">
    <option value="prazo_asc">Prazo mais próximo</option>
    <option value="valor_desc">Maior valor estimado</option>
    <option value="uf">Estado (A-Z)</option>
  </select>
  <button class="quickbtn" id="btnUrgente">Ver só as urgentes (&le;5 dias)</button>
  <button class="quickbtn" id="btnRO">Ver só Rondônia (RO)</button>
</div>

<table>
  <thead>
    <tr>
      <th>UF</th><th>Órgão</th><th>Objeto</th><th>Valor estimado</th><th>Encerramento</th><th>Situação</th><th>Edital</th>
    </tr>
  </thead>
  <tbody id="corpo"></tbody>
</table>

<footer>
  Fonte: API pública do PNCP (Portal Nacional de Contratações Públicas), modalidade Pregão Eletrônico, filtrada localmente pelas palavras-chave do escopo. Atualizado automaticamente todo dia pelo agente Juliana.
</footer>

<script>
const DATA = {data_json};

function fmtMoeda(v) {{
  if (!v) return '-';
  return v.toLocaleString('pt-BR', {{style:'currency', currency:'BRL', maximumFractionDigits:0}});
}}
function fmtData(s) {{
  if (!s) return '-';
  const d = new Date(s);
  return d.toLocaleDateString('pt-BR');
}}
function diasRestantes(s) {{
  if (!s) return null;
  const hoje = new Date(); hoje.setHours(0,0,0,0);
  const alvo = new Date(s); alvo.setHours(0,0,0,0);
  return Math.round((alvo - hoje) / 86400000);
}}

const ufs = [...new Set(DATA.map(r => r.uf).filter(Boolean))].sort();
const selUF = document.getElementById('filtroUF');
ufs.forEach(uf => {{
  const o = document.createElement('option');
  o.value = uf; o.textContent = uf;
  selUF.appendChild(o);
}});

document.getElementById('cTotal').textContent = DATA.length;
document.getElementById('cValor').textContent = fmtMoeda(DATA.reduce((s,r)=>s+(r.valor_estimado||0),0));
document.getElementById('cUF').textContent = ufs.length;
document.getElementById('cUrgente').textContent = DATA.filter(r => {{ const d = diasRestantes(r.encerramento_proposta); return d !== null && d >= 0 && d <= 5; }}).length;
document.getElementById('cRO').textContent = DATA.filter(r => r.uf === 'RO').length;

let soUrgente = false;
let soRO = false;
document.getElementById('btnUrgente').addEventListener('click', () => {{
  soUrgente = !soUrgente;
  render();
}});
document.getElementById('btnRO').addEventListener('click', () => {{
  soRO = !soRO;
  render();
}});

function render() {{
  const q = document.getElementById('busca').value.toLowerCase();
  const uf = selUF.value;
  const ord = document.getElementById('ordenar').value;
  let rows = DATA.filter(r => {{
    if (uf && r.uf !== uf) return false;
    if (soRO && r.uf !== 'RO') return false;
    if (soUrgente) {{
      const d = diasRestantes(r.encerramento_proposta);
      if (d === null || d < 0 || d > 5) return false;
    }}
    if (q) {{
      const t = ((r.orgao||'') + ' ' + (r.objeto||'') + ' ' + (r.municipio||'')).toLowerCase();
      if (!t.includes(q)) return false;
    }}
    return true;
  }});
  if (ord === 'valor_desc') rows.sort((a,b) => (b.valor_estimado||0) - (a.valor_estimado||0));
  if (ord === 'prazo_asc') rows.sort((a,b) => new Date(a.encerramento_proposta||'2999') - new Date(b.encerramento_proposta||'2999'));
  if (ord === 'uf') rows.sort((a,b) => (a.uf||'').localeCompare(b.uf||''));

  const tbody = document.getElementById('corpo');
  tbody.innerHTML = '';
  if (rows.length === 0) {{
    tbody.innerHTML = '<tr><td colspan="7" class="empty">Nenhum resultado.</td></tr>';
    return;
  }}
  for (const r of rows) {{
    const dias = diasRestantes(r.encerramento_proposta);
    const tr = document.createElement('tr');
    let prazoClass = '';
    if (r.uf === 'RO') tr.className = 'ro';
    if (dias !== null && dias >= 0) {{
      if (dias <= 1) {{ tr.className = 'urgente-1'; prazoClass = 'prazo-1'; }}
      else if (dias <= 5) {{ tr.className = 'urgente-5'; prazoClass = 'prazo-5'; }}
    }}
    tr.innerHTML = `
      <td><span class="uf ${{r.uf === 'RO' ? 'ro' : ''}}">${{r.uf||'-'}}</span></td>
      <td>${{r.orgao||'-'}}<br><span style="color:var(--muted);font-size:11px">${{r.municipio||''}}</span></td>
      <td class="obj">${{r.objeto||'-'}}</td>
      <td class="val">${{fmtMoeda(r.valor_estimado)}}</td>
      <td class="${{prazoClass}}">${{fmtData(r.encerramento_proposta)}}${{dias !== null && dias >= 0 ? ` (${{dias}}d)` : ''}}</td>
      <td>${{r.situacao||'-'}}</td>
      <td>${{r.link ? `<a class="lk" href="${{r.link}}" target="_blank">Abrir</a>` : '-'}}</td>
    `;
    tbody.appendChild(tr);
  }}
}}

document.getElementById('busca').addEventListener('input', render);
selUF.addEventListener('change', render);
document.getElementById('ordenar').addEventListener('change', render);
render();
</script>
</body>
</html>"""
