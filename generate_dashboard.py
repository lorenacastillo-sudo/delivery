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
HEADERS = {
    "Authorization": f"Basic {AUTH}",
    "Content-Type": "application/json"
}

SER_STATUS_MAP = {
    'En curso':'En curso','Escalated':'Escalated','Pending':'Pending',
    'Waiting for customer':'Waiting for customer',
    'Waiting for support':'Waiting for support',
    'Waiting for approval':'Waiting for approval',
}

SER_OPEN = {'En curso','Escalated','Pending','Waiting for customer','Waiting for support','Waiting for approval'}

TEAM_MAP = {
    # Shared Services
    'Alexander Contreras': 'Shared Services',
    'Deisy Muñoz': 'Shared Services',
    'Gabriel Andrés Rondón Barragán': 'Shared Services',
    # Infraestructura
    'Omar Davila': 'Infraestructura',
    'David Tabla': 'Infraestructura',
    'Valentina Aguirre': 'Infraestructura',
    # Traction
    'Juan Pablo Velandia': 'Traction',
    'Edison Rojas': 'Traction',
    'Oscar Mendez': 'Traction',
    'Maria Paulina Ramirez Vasquez': 'Traction',
    'Joaquín Forero': 'Traction',
    # QA
    'Fabian Roa': 'QA',
    'Lorena Pacavita': 'QA',
    # Tech Product
    'Vivian Rodriguez': 'Tech Product',
    'Karen Garzón': 'Tech Product',
    # Client Management/Finance & Accounting
    'Arnold Blandon': 'Client Management/Finance & Accounting',
    'Anderson Caceres': 'Client Management/Finance & Accounting',
    'Miguel Jaramillo': 'Client Management/Finance & Accounting',
    # Onboarding
    'Luis Meza': 'Onboarding',
    'Heiner Granados': 'Onboarding',
    # Delivery
    'Lorena Castillo': 'Delivery',
    'Daniela Jaramillo': 'Delivery',
    # Legacy/Integrations
    'Andrés Bueno': 'Legacy/Integrations',
    'Daniela Guzman': 'Legacy/Integrations',
    'Jose Acevedo': 'Legacy/Integrations',
    'Javier Gutierrez': 'Legacy/Integrations',
}

# People to exclude from dashboard
EXCLUDE = {'Valentina Juya', 'Area Financiera', 'Sin asignar'}

# Infraestructura members who also get DEV tickets
INFRA_MEMBERS = {'Omar Davila', 'David Tabla', 'Valentina Aguirre'}


def fetch_all(jql, fields):
    all_issues = []
    url = f"{JIRA_BASE}/rest/api/3/search/jql"
    params = {
        "jql": jql,
        "fields": ",".join(fields),
        "maxResults": 100,
    }
    while True:
        r = requests.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)
        next_token = data.get("nextPageToken")
        if not next_token or not issues:
            break
        params = {
            "jql": jql,
            "fields": ",".join(fields),
            "maxResults": 100,
            "nextPageToken": next_token,
        }
    return all_issues

def get_last_comment(issue_key):
    """Fetch last comment for a blocked issue"""
    try:
        url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/comment"
        params = {"maxResults": 1, "orderBy": "-created"}
        r = requests.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()
        comments = data.get("comments", [])
        if not comments:
            return ""
        body = comments[-1].get("body", {})
        # Extract plain text from ADF format
        text = ""
        if isinstance(body, dict):
            for block in body.get("content", []):
                for inline in block.get("content", []):
                    if inline.get("type") == "text":
                        text += inline.get("text", "")
                    elif inline.get("type") == "mention":
                        text += "@" + inline.get("attrs", {}).get("text", "").replace("@","")
        elif isinstance(body, str):
            text = body
        return text[:200].strip()
    except:
        return ""

