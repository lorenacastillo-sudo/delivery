import requests
import json
import os
import base64
from datetime import datetime
from collections import defaultdict

JIRA_BASE = os.environ['JIRA_BASE_URL']
JIRA_EMAIL = os.environ['JIRA_EMAIL']
JIRA_TOKEN = os.environ['JIRA_TOKEN']
AUTH = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_TOKEN}".encode()).decode()
HEADERS = {"Authorization": f"Basic {AUTH}", "Content-Type": "application/json"}

TEAM_MAP = {
    'Alexander Contreras': 'Shared Services',
    'Deisy Muñoz': 'Shared Services',
    'Gabriel Andrés Rondón Barragán': 'Shared Services',
    'Omar Davila': 'Infraestructura',
    'David Tabla': 'Infraestructura',
    'Valentina Aguirre': 'Infraestructura',
    'Juan Pablo Velandia': 'Traction',
    'Edison Rojas': 'Traction',
    'Oscar Mendez': 'Traction',
    'Maria Paulina Ramirez Vasquez': 'Traction',
    'Joaquín Forero': 'Traction',
    'Fabian Roa': 'QA',
    'Lorena Pacavita': 'QA',
    'Vivian Rodriguez': 'Tech Product',
    'Karen Garzón': 'Tech Product',
    'Arnold Blandon': 'Client Management/Finance & Accounting',
    'Anderson Caceres': 'Client Management/Finance & Accounting',
    'Miguel Jaramillo': 'Client Management/Finance & Accounting',
    'Luis Meza': 'Onboarding',
    'Heiner Granados': 'Onboarding',
    'Lorena Castillo': 'Delivery',
    'Daniela Jaramillo': 'Delivery',
    'Andrés Bueno': 'Legacy/Integrations',
    'Daniela Guzman': 'Legacy/Integrations',
    'Jose Acevedo': 'Legacy/Integrations',
    'Javier Gutierrez': 'Legacy/Integrations',
}

EXCLUDE = {'Valentina Juya', 'Area Financiera', 'Sin asignar'}
INFRA_MEMBERS = {'Omar Davila', 'David Tabla', 'Valentina Aguirre'}

SER_OPEN = {'En curso', 'Escalated', 'Pending', 'Waiting for customer', 'Waiting for support', 'Waiting for approval'}
SER_MAP = {s: s for s in SER_OPEN}

ACTIVE = {'[IN PROGRESS]', 'En curso', 'Pending'}
BLOCKED = {'[BLOCKED]', 'Escalated'}
DONE = {'[FINISHED]', 'Resolved', '[CANCELED]', '[SOLVED]'}

FIELDS = ["summary","assignee","status","issuetype","project","timeoriginalestimate",
          "timespent","timeestimate","priority","customfield_10001","statuscategorychangedate","customfield_10937"]

def fetch_all(jql):
    all_issues = []
    url = f"{JIRA_BASE}/rest/api/3/search/jql"
    params = {"jql": jql, "fields": ",".join(FIELDS), "maxResults": 100}
    while True:
        r = requests.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)
        next_token = data.get("nextPageToken")
        if not next_token or not issues:
            break
        params = {"jql": jql, "fields": ",".join(FIELDS), "maxResults": 100, "nextPageToken": next_token}
    return all_issues

def days_in_status(f):
    sc = f.get('statuscategorychangedate', '')[:10]
    if not sc:
        return 0
    try:
        return (datetime.now() - datetime.strptime(sc, '%Y-%m-%d')).days
    except:
        return 0

print("Fetching REQ (openSprints)...")
req_open = fetch_all('sprint in openSprints() AND issuetype in ("Task","Bug","Subtask","Test Set")')
print(f"REQ openSprints: {len(req_open)}")

print("Fetching REQ (sprint 2016)...")
req_2016 = fetch_all('sprint = 2016 AND issuetype in ("Task","Bug","Subtask","Test Set")')
print(f"REQ sprint 2016: {len(req_2016)}")

seen = set()
req_issues = []
for i in req_open + req_2016:
    if i['key'] not in seen:
        seen.add(i['key'])
        req_issues.append(i)
print(f"REQ total: {len(req_issues)}")

print("Fetching SER...")
ser_issues = fetch_all('project = SER AND status in ("En curso","Escalated","Pending","Waiting for customer","Waiting for support","Waiting for approval")')
print(f"SER: {len(ser_issues)}")