print("Fetching REQ issues (openSprints)...")
req_open = fetch_all(
    'sprint in openSprints() AND issuetype in ("Task","Bug","Subtask","Test Set")',
    ["summary","assignee","status","issuetype","project","timeoriginalestimate",
     "timespent","timeestimate","priority","customfield_10001","statuscategorychangedate","created","customfield_10937"]
)
print(f"REQ openSprints: {len(req_open)} issues")

print("Fetching REQ issues (sprint 2016)...")
req_2016 = fetch_all(
    'sprint = 2016 AND issuetype in ("Task","Bug","Subtask","Test Set")',
    ["summary","assignee","status","issuetype","project","timeoriginalestimate",
     "timespent","timeestimate","priority","customfield_10001","statuscategorychangedate","created","customfield_10937"]
)
print(f"REQ sprint 2016: {len(req_2016)} issues")

# Deduplicate by key
seen_keys = set()
req_issues = []
for i in req_open + req_2016:
    if i['key'] not in seen_keys:
        seen_keys.add(i['key'])
        req_issues.append(i)
print(f"REQ total (deduplicated): {len(req_issues)} issues")

print("Fetching SER issues...")
ser_issues = fetch_all(
    'project = SER AND status in ("En curso", "Escalated", "Pending", "Waiting for customer", "Waiting for support", "Waiting for approval")',
    ["summary","assignee","status","issuetype","project","timeoriginalestimate",
     "timespent","timeestimate","priority","customfield_10001","statuscategorychangedate","created","customfield_10937"]
)
print(f"SER: {len(ser_issues)} issues")

print("Fetching DEV issues for Infraestructura...")
dev_issues = fetch_all(
    'project = DEV AND status in ("En curso", "Escalated", "Pending", "Waiting for customer", "Waiting for support", "Waiting for approval", "Waiting for approval")',
    ["summary","assignee","status","issuetype","project","timeoriginalestimate",
     "timespent","timeestimate","priority","customfield_10001","statuscategorychangedate","created","customfield_10937"]
)
print(f"DEV: {len(dev_issues)} issues")

people = defaultdict(lambda: {'team':'Sin equipo','issues':[]})

for i in req_issues:
    f = i['fields']
    name = f['assignee']['displayName'] if f.get('assignee') else 'Sin asignar'
    if name in EXCLUDE:
        continue
    team = TEAM_MAP.get(name, (f.get('customfield_10001') or {}).get('name','Sin equipo'))
    status = f['status']['name']
    proj = f['project']['key']
    est = f.get('timeoriginalestimate') or 0
    log = f.get('timespent') or 0
    rem = f.get('timeestimate') or 0
    prio = (f.get('priority') or {}).get('name','Medium')
    summary = (f.get('summary') or '')[:70]
    itype = f['issuetype']['name']
    # Days in current status
    status_change = f.get('statuscategorychangedate','')[:10] if f.get('statuscategorychangedate') else ''
    days_in_status = 0
    if status_change:
        try:
            from datetime import datetime
            d = datetime.strptime(status_change, '%Y-%m-%d')
            days_in_status = (datetime.now() - d).days
        except:
            pass
    p = people[name]
    if p['team'] == 'Sin equipo' and team != 'Sin equipo':
        p['team'] = team
    inversion = (f.get('customfield_10937') or {}).get('value', '')
    p['issues'].append({
        'key': i['key'], 'summary': summary, 'status': status,
        'type': itype, 'proj': proj, 'est': est, 'log': log,
        'rem': rem, 'prio': prio, 'board': 'REQ', 'days_in_status': days_in_status,
        'last_comment': '', 'inversion': inversion
    })