print("Fetching DEV...")
dev_issues = fetch_all('project = DEV AND status in ("En curso","Escalated","Pending","Waiting for customer","Waiting for support","Waiting for approval")')
print(f"DEV: {len(dev_issues)}")

people = defaultdict(lambda: {'team': 'Sin equipo', 'issues': []})

def add_issue(i, board, status_override=None):
    f = i['fields']
    name = f['assignee']['displayName'] if f.get('assignee') else 'Sin asignar'
    if name in EXCLUDE:
        return
    if board == 'DEV' and name not in INFRA_MEMBERS:
        return
    status = status_override or f['status']['name']
    if board in ('SER', 'DEV') and status not in SER_OPEN:
        return
    team = TEAM_MAP.get(name, (f.get('customfield_10001') or {}).get('name', 'Sin equipo'))
    p = people[name]
    if p['team'] == 'Sin equipo' and team != 'Sin equipo':
        p['team'] = team
    inversion = (f.get('customfield_10937') or {}).get('value', '')
    p['issues'].append({
        'key': i['key'],
        'summary': (f.get('summary') or '')[:70],
        'status': status,
        'type': f['issuetype']['name'],
        'proj': f['project']['key'],
        'est': f.get('timeoriginalestimate') or 0,
        'log': f.get('timespent') or 0,
        'rem': f.get('timeestimate') or 0,
        'prio': (f.get('priority') or {}).get('name', 'Medium'),
        'board': board,
        'days_in_status': days_in_status(f),
        'inversion': inversion,
    })

for i in req_issues:
    add_issue(i, 'REQ')

for i in ser_issues:
    add_issue(i, 'SER')

for i in dev_issues:
    add_issue(i, 'DEV')

output = []
for name, data in sorted(people.items()):
    issues = data['issues']
    req_only = [i for i in issues if i['board'] == 'REQ']
    capex_h = round(sum(i['est'] for i in req_only if i['inversion'] == 'CAPEX') / 3600, 1)
    opex_h = round(sum(i['est'] for i in req_only if i['inversion'] == 'OPEX') / 3600, 1)
    total_inv = capex_h + opex_h
    output.append({
        'name': name,
        'team': data['team'],
        'issues': issues,
        'stats': {
            'total': len(issues),
            'est_h': round(sum(i['est'] for i in issues) / 3600, 1),
            'log_h': round(sum(i['log'] for i in issues) / 3600, 1),
            'inprog': sum(1 for i in issues if i['status'] in ACTIVE),
            'blocked': sum(1 for i in issues if i['status'] in BLOCKED),
            'todo': sum(1 for i in issues if i['status'] not in ACTIVE | BLOCKED | DONE | {'[RETURNED]'}),
            'done': sum(1 for i in issues if i['status'] in DONE),
            'ret': sum(1 for i in issues if i['status'] == '[RETURNED]'),
            'ser': sum(1 for i in issues if i['board'] == 'SER'),
            'req': sum(1 for i in issues if i['board'] == 'REQ'),
            'dev': sum(1 for i in issues if i['board'] == 'DEV'),
            'capex_h': capex_h,
            'opex_h': opex_h,
            'capex_pct': round(capex_h / total_inv * 100) if total_inv > 0 else 0,
            'opex_pct': round(opex_h / total_inv * 100) if total_inv > 0 else 0,
        }
    })

updated = datetime.now().strftime("%d/%m/%Y %H:%M")
data_json = json.dumps(output, ensure_ascii=False)

html = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sprint Dashboard · Lineru</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f3;color:#1a1a1a;padding:1.25rem;}
.hdr{display:flex;align-items:center;gap:10px;background:#fff;padding:.85rem 1.1rem;border-radius:12px;margin-bottom:1rem;}
.hdr-title{font-size:15px;font-weight:600;}.hdr-sub{font-size:11px;color:#666;margin-top:1px;}
.pulse{width:8px;height:8px;border-radius:50%;background:#1d9e75;animation:blink 2s infinite;flex-shrink:0;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.upd{margin-left:auto;font-size:10px;color:#aaa;}
.pills{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:1rem;}
.pill{padding:3px 11px;border-radius:16px;font-size:11px;font-weight:500;cursor:pointer;border:1px solid #ddd;background:#fff;color:#555;}
.pill.on{background:#1a1a1a;color:#fff;border-color:#1a1a1a;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px;margin-bottom:1rem;}
.pc{background:#fff;border-radius:10px;padding:12px;cursor:pointer;border:1.5px solid transparent;}
.pc:hover{border-color:#ddd;}.pc.sel{border-color:#378add;box-shadow:0 0 0 3px rgba(55,138,221,.1);}
.av{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;}
.pname{font-size:12px;font-weight:600;}.pteam{font-size:10px;color:#888;}
.bar-wrap{height:5px;background:#f0f0ec;border-radius:3px;overflow:hidden;display:flex;margin:5px 0 2px;}
.bar-log{height:100%;}.bar-rem{height:100%;opacity:.7;}
.bar-labels{display:flex;justify-content:space-between;font-size:8.5px;color:#aaa;margin-bottom:4px;}
.inv-bar{height:3px;display:flex;border-radius:2px;overflow:hidden;margin-bottom:2px;}
.inv-labels{font-size:8.5px;color:#aaa;margin-bottom:4px;}
.divider{height:1px;background:#f0f0ec;margin:6px 0;}
.br{display:flex;align-items:flex-start;gap:5px;margin-bottom:3px;}
.bl{font-size:9px;font-weight:700;padding:2px 5px;border-radius:3px;white-space:nowrap;margin-top:1px;}
.lreq{background:#eaf3de;color:#27500a;}.lser{background:#eeedfe;color:#3c3489;}.ldev{background:#faeeda;color:#633806;}
.chips{display:flex;gap:3px;flex-wrap:wrap;}
.ch{font-size:9px;padding:1px 5px;border-radius:5px;font-weight:500;white-space:nowrap;}
.cp{background:#eaf3de;color:#27500a;}.cb{background:#fcebeb;color:#791f1f;}
.ct{background:#e6f1fb;color:#0c447c;}.cf{background:#e1f5ee;color:#085041;}
.cr{background:#faece7;color:#712b13;}.cs{background:#eeedfe;color:#3c3489;}
.cenc{background:#eaf3de;color:#27500a;}.cesc{background:#fcebeb;color:#791f1f;}
.cwf{background:#eeedfe;color:#3c3489;}.cpen{background:#faeeda;color:#633806;}
/* detail */
.det{background:#fff;border-radius:12px;padding:1.25rem;margin-top:.75rem;}
.dh{display:flex;align-items:center;gap:12px;margin-bottom:1rem;}
.dav{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:600;}
.dn{font-size:15px;font-weight:600;}.dm{font-size:11px;color:#666;margin-top:2px;}
.mrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(95px,1fr));gap:8px;margin-bottom:1rem;}
.m{background:#f7f7f5;border-radius:8px;padding:9px 11px;}
.ml{font-size:10px;color:#666;}.mv{font-size:18px;font-weight:600;margin-top:2px;}.ms{font-size:9px;color:#aaa;margin-top:1px;}
.sec{margin-top:.85rem;}
.slbl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#888;display:flex;align-items:center;gap:5px;margin-bottom:5px;}
.sdot{width:6px;height:6px;border-radius:50%;display:inline-block;}
.dp{background:#1d9e75;}.db{background:#e24b4a;}.dt{background:#378add;}.df{background:#9dd4be;}.dret{background:#ba7517;}.dc{background:#ccc;}
.irow{display:grid;grid-template-columns:90px 1fr auto;gap:6px;align-items:start;padding:6px 0;border-bottom:1px solid #f5f5f3;}
.irow:last-child{border-bottom:none;}
.ikey{font-size:9.5px;font-weight:500;color:#666;font-family:monospace;}
.ikey a{color:#1a1a1a;text-decoration:none;}.ikey a:hover{color:#378add;text-decoration:underline;}
.iproj{font-size:8.5px;padding:1px 4px;border-radius:3px;margin-top:2px;display:inline-block;}
.preq{background:#eaf3de;color:#27500a;}.pser{background:#eeedfe;color:#3c3489;}.pdev{background:#faeeda;color:#633806;}
.ititle{font-size:11px;line-height:1.4;}
.dblock{font-size:9.5px;padding:1px 5px;border-radius:4px;background:#fcebeb;font-weight:600;margin-left:4px;}
.tc{text-align:right;white-space:nowrap;}
.tn{font-size:9.5px;color:#888;font-family:monospace;}
</style>
</head>
<body>
<div class="hdr">
  <div class="pulse"></div>
  <div><div class="hdr-title">Sprint Dashboard &middot; Lineru</div>
  <div class="hdr-sub">Sprint activo &middot; REQ + SER + DEV</div></div>
  <div class="upd">&#x1F504; """ + updated + """</div>
</div>
<div class="pills" id="pills"></div>
<div class="grid" id="grid"></div>
<div id="det"></div>
<script>
var ALL = [];
</script>
<script type="application/json" id="_jdata">
""" + data_json + """
</script>
<script>
try { ALL = JSON.parse(document.getElementById('_jdata').textContent); } catch(e) { console.error('Data parse error:', e); }
var TEAMS = ["Todos","Onboarding","Traction","Legacy/Integrations","QA","Tech Product","Shared Services","Infraestructura","Client Management/Finance & Accounting","Delivery","Sin equipo"];
var curTeam = "Todos";
var AC = ["#e6f1fb","#eaf3de","#faeeda","#eeedfe","#faece7","#fbeaf0"];
var AT = ["#0c447c","#27500a","#633806","#3c3489","#712b13","#72243e"];

function ini(n){return n.split(" ").slice(0,2).map(function(w){return w[0];}).join("").toUpperCase();}
function avc(n){var i=n.charCodeAt(0)%6;return "background:"+AC[i]+";color:"+AT[i]+";";}

function sl(st){
  var m={"[IN PROGRESS]":"In Progress","[BLOCKED]":"Blocked","[RETURNED]":"Returned","[TO DO]":"To Do",
         "[FINISHED]":"Finished","[CANCELED]":"Canceled","[SOLVED]":"Solved","[READY FOR TESTING]":"Rdy Test",
         "[IN TESTING]":"In Testing","En curso":"En curso","Escalated":"Escalated","Pending":"Pending",
         "Waiting for customer":"Wtg Customer","Waiting for support":"Wtg Support","Waiting for approval":"Wtg Approval",
         "Resolved":"Resolved"};
  return m[st]||st;
}

function sch(st,board){
  if(board==="SER"||board==="DEV"){
    if(st==="En curso")return "ch cenc";
    if(st==="Escalated")return "ch cesc";
    if(st==="Pending")return "ch cpen";
    if(st.indexOf("Waiting")===0)return "ch cwf";
    return "ch cs";
  }
  if(st==="[IN PROGRESS]")return "ch cp";
  if(st==="[BLOCKED]")return "ch cb";
  if(st==="[RETURNED]")return "ch cr";
  if(st==="[TO DO]")return "ch ct";
  if(st==="[FINISHED]"||st==="[SOLVED]"||st==="[CANCELED]")return "ch cf";
  return "ch cs";
}

function ab(issues,board){
  var c={};
  issues.filter(function(i){return i.board===board;}).forEach(function(i){c[i.status]=(c[i.status]||0)+1;});
  return c;
}

function chipsHtml(counts,board){
  return Object.keys(counts).map(function(st){
    return "<span class='"+sch(st,board)+"'>"+counts[st]+" "+sl(st)+"</span>";
  }).join("");
}

function render(){
  var list = curTeam==="Todos" ? ALL : ALL.filter(function(p){return p.team===curTeam;});
  document.getElementById("pills").innerHTML = TEAMS.map(function(t){
    var label = t==="Client Management/Finance & Accounting" ? "Client Mgmt" : t;
    return "<div class='pill"+(t===curTeam?" on":"")+"' onclick='setTeam(\""+t.replace(/"/g,"&quot;")+"\")'>"+label+"</div>";
  }).join("");
  if(!list.length){
    document.getElementById("grid").innerHTML="<div style='grid-column:1/-1;text-align:center;padding:2rem;color:#aaa;'>Sin personas.</div>";
    return;
  }
  document.getElementById("grid").innerHTML = list.map(function(p,i){return cardHtml(p,i);}).join("");
}

function setTeam(t){curTeam=t;document.getElementById("det").innerHTML="";render();}

function cardHtml(p,idx){
  var s=p.stats;
  var req=ab(p.issues,"REQ"),ser=ab(p.issues,"SER"),dev=ab(p.issues,"DEV");
  var hR=Object.keys(req).length>0,hS=Object.keys(ser).length>0,hD=Object.keys(dev).length>0;
  var lh=s.log_h,rh=Math.max(0,s.est_h-lh);
  var lp=Math.min(lh/160*100,100).toFixed(1);
  var rp=Math.min(rh/160*100,100).toFixed(1);
  var over=lh>s.est_h&&s.est_h>0;
  var logC=over?"#e24b4a":"#1d9e75";
  var html="<div class='pc' id='pc"+idx+"' onclick='selCard("+idx+")'>";
  html+="<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px;'>";
  html+="<div class='av' style='"+avc(p.name)+"'>"+ini(p.name)+"</div>";
  html+="<div><div class='pname'>"+p.name+"</div><div class='pteam'>"+p.team+"</div></div></div>";
  html+="<div style='display:flex;justify-content:space-between;font-size:9.5px;color:#999;margin-bottom:3px;'>";
  html+="<span>"+s.total+" issues &middot; "+s.est_h.toFixed(1)+"h</span></div>";
  html+="<div class='bar-wrap'>";
  html+="<div class='bar-log' style='width:"+lp+"%;background:"+logC+";'></div>";
  html+="<div class='bar-rem' style='width:"+rp+"%;background:#f0a500;'></div>";
  html+="</div>";
  html+="<div class='bar-labels'>";
  html+="<span style='color:"+logC+";'>&#9632; "+lh.toFixed(1)+"h log</span>";
  html+="<span style='color:#f0a500;'>&#9632; "+rh.toFixed(1)+"h rest</span>";
  html+="<span>/ 160h</span></div>";
  if(s.capex_pct+s.opex_pct>0){
    html+="<div class='inv-bar'>";
    html+="<div style='flex:"+s.capex_pct+";background:#378add;'></div>";
    html+="<div style='flex:"+s.opex_pct+";background:#f0a500;'></div></div>";
    html+="<div class='inv-labels'>";
    html+="<span style='color:#378add;font-weight:600;'>&#9632;CAP "+s.capex_pct+"%</span> ";
    html+="<span style='color:#f0a500;font-weight:600;'>&#9632;OPE "+s.opex_pct+"%</span></div>";
  }
  html+="<div class='divider'></div>";
  if(hR) html+="<div class='br'><span class='bl lreq'>REQ</span><div class='chips'>"+chipsHtml(req,"REQ")+"</div></div>";
  if(hS) html+="<div class='br'><span class='bl lser'>SER</span><div class='chips'>"+chipsHtml(ser,"SER")+"</div></div>";
  if(hD) html+="<div class='br'><span class='bl ldev'>DEV</span><div class='chips'>"+chipsHtml(dev,"DEV")+"</div></div>";
  html+="</div>";
  return html;
}

function selCard(idx){
  document.querySelectorAll(".pc").forEach(function(c,j){c.classList.toggle("sel",j===idx);});
  var list = curTeam==="Todos" ? ALL : ALL.filter(function(p){return p.team===curTeam;});
  renderDet(list[idx]);
  document.getElementById("det").scrollIntoView({behavior:"smooth",block:"nearest"});
}

var SOR=["[IN PROGRESS]","En curso","[BLOCKED]","Escalated","[RETURNED]","Pending",
         "Waiting for customer","Waiting for support","Waiting for approval",
         "[TO DO]","[READY FOR TESTING]","[IN TESTING]","[FINISHED]","Resolved","[SOLVED]","[CANCELED]"];
var SDOT={"[IN PROGRESS]":"dp","[BLOCKED]":"db","[RETURNED]":"dret","[TO DO]":"dt",
          "[FINISHED]":"df","[CANCELED]":"dc","[SOLVED]":"df","[READY FOR TESTING]":"dret",
          "[IN TESTING]":"dp","En curso":"dp","Escalated":"db","Pending":"dret",
          "Waiting for customer":"dret","Waiting for support":"dt","Waiting for approval":"dt","Resolved":"df"};

function renderDet(p){
  var s=p.stats;
  var lh=s.log_h,rh=Math.max(0,s.est_h-lh);
  var over=lh>s.est_h&&s.est_h>0;
  var logC=over?"#e24b4a":"#1d9e75";
  var lp=Math.min(lh/160*100,100).toFixed(1);
  var rp=Math.min(rh/160*100,100).toFixed(1);
  var grp={};
  SOR.forEach(function(st){grp[st]=[];});
  p.issues.forEach(function(i){if(grp[i.status])grp[i.status].push(i);else grp[i.status]=[i];});
  var issHtml="";
  SOR.forEach(function(st){
    var items=grp[st]||[];
    if(!items.length)return;
    issHtml+="<div class='sec'><div class='slbl'><span class='sdot "+(SDOT[st]||"dc")+"'></span>"+sl(st)+" <span style='opacity:.4;font-weight:400'>("+items.length+")</span></div>";
    items.forEach(function(i){
      var bprojCls=i.board==="SER"?"pser":i.board==="DEV"?"pdev":"preq";
      var dblabel="";
      if((i.status==="[BLOCKED]"||i.status==="Escalated")&&i.days_in_status>0){
        var dc=i.days_in_status>5?"#e24b4a":i.days_in_status>2?"#ba7517":"#888";
        dblabel="<span class='dblock' style='color:"+dc+";'>"+i.days_in_status+"d bloq</span>";
      }
      issHtml+="<div class='irow'>";
      issHtml+="<div><div class='ikey'><a href='https://lineru.atlassian.net/browse/"+i.key+"' target='_blank'>"+i.key+"</a></div>";
      issHtml+="<span class='iproj "+bprojCls+"'>"+i.proj+"</span></div>";
      issHtml+="<div><div class='ititle'>"+i.summary+dblabel+"</div></div>";
      issHtml+="<div class='tc'><div class='tn'>"+(i.est>0?(i.est/3600).toFixed(1)+"h":"&mdash;")+"</div>";
      if(i.log>0) issHtml+="<div style='font-size:9px;color:#aaa;'>log "+(i.log/3600).toFixed(1)+"h</div>";
      issHtml+="</div></div>";
    });
    issHtml+="</div>";
  });
  var html="<div class='det'>";
  html+="<div class='dh'><div class='dav' style='"+avc(p.name)+"'>"+ini(p.name)+"</div>";
  html+="<div><div class='dn'>"+p.name+"</div><div class='dm'>"+p.team+" &middot; "+s.total+" issues</div></div></div>";
  html+="<div class='mrow'>";
  html+="<div class='m'><div class='ml'>Estimado</div><div class='mv'>"+s.est_h.toFixed(1)+"h</div><div class='ms'>"+Math.min(s.est_h/160*100,999).toFixed(0)+"% de 160h</div></div>";
  html+="<div class='m'><div class='ml'>Logueado</div><div class='mv' style='color:"+logC+"'>"+lh.toFixed(1)+"h</div><div class='ms'>"+(over?"excedido":"registrado")+"</div></div>";
  html+="<div class='m'><div class='ml'>Restante</div><div class='mv' style='color:#f0a500'>"+rh.toFixed(1)+"h</div><div class='ms'>por ejecutar</div></div>";
  html+="<div class='m'><div class='ml'>Bloqueados</div><div class='mv' style='color:"+(s.blocked>0?"#e24b4a":"#1a1a1a")+"'>"+s.blocked+"</div><div class='ms'>requieren acción</div></div>";
  html+="<div class='m'><div class='ml'>Terminados</div><div class='mv' style='color:#1d9e75'>"+s.done+"</div><div class='ms'>de "+s.total+"</div></div>";
  html+="<div class='m'><div class='ml'>REQ/SER/DEV</div><div class='mv'>"+s.req+"/"+s.ser+"/"+s.dev+"</div><div class='ms'>tickets</div></div>";
  if(s.capex_pct+s.opex_pct>0){
    html+="<div class='m'><div class='ml'>CAPEX / OPEX</div>";
    html+="<div style='height:8px;border-radius:4px;overflow:hidden;display:flex;margin-top:5px;'>";
    html+="<div style='flex:"+s.capex_pct+";background:#378add;'></div>";
    html+="<div style='flex:"+s.opex_pct+";background:#f0a500;'></div></div>";
    html+="<div class='ms' style='margin-top:4px;'><span style='color:#378add;font-weight:600;'>"+s.capex_pct+"% ("+s.capex_h+"h)</span> <span style='color:#f0a500;font-weight:600;'>"+s.opex_pct+"% ("+s.opex_h+"h)</span></div></div>";
  }
  html+="</div>";
  html+="<div style='margin-bottom:.75rem;'>";
  html+="<div style='height:8px;background:#f0f0ec;border-radius:4px;overflow:hidden;display:flex;'>";
  html+="<div style='width:"+lp+"%;background:"+logC+";'></div>";
  html+="<div style='width:"+rp+"%;background:#f0a500;opacity:.7;'></div></div>";
  html+="<div style='display:flex;justify-content:space-between;font-size:10px;color:#888;margin-top:4px;'>";
  html+="<span style='color:"+logC+";font-weight:600;'>&#9632; Logueado: "+lh.toFixed(1)+"h</span>";
  html+="<span style='color:#f0a500;font-weight:600;'>&#9632; Restante: "+rh.toFixed(1)+"h</span>";
  html+="<span>Libre: "+Math.max(0,160-lh-rh).toFixed(1)+"h / 160h</span></div></div>";
  html+=issHtml+"</div>";
  document.getElementById("det").innerHTML=html;
}

render();
</script>
</body>
</html>"""

with open("dashboard_sprint_lineru.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"Dashboard generated: {len(html)} chars")
print(f"Updated: {updated}")