for i in ser_issues:
    f = i['fields']
    name = f['assignee']['displayName'] if f.get('assignee') else 'Sin asignar'
    if name in EXCLUDE:
        continue
    raw_st = f['status']['name']
    status = SER_STATUS_MAP.get(raw_st, raw_st)
    if status not in SER_OPEN:
        continue
    team = TEAM_MAP.get(name, (f.get('customfield_10001') or {}).get('name','Sin equipo'))
    proj = f['project']['key']
    est = f.get('timeoriginalestimate') or 0
    log = f.get('timespent') or 0
    rem = f.get('timeestimate') or 0
    prio = (f.get('priority') or {}).get('name','Medium')
    summary = (f.get('summary') or '')[:70]
    itype = f['issuetype']['name']
    p = people[name]
    if p['team'] == 'Sin equipo' and team != 'Sin equipo':
        p['team'] = team
    p['issues'].append({
        'key': i['key'], 'summary': summary, 'status': status,
        'type': itype, 'proj': proj, 'est': est, 'log': log,
        'rem': rem, 'prio': prio, 'board': 'SER',
        'days_in_status': (lambda sc: ((__import__('datetime').datetime.now() - __import__('datetime').datetime.strptime(sc[:10], '%Y-%m-%d')).days) if sc else 0)(f.get('statuscategorychangedate','')),
        'last_comment': '', 'inversion': (f.get('customfield_10937') or {}).get('value', '')
    })

ACTIVE = {'[IN PROGRESS]','En curso','Pending'}
BLOCKED = {'[BLOCKED]','Escalated'}
DONE = {'[FINISHED]','Resolved','[CANCELED]','[SOLVED]'}

# Fetch last comment for all blocked REQ issues
print("Fetching comments for blocked issues...")
blocked_keys = [
    i['key'] for data in people.values()
    for i in data['issues']
    if i['status'] in {'[BLOCKED]', 'Escalated'} and i['board'] in {'REQ', 'DEV'}
]
print(f"Blocked issues: {len(blocked_keys)}")
comments_map = {}
for key in blocked_keys:
    comments_map[key] = get_last_comment(key)

# Attach comments to issues
for data in people.values():
    for i in data['issues']:
        if i['key'] in comments_map:
            i['last_comment'] = comments_map[i['key']]
        else:
            i['last_comment'] = ""

output = []
for name, data in sorted(people.items()):
    issues = data['issues']
    req_issues_only = [i for i in issues if i['board'] == 'REQ']
    capex_h = round(sum(i['est'] for i in req_issues_only if i.get('inversion') == 'CAPEX')/3600, 1)
    opex_h = round(sum(i['est'] for i in req_issues_only if i.get('inversion') == 'OPEX')/3600, 1)
    total_inv_h = capex_h + opex_h
    capex_pct = round(capex_h/total_inv_h*100) if total_inv_h > 0 else 0
    opex_pct = round(opex_h/total_inv_h*100) if total_inv_h > 0 else 0
    stats = {
        'total': len(issues),
        'est_h': round(sum(i['est'] for i in issues)/3600, 1),
        'log_h': round(sum(i['log'] for i in issues)/3600, 1),
        'inprog': sum(1 for i in issues if i['status'] in ACTIVE),
        'blocked': sum(1 for i in issues if i['status'] in BLOCKED),
        'todo': sum(1 for i in issues if i['status'] not in ACTIVE|BLOCKED|DONE|{'[RETURNED]'}),
        'done': sum(1 for i in issues if i['status'] in DONE),
        'ret': sum(1 for i in issues if i['status'] == '[RETURNED]'),
        'ser': sum(1 for i in issues if i['board'] == 'SER'),
        'req': sum(1 for i in issues if i['board'] == 'REQ'),
        'capex_h': capex_h, 'opex_h': opex_h,
        'capex_pct': capex_pct, 'opex_pct': opex_pct,
    }
    output.append({'name': name, 'team': data['team'], 'issues': issues, 'stats': stats})

updated = datetime.now().strftime("%d/%m/%Y %H:%M")
data_json = json.dumps(output, ensure_ascii=False)

html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sprint Dashboard · Lineru</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f3;color:#1a1a1a;padding:1.5rem;}}
.hdr{{display:flex;align-items:center;gap:10px;margin-bottom:1.25rem;padding-bottom:.85rem;border-bottom:1px solid #e0e0dc;background:#fff;padding:1rem 1.25rem;border-radius:12px;margin-bottom:1rem;}}
.hdr-title{{font-size:16px;font-weight:600;}}.hdr-sub{{font-size:11px;color:#666;margin-top:2px;}}
.pulse{{width:8px;height:8px;border-radius:50%;background:#1d9e75;animation:pulse 2s infinite;flex-shrink:0;}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.updated{{margin-left:auto;font-size:10px;color:#aaa;white-space:nowrap;}}
.pills{{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:1rem;}}
.pill{{padding:4px 12px;border-radius:16px;font-size:11px;font-weight:500;cursor:pointer;border:1px solid #ddd;background:#fff;color:#555;transition:all .12s;}}
.pill.on{{background:#1a1a1a;color:#fff;border-color:#1a1a1a;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px;margin-bottom:1rem;}}
.pcard{{background:#fff;border-radius:10px;padding:12px;cursor:pointer;border:1.5px solid transparent;transition:all .12s;}}
.pcard:hover{{border-color:#ccc;}}.pcard.sel{{border-color:#378add;box-shadow:0 0 0 3px rgba(55,138,221,.1);}}
.av{{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;margin-bottom:8px;}}
.pname{{font-size:12px;font-weight:600;}}.pteam{{font-size:10px;color:#888;margin-top:1px;}}
.divider{{height:1px;background:#f0f0ec;margin:8px 0;}}
.board-row{{display:flex;align-items:flex-start;gap:6px;margin-bottom:4px;}}
.board-label{{font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;white-space:nowrap;margin-top:1px;}}
.lreq{{background:#eaf3de;color:#27500a;}}.lser{{background:#eeedfe;color:#3c3489;}}
.chips{{display:flex;gap:3px;flex-wrap:wrap;}}
.ch{{font-size:9px;padding:1px 5px;border-radius:5px;font-weight:500;white-space:nowrap;}}
.ch-p{{background:#eaf3de;color:#27500a;}}.ch-b{{background:#fcebeb;color:#791f1f;}}
.ch-t{{background:#e6f1fb;color:#0c447c;}}.ch-f{{background:#e1f5ee;color:#085041;}}
.ch-r{{background:#faece7;color:#712b13;}}.ch-s{{background:#eeedfe;color:#3c3489;}}
.ch-enc{{background:#eaf3de;color:#27500a;}}.ch-esc{{background:#fcebeb;color:#791f1f;}}
.ch-wf{{background:#eeedfe;color:#3c3489;}}.ch-res{{background:#e1f5ee;color:#085041;}}
.ch-pen{{background:#faeeda;color:#633806;}}
.detail{{background:#fff;border:1px solid #e8e8e4;border-radius:12px;padding:1.25rem;margin-top:.75rem;}}
.dhdr{{display:flex;align-items:center;gap:12px;margin-bottom:1rem;}}
.dav{{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:600;}}
.dname{{font-size:15px;font-weight:600;}}.dmeta{{font-size:11px;color:#666;margin-top:2px;}}
.mrow{{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:8px;margin-bottom:1rem;}}
.m{{background:#f7f7f5;border-radius:8px;padding:10px 12px;}}
.ml{{font-size:10px;color:#666;}}.mv{{font-size:19px;font-weight:600;margin-top:3px;}}.ms{{font-size:9px;color:#aaa;margin-top:2px;}}
.pb-wrap{{margin-bottom:1rem;}}
.pb-lbl{{display:flex;justify-content:space-between;font-size:10.5px;color:#666;margin-bottom:5px;}}
.pb-track{{height:7px;background:#f0f0ec;border-radius:4px;overflow:hidden;}}
.pb-fill{{height:100%;border-radius:4px;}}
.sec{{margin-top:1rem;}}
.slbl{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#888;display:flex;align-items:center;gap:5px;margin-bottom:6px;}}
.sdot{{width:6px;height:6px;border-radius:50%;display:inline-block;}}
.dp{{background:#1d9e75;}}.db{{background:#e24b4a;}}.dt{{background:#378add;}}.df2{{background:#9dd4be;}}.dr{{background:#ba7517;}}.dc{{background:#ccc;}}
.irow{{display:grid;grid-template-columns:90px 1fr auto;gap:8px;align-items:start;padding:7px 0;border-bottom:1px solid #f5f5f3;}}
.irow:last-child{{border-bottom:none;}}
.ikey{{font-size:10px;font-weight:500;color:#555;font-family:monospace;}}
.ikey a{{color:#1a1a1a;text-decoration:none;}}.ikey a:hover{{color:#378add;text-decoration:underline;}}
.iproj{{font-size:8.5px;padding:1px 4px;border-radius:3px;margin-top:3px;display:inline-block;}}
.ps{{background:#eeedfe;color:#3c3489;}}.pr{{background:#eaf3de;color:#27500a;}}
.ititle{{font-size:11.5px;line-height:1.4;color:#1a1a1a;}}
.itags{{display:flex;gap:3px;flex-wrap:wrap;margin-top:3px;}}
.tag{{font-size:8.5px;padding:1px 5px;border-radius:4px;}}
.tag-h{{background:#fcebeb;color:#791f1f;font-weight:600;}}
.tc{{text-align:right;white-space:nowrap;}}
.tn{{font-size:10px;color:#888;font-family:monospace;}}
.tlog{{font-size:9px;color:#aaa;margin-top:2px;}}
.mini-bar{{width:50px;height:3px;background:#f0f0ec;border-radius:2px;overflow:hidden;margin:3px 0 0 auto;}}
.mini-fill{{height:100%;border-radius:2px;}}
.bar-ok{{background:#1d9e75;}}.bar-ov{{background:#e24b4a;}}.bar-ze{{background:#ddd;}}
.empty{{text-align:center;padding:3rem;color:#aaa;font-size:13px;}}
@media(max-width:600px){{.grid{{grid-template-columns:1fr 1fr;}}.irow{{grid-template-columns:auto 1fr auto;}}}}
</style>
</head>
<body>

<div class="hdr">
  <div class="pulse"></div>
  <div>
    <div class="hdr-title">Sprint Dashboard &middot; Lineru</div>
    <div class="hdr-sub">Sprint activo &middot; Task / Bug / Subtask / Test Set &middot; SER + REQ</div>
  </div>
  <div class="updated">&#x1F504; Actualizado: {updated}</div>
</div>

<div class="pills" id="pills"></div>
<div class="grid" id="grid"></div>
<div id="detail"></div>

<script>
var ALL={data_json};
var AC=["#e6f1fb","#eaf3de","#faeeda","#eeedfe","#faece7","#fbeaf0"];
var AT=["#0c447c","#27500a","#633806","#3c3489","#712b13","#72243e"];
var TEAMS=["Todos","Onboarding","Traction","Legacy/Integrations","QA","Tech Product","Shared Services","Infraestructura","Client Management/Finance & Accounting","Delivery","Sin equipo"];
var curTeam="Todos";
function ini(n){{return n.split(" ").slice(0,2).map(function(w){{return w[0];}}).join("").toUpperCase();}}
function avc(n){{var i=n.charCodeAt(0)%AC.length;return "background:"+AC[i]+";color:"+AT[i]+";";}}
function sl(st){{var m={{"[IN PROGRESS]":"In Progress","[BLOCKED]":"Blocked","[RETURNED]":"Returned","[TO DO]":"To Do","[FINISHED]":"Finished","[CANCELED]":"Canceled","[SOLVED]":"Solved","[READY FOR TESTING]":"Rdy Test","[IN TESTING]":"In Testing","En curso":"En curso","Escalated":"Escalated","Pending":"Pending","Waiting for customer":"Wtg Customer","Waiting for support":"Wtg Support","Waiting for approval":"Wtg Approval","Resolved":"Resolved"}};return m[st]||st;}}
function rc(st){{if(st==="[IN PROGRESS]")return "ch-p";if(st==="[BLOCKED]")return "ch-b";if(st==="[RETURNED]")return "ch-r";if(st==="[TO DO]")return "ch-t";if(["[FINISHED]","[SOLVED]","[CANCELED]"].indexOf(st)>-1)return "ch-f";return "ch-s";}}
function sc(st){{if(st==="En curso")return "ch-enc";if(st==="Escalated")return "ch-esc";if(st==="Pending")return "ch-pen";if(["Waiting for customer","Waiting for support","Waiting for approval"].indexOf(st)>-1)return "ch-wf";if(st==="Resolved")return "ch-res";return "ch-s";}}
function ab(issues,board){{var c={{}};issues.filter(function(i){{return i.board===board;}}).forEach(function(i){{c[i.status]=(c[i.status]||0)+1;}});return c;}}
function chips(counts,cf){{return Object.keys(counts).map(function(st){{return "<span class=\\"ch "+cf(st)+"\\">"+counts[st]+" "+sl(st)+"</span>";}}).join("");}}
function render(){{
  var pEl=document.getElementById("pills");
  pEl.innerHTML=TEAMS.map(function(t){{return "<div class=\\"pill"+(t===curTeam?" on":"")+"\\" onclick=\\"setTeam('"+t.replace(/'/g,"\\'")+"')\\">"+t.replace("Client Management/Finance & Accounting","Client Mgmt")+"</div>";}}).join("");
  var list=filt();
  var gEl=document.getElementById("grid");
  if(!list.length){{gEl.innerHTML="<div class=\\"empty\\" style=\\"grid-column:1/-1\\">Sin personas en este equipo.</div>";return;}}
  gEl.innerHTML=list.map(function(p,i){{return card(p,i);}}).join("");
}}
function filt(){{return curTeam==="Todos"?ALL:ALL.filter(function(p){{return p.team===curTeam;}});}}
function setTeam(t){{curTeam=t;document.getElementById("detail").innerHTML="";render();}}
function card(p,i){{
  var req=ab(p.issues,"REQ");var ser=ab(p.issues,"SER");var dev=ab(p.issues,"DEV");
  var hR=Object.keys(req).length>0;var hS=Object.keys(ser).length>0;var hD=Object.keys(dev).length>0;
  var pct=Math.min(p.stats.est_h/160*100,100);
  var bc=p.stats.blocked>3?"#e24b4a":p.stats.est_h>120?"#ba7517":"#1d9e75";
  return "<div class=\\"pcard\\" onclick=\\"sel("+i+")\\">"
    +"<div style=\\"display:flex;align-items:center;gap:8px;margin-bottom:8px;\\">"
    +"<div class=\\"av\\" style=\\""+avc(p.name)+"\\">"+ini(p.name)+"</div>"
    +"<div><div class=\\"pname\\">"+p.name+"</div><div class=\\"pteam\\">"+p.team+"</div></div></div>"
    +"<div style=\\"display:flex;justify-content:space-between;font-size:9.5px;color:#999;margin-bottom:4px;\\">"
    +"<span>"+p.stats.total+" issues &middot; "+p.stats.est_h.toFixed(1)+"h</span>"
    +"<span>"+pct.toFixed(0)+"% cap</span></div>"
    +"<div style=\\"height:4px;background:#f0f0ec;border-radius:2px;overflow:hidden;margin-bottom:8px;\\">"
    +"<div style=\\"height:100%;width:"+pct.toFixed(0)+"%;background:"+bc+";border-radius:2px;\\"></div></div>"
    +"<div class=\\"divider\\"></div>"
    +(hR?"<div class=\\"board-row\\"><span class=\\"board-label lreq\\">REQ</span><div class=\\"chips\\">"+chips(req,rc)+"</div></div>":"")
    +(hS?"<div class=\\"board-row\\"><span class=\\"board-label lser\\">SER</span><div class=\\"chips\\">"+chips(ser,sc)+"</div></div>":"")
    +"</div>";
}}
function sel(i){{
  document.querySelectorAll(".pcard").forEach(function(c,j){{c.classList.toggle("sel",j===i);}});
  var list=filt();det(list[i]);
  document.getElementById("detail").scrollIntoView({{behavior:"smooth",block:"nearest"}});
}}
var SOR=["[IN PROGRESS]","En curso","[BLOCKED]","Escalated","[RETURNED]","Pending","Waiting for customer","Waiting for support","Waiting for approval","[TO DO]","[READY FOR TESTING]","[IN TESTING]","[FINISHED]","Resolved","[SOLVED]","[CANCELED]"];
var SD={{"[IN PROGRESS]":"dp","[BLOCKED]":"db","[RETURNED]":"dr","[TO DO]":"dt","[FINISHED]":"df2","[CANCELED]":"dc","[SOLVED]":"df2","[READY FOR TESTING]":"dr","[IN TESTING]":"dp","En curso":"dp","Escalated":"db","Pending":"dr","Waiting for customer":"dr","Waiting for support":"dt","Waiting for approval":"dt","Resolved":"df2"}};
function det(p){{
  var s=p.stats;var fc=s.blocked>3?"#e24b4a":s.est_h>120?"#ba7517":"#1d9e75";
  var grp={{}};SOR.forEach(function(st){{grp[st]=[];}});
  p.issues.forEach(function(i){{if(grp[i.status])grp[i.status].push(i);else grp[i.status]=[i];}});
  var iss="";
  SOR.forEach(function(st){{
    var items=grp[st]||[];if(!items.length)return;
    iss+="<div class=\\"sec\\"><div class=\\"slbl\\"><span class=\\"sdot "+(SD[st]||"dc")+"\\"></span>"+sl(st)+" <span style=\\"opacity:.4;font-weight:400\\">("+items.length+")</span></div>";
    items.forEach(function(i){{
      var bp=i.est>0?Math.min(i.log/i.est,1)*100:0;
      var bc2=i.log>i.est&&i.est>0?"bar-ov":i.est===0?"bar-ze":"bar-ok";
      iss+="<div class=\\"irow\\">"
        +"<div><div class=\\"ikey\\"><a href=\\"https://lineru.atlassian.net/browse/"+i.key+"\\" target=\\"_blank\\">"+i.key+"</a></div>"
        +"<span class=\\"iproj "+(i.board==="SER"?"ps":"pr")+"\\">"+i.proj+"</span></div>"
        +"<div><div class=\\"ititle\\">"+i.summary+"</div>"
        +(i.prio==="High"?"<div class=\\"itags\\"><span class=\\"tag tag-h\\">High</span></div>":"")
        +"</div>"
        +"<div class=\\"tc\\"><div class=\\"tn\\">"+(i.est>0?(i.est/3600).toFixed(1)+"h":"&mdash;")+"</div>"
        +(i.log>0?"<div class=\\"tlog\\">log: "+(i.log/3600).toFixed(1)+"h</div>":"")
        +"<div class=\\"mini-bar\\"><div class=\\"mini-fill "+bc2+"\\" style=\\"width:"+Math.round(bp)+"%\\"></div></div>"
        +"</div></div>";
    }});
    iss+="</div>";
  }});
  document.getElementById("detail").innerHTML="<div class=\\"detail\\">"
    +"<div class=\\"dhdr\\"><div class=\\"dav\\" style=\\""+avc(p.name)+"\\">"+ini(p.name)+"</div>"
    +"<div><div class=\\"dname\\">"+p.name+"</div><div class=\\"dmeta\\">"+p.team+" &middot; "+s.total+" issues</div></div></div>"
    +"<div class=\\"mrow\\">"
    +"<div class=\\"m\\"><div class=\\"ml\\">Estimado</div><div class=\\"mv\\">"+s.est_h.toFixed(1)+"h</div><div class=\\"ms\\">"+Math.min(s.est_h/160*100,999).toFixed(0)+"% de 160h</div></div>"
    +"<div class=\\"m\\"><div class=\\"ml\\">Logueado</div><div class=\\"mv\\">"+s.log_h.toFixed(1)+"h</div><div class=\\"ms\\">horas registradas</div></div>"
    +"<div class=\\"m\\"><div class=\\"ml\\">In Progress</div><div class=\\"mv\\" style=\\"color:#1d9e75\\">"+s.inprog+"</div><div class=\\"ms\\">activos</div></div>"
    +"<div class=\\"m\\"><div class=\\"ml\\">Bloqueados</div><div class=\\"mv\\" style=\\"color:"+(s.blocked>0?"#e24b4a":"#1a1a1a")+"\\">"+s.blocked+"</div><div class=\\"ms\\">requieren acción</div></div>"
    +"<div class=\\"m\\"><div class=\\"ml\\">Terminados</div><div class=\\"mv\\" style=\\"color:#1d9e75\\">"+s.done+"</div><div class=\\"ms\\">de "+s.total+"</div></div>"
    +"<div class=\\"m\\"><div class=\\"ml\\">SER / REQ</div><div class=\\"mv\\">"+s.ser+" / "+s.req+"</div><div class=\\"ms\\">tickets</div></div>"
    +"</div>"
    +"<div class=\\"pb-wrap\\"><div class=\\"pb-lbl\\"><span>Capacidad utilizada vs 160h</span><span>"+s.est_h.toFixed(1)+"h / 160h</span></div>"
    +"<div class=\\"pb-track\\"><div class=\\"pb-fill\\" style=\\"width:"+Math.min(s.est_h/160*100,100).toFixed(0)+"%;background:"+fc+"\\"></div></div></div>"
    +iss+"</div>";
}}
render();
</script>
</body>
</html>"""

with open("dashboard_sprint_lineru.html", "w", encoding="utf-8") as f:
    f.write(html)

# Process DEV issues (only for Infraestructura members)
for i in dev_issues:
    f = i['fields']
    name = f['assignee']['displayName'] if f.get('assignee') else 'Sin asignar'
    if name not in INFRA_MEMBERS:
        continue
    raw_st = f['status']['name']
    status = SER_STATUS_MAP.get(raw_st, raw_st)
    if status not in SER_OPEN:
        continue
    team = 'Infraestructura'
    proj = f['project']['key']
    est = f.get('timeoriginalestimate') or 0
    log = f.get('timespent') or 0
    rem = f.get('timeestimate') or 0
    prio = (f.get('priority') or {}).get('name','Medium')
    summary = (f.get('summary') or '')[:70]
    itype = f['issuetype']['name']
    days_in_status = (lambda sc: ((__import__('datetime').datetime.now() - __import__('datetime').datetime.strptime(sc[:10], '%Y-%m-%d')).days) if sc else 0)(f.get('statuscategorychangedate',''))
    p = people[name]
    if p['team'] == 'Sin equipo':
        p['team'] = team
    p['issues'].append({
        'key': i['key'], 'summary': summary, 'status': status,
        'type': itype, 'proj': proj, 'est': est, 'log': log,
        'rem': rem, 'prio': prio, 'board': 'DEV', 'days_in_status': days_in_status,
        'last_comment': '', 'inversion': (f.get('customfield_10937') or {}).get('value', '')
    })

print(f"Dashboard generated: {len(html)} chars")
print(f"Updated: {updated}")
