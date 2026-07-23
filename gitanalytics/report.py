from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .util import atomic_write_text


def _safe_json(data: Any) -> str:
    """Serialize JSON for embedding in an HTML script element."""
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_html(report: dict[str, Any]) -> str:
    payload = _safe_json(report)
    return r'''<!doctype html>
<html lang="de" data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>GitAnalytics</title>
<style>
:root {
  --bg: #f4f6f8; --panel: #ffffff; --panel-2: #f8fafc; --text: #17202a;
  --muted: #64748b; --border: #dfe5ec; --accent: #315efb; --accent-2: #163da8;
  --good: #18864b; --warn: #a96200; --bad: #b42318; --shadow: 0 8px 24px rgba(21,35,55,.08);
  --heat-0: #e9eef5; --heat-1: #c6d7ff; --heat-2: #8eafff; --heat-3: #537df0; --heat-4: #254bb8;
  --radius: 14px; --mono: ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
html[data-theme="dark"] {
  --bg: #0d1117; --panel: #151b23; --panel-2: #1c2430; --text: #e6edf3;
  --muted: #9aa8b7; --border: #2d3745; --accent: #7aa2ff; --accent-2: #b9ccff;
  --good: #52c781; --warn: #f0ae4b; --bad: #ff7b72; --shadow: 0 8px 24px rgba(0,0,0,.28);
  --heat-0: #202936; --heat-1: #263b68; --heat-2: #31569b; --heat-3: #4d76d7; --heat-4: #89a9ff;
}
@media (prefers-color-scheme: dark) {
  html[data-theme="auto"] {
    --bg: #0d1117; --panel: #151b23; --panel-2: #1c2430; --text: #e6edf3;
    --muted: #9aa8b7; --border: #2d3745; --accent: #7aa2ff; --accent-2: #b9ccff;
    --good: #52c781; --warn: #f0ae4b; --bad: #ff7b72; --shadow: 0 8px 24px rgba(0,0,0,.28);
    --heat-0: #202936; --heat-1: #263b68; --heat-2: #31569b; --heat-3: #4d76d7; --heat-4: #89a9ff;
  }
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
button,input { font:inherit; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
a { color:var(--accent); }
.shell { min-height:100vh; display:grid; grid-template-columns:235px minmax(0,1fr); }
.sidebar { position:sticky; top:0; height:100vh; padding:24px 16px; background:var(--panel); border-right:1px solid var(--border); overflow:auto; }
.brand { display:flex; align-items:center; gap:10px; margin:0 8px 24px; }
.logo { width:36px; height:36px; border-radius:10px; background:linear-gradient(135deg,var(--accent),var(--accent-2)); display:grid; place-items:center; color:white; font-weight:800; letter-spacing:-1px; }
.brand strong { display:block; font-size:18px; line-height:1.1; }
.brand small { color:var(--muted); }
.nav { display:grid; gap:4px; }
.nav button { width:100%; border:0; background:transparent; color:var(--muted); padding:10px 12px; text-align:left; border-radius:9px; cursor:pointer; }
.nav button:hover,.nav button.active { color:var(--text); background:var(--panel-2); }
.nav button.active { box-shadow:inset 3px 0 var(--accent); }
.side-meta { margin-top:24px; padding:14px 12px; color:var(--muted); border-top:1px solid var(--border); font-size:12px; overflow-wrap:anywhere; }
.main { min-width:0; }
.topbar { position:sticky; top:0; z-index:20; min-height:70px; padding:14px 28px; display:flex; align-items:center; justify-content:space-between; gap:18px; background:color-mix(in srgb,var(--bg) 88%,transparent); backdrop-filter:blur(14px); border-bottom:1px solid var(--border); }
.topbar h1 { margin:0; font-size:20px; line-height:1.2; }
.topbar p { margin:3px 0 0; color:var(--muted); font-size:12px; }
.actions { display:flex; gap:8px; }
.filters { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:0 0 20px; padding:12px; background:var(--panel); border:1px solid var(--border); border-radius:10px; }
.filters label { color:var(--muted); font-size:12px; }
.filters select { margin-left:6px; max-width:260px; padding:6px 8px; border:1px solid var(--border); border-radius:7px; background:var(--panel-2); color:var(--text); }
.action { border:1px solid var(--border); background:var(--panel); color:var(--text); border-radius:9px; padding:7px 10px; cursor:pointer; }
.content { max-width:1540px; margin:0 auto; padding:28px; }
.page { display:none; }
.page.active { display:block; }
.page-head { display:flex; align-items:end; justify-content:space-between; gap:20px; margin:0 0 20px; }
.page-head h2 { margin:0; font-size:24px; }
.page-head p { margin:5px 0 0; color:var(--muted); max-width:850px; }
.grid { display:grid; gap:16px; }
.kpis { grid-template-columns:repeat(6,minmax(125px,1fr)); margin-bottom:16px; }
.grid-2 { grid-template-columns:repeat(2,minmax(0,1fr)); }
.grid-3 { grid-template-columns:repeat(3,minmax(0,1fr)); }
.card { background:var(--panel); border:1px solid var(--border); border-radius:var(--radius); box-shadow:var(--shadow); padding:18px; min-width:0; }
.card h3 { margin:0 0 4px; font-size:15px; }
.card .sub { color:var(--muted); font-size:12px; margin-bottom:13px; }
.kpi { padding:15px 16px; }
.kpi .label { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.055em; overflow-wrap:anywhere; }
.kpi .value { margin-top:5px; font-size:25px; font-weight:750; letter-spacing:-.025em; }
.kpi .detail { color:var(--muted); font-size:11px; min-height:17px; }
.stat-row { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px; }
.stat { background:var(--panel-2); border:1px solid var(--border); border-radius:10px; padding:12px; }
.stat strong { display:block; font-size:18px; }
.stat span { color:var(--muted); font-size:11px; }
.insight-list { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
.insight { background:var(--panel-2); border:1px solid var(--border); border-radius:10px; padding:12px; }
.insight span { display:block; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }
.insight strong { display:block; margin-top:4px; font-size:16px; overflow-wrap:anywhere; }
.chart { min-height:245px; width:100%; overflow:hidden; }
.chart svg { display:block; width:100%; height:auto; overflow:visible; }
.axis-label { fill:var(--muted); font-size:10px; }
.grid-line { stroke:var(--border); stroke-width:1; }
.line { fill:none; stroke:var(--accent); stroke-width:2.5; }
.area { fill:color-mix(in srgb,var(--accent) 15%,transparent); }
.dot { fill:var(--accent); }
.dot[data-crossfilter] { cursor:pointer; }
.bar-list { display:grid; gap:9px; }
.bar-row { display:grid; grid-template-columns:minmax(95px,1.4fr) minmax(100px,4fr) auto; align-items:center; gap:10px; }
.bar-row { width:100%; border:0; padding:0; background:transparent; color:inherit; text-align:left; }
.bar-row.filterable { cursor:pointer; border-radius:6px; }
.bar-row.filterable:hover { background:var(--panel-2); }
.bar-label { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.bar-track { height:9px; background:var(--panel-2); border:1px solid var(--border); border-radius:999px; overflow:hidden; }
.bar-fill { height:100%; min-width:1px; background:var(--accent); border-radius:999px; }
.bar-value { color:var(--muted); font-variant-numeric:tabular-nums; }
.heat-wrap { overflow:auto; padding-bottom:4px; }
.heat-grid { min-width:830px; display:grid; grid-template-columns:78px repeat(24,1fr); gap:3px; align-items:center; }
.heat-cell { aspect-ratio:1; min-width:20px; border:0; padding:0; border-radius:3px; background:var(--heat-0); color:transparent; }
.heat-cell[data-crossfilter] { cursor:pointer; }
.heat-label { color:var(--muted); font-size:10px; text-align:center; }
.calendar { display:grid; grid-auto-flow:column; grid-template-rows:repeat(7,12px); grid-auto-columns:12px; gap:3px; overflow:auto; padding:8px 2px 12px; }
.calendar-cell { width:12px; height:12px; border:0; padding:0; border-radius:2px; background:var(--heat-0); cursor:pointer; }
.legend { display:flex; align-items:center; justify-content:flex-end; gap:4px; margin-top:7px; color:var(--muted); font-size:10px; }
.legend i { width:12px; height:12px; border-radius:2px; }
.table-tools { display:flex; gap:10px; justify-content:space-between; align-items:center; margin:4px 0 12px; }
.search { min-width:240px; max-width:360px; width:100%; border:1px solid var(--border); background:var(--panel-2); color:var(--text); border-radius:9px; padding:8px 10px; }
.table-wrap { overflow:auto; border:1px solid var(--border); border-radius:10px; }
table { width:100%; border-collapse:collapse; font-size:12px; }
th,td { padding:9px 10px; border-bottom:1px solid var(--border); text-align:left; white-space:nowrap; }
th { position:sticky; top:0; background:var(--panel-2); color:var(--muted); cursor:pointer; user-select:none; z-index:2; }
th[aria-sort="ascending"],th[aria-sort="descending"] { color:var(--text); }
th .sort-ind { display:inline-block; width:1em; color:var(--muted); }
th[aria-sort] .sort-ind { color:var(--accent); }
tbody tr:hover { background:var(--panel-2); }
tbody tr:last-child td { border-bottom:0; }
td.num,th.num { text-align:right; font-variant-numeric:tabular-nums; }
.table-filter { border:0; padding:0; background:transparent; color:var(--accent); cursor:pointer; text-align:inherit; font:inherit; }
.badge { display:inline-flex; align-items:center; border:1px solid var(--border); border-radius:999px; padding:2px 7px; font-size:10px; background:var(--panel-2); }
.badge.active,.badge.ready { color:var(--good); }
.badge.quiet,.badge.stale { color:var(--warn); }
.badge.dormant,.badge.error { color:var(--bad); }
.notice { border-left:4px solid var(--warn); background:var(--panel-2); border-radius:8px; padding:10px 12px; margin:8px 0; }
.notice.bad { border-left-color:var(--bad); }
.notice.good { border-left-color:var(--good); }
.empty { min-height:130px; display:grid; place-items:center; text-align:center; color:var(--muted); }
.code { font:12px/1.55 var(--mono); white-space:pre-wrap; overflow-wrap:anywhere; background:var(--panel-2); border:1px solid var(--border); border-radius:10px; padding:13px; }
.muted { color:var(--muted); }
.mt { margin-top:16px; }
.footer { color:var(--muted); text-align:center; padding:16px 28px 32px; font-size:11px; }
@media (max-width:1200px) { .kpis { grid-template-columns:repeat(3,1fr); } .grid-3 { grid-template-columns:1fr 1fr; } }
@media (max-width:850px) {
  .shell { grid-template-columns:1fr; }
  .sidebar { position:static; height:auto; border-right:0; border-bottom:1px solid var(--border); padding:12px 16px; }
  .brand { margin:0 0 10px; }
  .nav { display:flex; overflow:auto; }
  .nav button { white-space:nowrap; width:auto; }
  .side-meta { display:none; }
  .topbar { top:0; padding:12px 16px; }
  .content { padding:18px 14px; }
  .grid-2,.grid-3 { grid-template-columns:1fr; }
  .insight-list { grid-template-columns:1fr 1fr; }
}
@media (max-width:520px) { .kpis { grid-template-columns:1fr 1fr; } .actions .print { display:none; } .insight-list { grid-template-columns:1fr; } }
@media print {
  :root { --bg:#fff; --panel:#fff; --text:#111; --muted:#555; --border:#ddd; --shadow:none; }
  .shell { display:block; } .sidebar,.topbar,.table-tools { display:none!important; }
  .content { max-width:none; padding:0; } .page { display:block!important; break-before:page; }
  .page:first-child { break-before:auto; } .card { break-inside:avoid; box-shadow:none; }
}
</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="brand"><div class="logo">GA</div><div><strong>GitAnalytics</strong><small>Repository Intelligence</small></div></div>
    <nav class="nav" aria-label="Berichtsbereiche">
      <button class="active" data-page="overview" aria-controls="page-overview" aria-current="page">Übersicht</button>
      <button data-page="activity" aria-controls="page-activity">Aktivität</button>
      <button data-page="repositories" aria-controls="page-repositories">Repositories</button>
      <button data-page="contributors" aria-controls="page-contributors">Autoren</button>
      <button data-page="collaboration" data-optional-page="collaboration" aria-controls="page-collaboration">Netzwerk</button>
      <button data-page="code" aria-controls="page-code">Code & Hotspots</button>
      <button data-page="releases" aria-controls="page-releases">Releases</button>
      <button data-page="quality" aria-controls="page-quality">Datenqualität</button>
    </nav>
    <div class="side-meta" id="side-meta"></div>
  </aside>
  <main class="main">
    <header class="topbar">
      <div><h1 id="report-title">GitAnalytics</h1><p id="report-subtitle"></p></div>
      <div class="actions"><label class="sr-only" for="language-select">Sprache</label><select class="action" id="language-select" aria-label="Sprache"><option value="de">Deutsch</option><option value="en">English</option></select><button class="action print" onclick="window.print()">Drucken</button><button class="action" id="theme-button" title="Darstellung wechseln">Darstellung</button></div>
    </header>
    <div class="content">
      <div class="filters" aria-label="Dashboard-Filter"><label>Zuletzt bearbeitet <select id="recent-filter"><option value="">Beliebiger Zeitpunkt</option><option value="1">letzter Tag</option><option value="7">letzte 7 Tage</option><option value="30">letzte 30 Tage</option><option value="180">letzte 180 Tage</option><option value="365">letzte 365 Tage</option><option value="730">letzte 2 Jahre</option></select></label><label>Branch (HEAD/Standard) <select id="branch-filter"><option value="">Beliebiger Branch</option><option value="main">main</option><option value="master">master</option></select></label><label>Repository <select id="repo-filter" multiple size="1"></select></label><label>Programmiersprache <select id="language-filter" multiple size="1"></select></label><label>Dateityp <select id="file-type-filter" multiple size="1"></select></label><button class="action" id="clear-filters" type="button">Filter zurücksetzen</button><span class="muted" id="filter-result" aria-live="polite" aria-atomic="true"></span></div>
      <section class="page active" id="page-overview" role="region"></section>
      <section class="page" id="page-activity" role="region"></section>
      <section class="page" id="page-repositories" role="region"></section>
      <section class="page" id="page-contributors" role="region"></section>
      <section class="page" id="page-collaboration" role="region"></section>
      <section class="page" id="page-code" role="region"></section>
      <section class="page" id="page-releases" role="region"></section>
      <section class="page" id="page-quality" role="region"></section>
    </div>
    <footer class="footer">Offline-Bericht · Keine externen Skripte, Fonts oder Tracking-Dienste</footer>
  </main>
</div>
<script id="gitanalytics-data" type="application/json">''' + payload + r'''</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('gitanalytics-data').textContent);
let locale = 'de-DE';
let nf = new Intl.NumberFormat(locale);
let df = new Intl.DateTimeFormat(locale,{year:'numeric',month:'2-digit',day:'2-digit'});
let dtf = new Intl.DateTimeFormat(locale,{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
const I18N = {
  'Übersicht':'Overview','Aktivität':'Activity','Autoren':'Contributors','Netzwerk':'Network','Netzwerkanalyse':'Network analysis','Referenzdistanz':'Reference distance','Code & Hotspots':'Code & hotspots','Datenqualität':'Data quality','Drucken':'Print','Darstellung':'Theme','Zuletzt bearbeitet':'Last updated','Beliebiger Zeitpunkt':'Any time','letzter Tag':'last day','letzte 7 Tage':'last 7 days','letzte 30 Tage':'last 30 days','letzte 180 Tage':'last 180 days','letzte 365 Tage':'last 365 days','letzte 2 Jahre':'last 2 years','Branch (HEAD/Standard)':'Branch (HEAD/default)','Beliebiger Branch':'Any branch','Programmiersprache':'Programming language','Dateityp':'File type','Filter zurücksetzen':'Clear filters','Kommentar-Dichte':'Comment density','Codezeilen':'Code lines','Kommentarzeilen':'Comment lines','HEAD-Dateien':'HEAD files','Top-Repositories':'Top repositories','Top-Autoren':'Top contributors','Repository-Matrix':'Repository matrix','Commits':'Commits','Repository':'Repository','Sprache':'Language','Dateien':'Files','Größe':'Size','Lizenz':'License','Datenqualität & Methodik':'Data quality & methodology','Releases & Tags':'Releases & tags','Keine Daten vorhanden.':'No data available.','Tabelle filtern':'Filter table','Tabelle durchsuchen …':'Search table …','Klick filtert Repository':'Click filters repository','Gefilterte Gesamtsummen':'Filtered totals','Sprachen im aktuellen HEAD':'Languages in current HEAD','Dateitypen im aktuellen HEAD':'File types in current HEAD','Kommentar-Dichte nach Sprache':'Comment density by language'
};
const reverseI18N = Object.fromEntries(Object.entries(I18N).map(([de,en])=>[en,de]));
function applyI18n(language){
  const dictionary=language==='en'?I18N:reverseI18N;
  document.documentElement.lang=language;
  locale=language==='en'?'en-US':'de-DE';nf=new Intl.NumberFormat(locale);df=new Intl.DateTimeFormat(locale,{year:'numeric',month:'2-digit',day:'2-digit'});dtf=new Intl.DateTimeFormat(locale,{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let node;while(node=walker.nextNode()){const clean=node.nodeValue.trim();if(dictionary[clean])node.nodeValue=node.nodeValue.replace(clean,dictionary[clean]);}
}
const esc = value => String(value ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num = value => value === null || value === undefined ? '–' : nf.format(Number(value));
const pct = value => value === null || value === undefined || Number.isNaN(Number(value)) ? '–' : (Number(value)*100).toLocaleString('de-DE',{maximumFractionDigits:1})+' %';
const date = value => { if(!value) return '–'; const d=new Date(value); return Number.isNaN(d.valueOf()) ? esc(value) : df.format(d); };
const datetime = value => { if(!value) return '–'; const d=new Date(value); return Number.isNaN(d.valueOf()) ? esc(value) : dtf.format(d); };
const bytes = value => { if(value===null||value===undefined) return '–'; let n=Number(value), u=['B','KiB','MiB','GiB','TiB'],i=0; while(n>=1024&&i<u.length-1){n/=1024;i++;} return n.toLocaleString('de-DE',{maximumFractionDigits:i?1:0})+' '+u[i]; };
const signedPct = value => value===null||value===undefined ? 'keine Vergleichsbasis' : ((value>0?'+':'')+(value*100).toLocaleString('de-DE',{maximumFractionDigits:1})+' %');
const cellValue = value => Array.isArray(value) ? value.join(', ') : (typeof value==='object'&&value!==null ? JSON.stringify(value) : value);
const empty = text => `<div class="empty">${esc(text)}</div>`;
const pageHead = (title,description) => `<div class="page-head"><div><h2>${esc(title)}</h2><p>${esc(description)}</p></div></div>`;
const kpi = (label,value,detail='') => `<div class="card kpi"><div class="label">${esc(label)}</div><div class="value">${value}</div><div class="detail">${detail}</div></div>`;
const stat = (label,value) => `<div class="stat"><strong>${value}</strong><span>${esc(label)}</span></div>`;
const heatLevel = (value,max) => value<=0?0:Math.max(1,Math.min(4,Math.ceil(value/max*4)));
function crossFilterAttrs(kind,value,values=[]){
  if(!kind)return '';
  const list=kind==='repositorySet'?` data-values="${esc(JSON.stringify(values||[]))}"`:'';
  return ` data-crossfilter="${esc(kind)}" data-value="${esc(value??'')}"${list}`;
}

function barList(rows,labelKey,valueKey,limit=12,formatter=num,filterKind=''){
  if(!rows || !rows.length) return empty('Keine Daten vorhanden.');
  const items=rows.slice(0,limit), max=Math.max(...items.map(r=>Number(r[valueKey]||0)),1);
  return `<div class="bar-list">${items.map(r=>{const attrs=crossFilterAttrs(filterKind,cellValue(r[labelKey]),r.repository_names||[]);return `<button type="button" class="bar-row ${filterKind?'filterable':''}"${attrs} title="${esc(cellValue(r[labelKey]))}: ${esc(formatter(r[valueKey]))}${filterKind?' · Klick filtert, Shift/Ctrl/Cmd kombiniert':''}"><span class="bar-label">${esc(cellValue(r[labelKey]))}</span><span class="bar-track"><span class="bar-fill" style="width:${Math.max(0,Number(r[valueKey]||0))/max*100}%"></span></span><span class="bar-value">${formatter(r[valueKey])}</span></button>`;}).join('')}</div>`;
}

function lineChart(rows,xKey,yKey){
  if(!rows || !rows.length) return empty('Keine Zeitreihe vorhanden.');
  const width=920,height=260,p={l:48,r:18,t:18,b:36};
  const values=rows.map(r=>Number(r[yKey]||0)), max=Math.max(...values,1), usableW=width-p.l-p.r, usableH=height-p.t-p.b;
  const points=values.map((v,i)=>[p.l+(rows.length===1?usableW/2:i/(rows.length-1)*usableW),p.t+usableH-(v/max*usableH)]);
  const path=points.map((q,i)=>(i?'L':'M')+q[0].toFixed(1)+' '+q[1].toFixed(1)).join(' ');
  const area=path+` L ${points[points.length-1][0]} ${p.t+usableH} L ${points[0][0]} ${p.t+usableH} Z`;
  const ticks=[0,.25,.5,.75,1].map(f=>{const y=p.t+usableH-f*usableH; return `<line class="grid-line" x1="${p.l}" x2="${width-p.r}" y1="${y}" y2="${y}"/><text class="axis-label" x="${p.l-7}" y="${y+4}" text-anchor="end">${num(Math.round(max*f))}</text>`}).join('');
  const step=Math.max(1,Math.ceil(rows.length/8));
  const labels=rows.map((r,i)=>i%step===0||i===rows.length-1?`<text class="axis-label" x="${points[i][0]}" y="${height-8}" text-anchor="middle">${esc(String(r[xKey]).slice(0,7))}</text>`:'').join('');
  const dots=points.map((q,i)=>{const row=rows[i],names=row.repository_names||[],attrs=names.length?crossFilterAttrs('repositorySet','',names):crossFilterAttrs('recent',daysAgo(row[xKey]));return `<circle class="dot"${attrs} cx="${q[0]}" cy="${q[1]}" r="4" tabindex="0" role="button" aria-label="${esc(rLabel(row,xKey))}: ${num(values[i])}. Repositories filtern."><title>${esc(rLabel(row,xKey))}: ${num(values[i])}. Klick filtert Repositories.</title></circle>`;}).join('');
  return `<div class="chart"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Zeitreihe">${ticks}<path class="area" d="${area}"/><path class="line" d="${path}"/>${dots}${labels}</svg></div>`;
}
function rLabel(row,key){return row[key]??'';}
function daysAgo(value){const time=new Date(value).valueOf();return Number.isNaN(time)?'':Math.max(1,Math.ceil((Date.now()-time)/86400000));}

function heatmap(cells){
  if(!cells || !cells.length) return empty('Keine Aktivitätsdaten vorhanden.');
  const max=Math.max(...cells.map(c=>Number(c.commits||0)),1), by=new Map(cells.map(c=>[`${c.weekday}-${c.hour}`,c]));
  let html='<div class="heat-wrap"><div class="heat-grid"><div></div>';
  for(let h=0;h<24;h++) html+=`<div class="heat-label">${String(h).padStart(2,'0')}</div>`;
  for(let d=0;d<7;d++){
    const sample=by.get(`${d}-0`); html+=`<div class="heat-label" style="text-align:left">${esc(sample?.weekday_label||d)}</div>`;
    for(let h=0;h<24;h++){const c=by.get(`${d}-${h}`)||{commits:0,repository_names:[]}; const lv=heatLevel(Number(c.commits),max), attrs=c.repository_names?.length?crossFilterAttrs('repositorySet','',c.repository_names):''; html+=`<button type="button" class="heat-cell"${attrs} style="background:var(--heat-${lv})" title="${esc(sample?.weekday_label||d)}, ${h}:00: ${num(c.commits)} Commits${attrs?' · Klick filtert Repositories':''}" aria-label="${esc(sample?.weekday_label||d)}, ${h}:00: ${num(c.commits)} Commits"></button>`;}
  }
  return html+'</div></div>'+legend();
}
function legend(){return '<div class="legend"><span>weniger</span>'+[0,1,2,3,4].map(i=>`<i style="background:var(--heat-${i})"></i>`).join('')+'<span>mehr</span></div>';}
const calendarMetrics={commits:'Commits',insertions:'Additionen',deletions:'Deletionen',churn:'Churn',repositories:'Repositories',authors:'Autor:innen'};
function calendarValue(row,metric){return metric==='churn'?Number(row.insertions||0)+Number(row.deletions||0):Number(row[metric]||0);}
function calendar(rows,metric='commits'){
  if(!rows||!rows.length) return empty('Keine Kalenderdaten vorhanden.');
  const label=calendarMetrics[metric]||calendarMetrics.commits, max=Math.max(...rows.map(r=>calendarValue(r,metric)),1);
  const cells=rows.map(r=>{const value=calendarValue(r,metric),attrs=(r.repository_names||[]).length?crossFilterAttrs('repositorySet','',r.repository_names):crossFilterAttrs('recent',daysAgo(r.date));return `<button type="button" class="calendar-cell"${attrs} style="background:var(--heat-${heatLevel(value,max)})" title="${date(r.date)}: ${num(value)} ${esc(label)}. Klick filtert Repositories." aria-label="${date(r.date)}: ${num(value)} ${esc(label)}"></button>`;}).join('');
  return `<div class="calendar" aria-label="Aktivitätskalender: ${esc(label)}">${cells}</div>${legend()}`;
}

let tableCounter=0;
function dataTable(rows,columns,options={}){
  if(!rows||!rows.length) return empty(options.empty||'Keine Daten vorhanden.');
  const id='tbl-'+(++tableCounter), limit=options.limit||rows.length;
  const head=columns.map((c,i)=>`<th scope="col" class="${c.num?'num':''}" data-index="${i}" tabindex="0" role="button" aria-label="${esc(c.label)} sortieren">${esc(c.label)} <span class="sort-ind">↕</span></th>`).join('');
  return `<div class="table-tools"><input class="search" aria-label="Tabelle filtern" placeholder="Tabelle durchsuchen …" data-table="${id}"><span class="muted">${num(Math.min(rows.length,limit))} von ${num(rows.length)}</span></div><div class="table-wrap"><table id="${id}"><thead><tr>${head}</tr></thead><tbody>${rows.slice(0,limit).map(r=>rowHtml(r,columns)).join('')}</tbody></table></div>`;
}
function rowHtml(row,columns){return `<tr>${columns.map(c=>{let raw=c.get?c.get(row):row[c.key], shown=c.format?c.format(raw,row):esc(cellValue(raw??'')); if(c.crossfilter){const values=c.values?c.values(row):(row.repository_names||[]);shown=`<button type="button" class="table-filter"${crossFilterAttrs(c.crossfilter,raw,values)}>${shown}</button>`;} return `<td class="${c.num?'num':''}" data-sort="${esc(raw??'')}">${shown}</td>`}).join('')}</tr>`;}
function activateTables(){
  document.querySelectorAll('.search[data-table]').forEach(input=>{if(input.dataset.bound)return;input.dataset.bound='1';input.addEventListener('input',()=>{const q=input.value.toLocaleLowerCase('de'); document.querySelectorAll(`#${input.dataset.table} tbody tr`).forEach(tr=>tr.hidden=!tr.textContent.toLocaleLowerCase('de').includes(q));});});
  document.querySelectorAll('th[data-index]').forEach(th=>{if(th.dataset.bound)return;th.dataset.bound='1';const sort=()=>{const table=th.closest('table'),body=table.tBodies[0],index=Number(th.dataset.index),asc=th.dataset.order!=='asc'; [...body.rows].sort((a,b)=>compare(a.cells[index].dataset.sort,b.cells[index].dataset.sort,asc)).forEach(row=>body.appendChild(row)); table.querySelectorAll('th[data-index]').forEach(other=>{if(other===th)return;other.dataset.order='';other.removeAttribute('aria-sort');const otherInd=other.querySelector('.sort-ind');if(otherInd)otherInd.textContent='↕';}); th.dataset.order=asc?'asc':'desc';th.setAttribute('aria-sort',asc?'ascending':'descending');const ind=th.querySelector('.sort-ind');if(ind)ind.textContent=asc?'↑':'↓';};th.addEventListener('click',sort);th.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();sort();}});});
  document.querySelectorAll('[data-crossfilter]').forEach(node=>{if(node.dataset.bound)return;node.dataset.bound='1';const filter=event=>{const kind=node.dataset.crossfilter;if(kind)applyCrossFilter(kind,node.dataset.value,event,node.dataset.values);};node.addEventListener('click',filter);node.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();filter(event);}});});
}
function compare(a,b,asc){const na=Number(a),nb=Number(b); let result=(!Number.isNaN(na)&&!Number.isNaN(nb)&&a!==''&&b!=='')?na-nb:String(a).localeCompare(String(b),'de',{numeric:true,sensitivity:'base'}); return asc?result:-result;}

const filters={repositories:new Set(),languages:new Set(),fileTypes:new Set(),recentDays:'',branch:''};
const selectedValues=select=>new Set([...select.selectedOptions].map(option=>option.value).filter(Boolean));
function selectedMatch(values, candidate){return !values.size||values.has(candidate);}
function recentMatch(repository){if(!filters.recentDays)return true; if(!repository.last_commit)return false; return Date.now()-new Date(repository.last_commit).valueOf()<=Number(filters.recentDays)*86400000;}
function branchMatch(repository){return !filters.branch||repository.head_branch===filters.branch||repository.default_branch===filters.branch;}
function filteredRepositories(){return D.repositories.filter(r=>selectedMatch(filters.repositories,r.name)&&(!filters.languages.size||(r.languages||[]).some(l=>filters.languages.has(l.language)))&&(!filters.fileTypes.size||(r.file_types||[]).some(t=>filters.fileTypes.has(t.file_type)))&&recentMatch(r)&&branchMatch(r));}
function filteredSummary(rows){
  const total=key=>rows.reduce((sum,row)=>sum+Number(row[key]||0),0), statuses={active:0,quiet:0,dormant:0,empty:0};
  rows.forEach(r=>statuses[r.activity_status]=(statuses[r.activity_status]||0)+1);
  const comments=total('comment_lines'), code=total('code_lines');
  return {...D.summary,repositories:rows.length,commits:total('commits'),active_repositories:statuses.active,quiet_repositories:statuses.quiet,dormant_repositories:statuses.dormant,empty_repositories:statuses.empty,additions:total('insertions'),deletions:total('deletions'),churn:total('churn'),tree_files:total('tree_files'),tree_bytes:total('tree_bytes'),code_lines:code,comment_lines:comments,comment_density:code+comments?comments/(code+comments):null};
}
function filteredLanguages(rows){const by=new Map(); rows.forEach(repo=>(repo.languages||[]).forEach(l=>{const old=by.get(l.language)||{language:l.language,files:0,bytes:0,code_lines:0,comment_lines:0,blank_lines:0,repositories:0,comment_types:{}}; old.files+=Number(l.files||0); old.bytes+=Number(l.bytes||0); old.code_lines+=Number(l.code_lines||0); old.comment_lines+=Number(l.comment_lines||0); old.blank_lines+=Number(l.blank_lines||0); old.repositories++; Object.entries(l.comment_types||{}).forEach(([kind,value])=>old.comment_types[kind]=(old.comment_types[kind]||0)+Number(value||0)); by.set(l.language,old);})); return [...by.values()].map(x=>({...x,comment_density:x.code_lines+x.comment_lines?x.comment_lines/(x.code_lines+x.comment_lines):null})).sort((a,b)=>b.bytes-a.bytes||a.language.localeCompare(b.language,'de'));}
function filteredFileTypes(rows){const by=new Map(); rows.forEach(repo=>(repo.file_types||[]).forEach(t=>{const old=by.get(t.file_type)||{file_type:t.file_type,files:0,bytes:0,repositories:0};old.files+=Number(t.files||0);old.bytes+=Number(t.bytes||0);old.repositories++;by.set(t.file_type,old);}));return [...by.values()].sort((a,b)=>b.bytes-a.bytes||a.file_type.localeCompare(b.file_type,'de'));}
function refreshDashboard(){const rows=filteredRepositories(); document.getElementById('filter-result').textContent=`${num(rows.length)} von ${num(D.repositories.length)} Repositories · Klick auf Visuals filtert, Shift/Ctrl/Cmd kombiniert`; renderOverview(); renderRepositories(); renderCode(); activateTables();setupCalendarMetric();applyI18n(document.getElementById('language-select').value);}
function setupCalendarMetric(){const select=document.getElementById('calendar-metric'),target=document.getElementById('calendar-content');if(!select||!target)return;select.addEventListener('change',()=>{target.innerHTML=calendar(D.activity.calendar_365,select.value);activateTables();});}
function syncSelect(select, values){[...select.options].forEach(option=>option.selected=values.has(option.value));}
function applyCrossFilter(kind,value,event,serializedValues=''){
  const map={repository:['repositories','repo-filter'],language:['languages','language-filter'],fileType:['fileTypes','file-type-filter']};
  if(kind==='repositorySet'){
    let group=[];try{group=JSON.parse(serializedValues||'[]');}catch(_){group=[];} group=group.filter(Boolean);
    if(!group.length)return; const values=filters.repositories,additive=event?.shiftKey||event?.ctrlKey||event?.metaKey,allSelected=group.every(item=>values.has(item));
    if(!additive)values.clear(); if(additive&&allSelected)group.forEach(item=>values.delete(item));else group.forEach(item=>values.add(item));
    syncSelect(document.getElementById('repo-filter'),values);refreshDashboard();return;
  }
  if(kind==='recent'){filters.recentDays=String(value);const select=document.getElementById('recent-filter');if(value&&!select.querySelector(`option[value="${String(value)}"]`)){const option=document.createElement('option');option.value=String(value);option.textContent=`letzte ${value} Tage`;select.append(option);}select.value=String(value);refreshDashboard();return;}
  const target=map[kind]; if(!target)return; const values=filters[target[0]], additive=event?.shiftKey||event?.ctrlKey||event?.metaKey;
  if(!additive)values.clear(); if(values.has(value)&&additive)values.delete(value); else values.add(value);
  syncSelect(document.getElementById(target[1]),values); refreshDashboard();
}
function setupFilters(){
  const repo=document.getElementById('repo-filter'), language=document.getElementById('language-filter'), type=document.getElementById('file-type-filter'), recent=document.getElementById('recent-filter'), branch=document.getElementById('branch-filter');
  repo.innerHTML=D.repositories.map(r=>`<option value="${esc(r.name)}">${esc(r.name)}</option>`).join('');
  language.innerHTML=[...new Set(D.repositories.flatMap(r=>(r.languages||[]).map(l=>l.language)))].sort((a,b)=>a.localeCompare(b,'de')).map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');
  type.innerHTML=[...new Set(D.repositories.flatMap(r=>(r.file_types||[]).map(t=>t.file_type)))].sort((a,b)=>a.localeCompare(b,'de')).map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');
  const update=()=>{filters.repositories=selectedValues(repo);filters.languages=selectedValues(language);filters.fileTypes=selectedValues(type);filters.recentDays=recent.value;filters.branch=branch.value;refreshDashboard();};
  repo.addEventListener('change',update); language.addEventListener('change',update); type.addEventListener('change',update); recent.addEventListener('change',update); branch.addEventListener('change',update); document.getElementById('clear-filters').addEventListener('click',()=>{filters.repositories.clear();filters.languages.clear();filters.fileTypes.clear();filters.recentDays='';filters.branch='';syncSelect(repo,filters.repositories);syncSelect(language,filters.languages);syncSelect(type,filters.fileTypes);recent.value='';branch.value='';refreshDashboard();}); refreshDashboard();
}

function renderOverview(){
  const rows=filteredRepositories(),s=filteredSummary(rows),a=D.activity,i=D.insights,q=D.quality;
  const insights=[
    ['Stärkster Wochentag',i.top_weekday?`${i.top_weekday.weekday} · ${num(i.top_weekday.commits)}`:'–'],
    ['Stärkste Stunde',i.top_hour?`${String(i.top_hour.hour).padStart(2,'0')}:00 · ${num(i.top_hour.commits)}`:'–'],
    ['Top-Autor',i.top_author?`${i.top_author.name} · ${num(i.top_author.commits)}`:'–'],
    ['Top-Repository',i.top_repository?`${i.top_repository.name} · ${num(i.top_repository.commits)}`:'–'],
    ['Hauptsprache im HEAD',i.top_tree_language?`${i.top_tree_language.language} · ${bytes(i.top_tree_language.bytes)}`:'–'],
    ['Stärkster Monat',i.peak_month?`${i.peak_month.key} · ${num(i.peak_month.commits)}`:'–']
  ];
  document.getElementById('page-overview').innerHTML=pageHead('Übersicht','Portfolio-Kennzahlen, Trends und auffällige Muster aus der ausgewählten Git-Historie.')+
  `<div class="grid kpis">${kpi('Repositories',num(s.repositories),`${num(s.active_repositories)} aktiv · ${num(s.dormant_repositories)} inaktiv`)}${kpi('Commits',num(s.commits),'für gefilterte Repositories')}${kpi('Code-Churn',num(s.churn),`+${num(s.additions)} / −${num(s.deletions)}`)}${kpi('Kommentar-Dichte',pct(s.comment_density),`${num(s.comment_lines)} Kommentarzeilen`)}${kpi('Codezeilen',num(s.code_lines),'HEAD, ohne Leerzeilen')}${kpi('HEAD-Dateien',num(s.tree_files),bytes(s.tree_bytes))}</div>`+
  `<div class="grid grid-2"><div class="card"><h3>Monatliche Aktivität</h3><div class="sub">Commits über die gesamte analysierte Zeitspanne</div>${lineChart(a.monthly.slice(-Math.max(1,Number(D.meta?.report?.timeline_months||60))),'key','commits')}</div><div class="card"><h3>Kernaussagen</h3><div class="sub">Deskriptive Werte, keine Leistungsbewertung</div><div class="insight-list">${insights.map(x=>`<div class="insight"><span>${esc(x[0])}</span><strong>${esc(x[1])}</strong></div>`).join('')}</div></div></div>`+
  `<div class="grid grid-3 mt"><div class="card"><h3>Top-Repositories</h3><div class="sub">Nach Commit-Anzahl</div>${barList(rows,'name','commits',10,num,'repository')}</div><div class="card"><h3>Top-Autoren</h3><div class="sub">Nach Commit-Anzahl</div>${barList(D.contributors.rows,'name','commits',10,num,'repositorySet')}</div><div class="card"><h3>Aktivitätsstatus</h3><div class="sub">Grenzen sind konfigurierbar</div><div class="stat-row">${stat('Aktiv',num(s.active_repositories))}${stat('Ruhig',num(s.quiet_repositories))}${stat('Dormant',num(s.dormant_repositories))}${stat('Leer',num(s.empty_repositories))}</div></div></div>`+
  `<div class="grid grid-2 mt"><div class="card"><h3>Letzte 365 Tage</h3><div class="sub">Jeder Block entspricht einem Kalendertag · <label>Metrik <select id="calendar-metric"><option value="commits">Commits</option><option value="insertions">Additionen</option><option value="deletions">Deletionen</option><option value="churn">Churn</option><option value="repositories">Repositories</option><option value="authors">Autor:innen</option></select></label></div><div id="calendar-content">${calendar(a.calendar_365)}</div></div><div class="card"><h3>Datenhinweise</h3><div class="sub">Qualität und Reichweite der Auswertung</div>${q.warnings.length?q.warnings.map(w=>`<div class="notice">${esc(w)}</div>`).join(''):'<div class="notice good">Keine allgemeinen Datenwarnungen.</div>'}</div></div>`;
}

function renderActivity(){
  const a=D.activity,s=D.summary;
  const recent=[30,90,365].map(n=>a.recent[String(n)]||{days:n,current:0,previous:0,delta:null});
  document.getElementById('page-activity').innerHTML=pageHead('Aktivität','Zeitliche Verteilung, Arbeitsmuster, Serien, Lücken und Vergleichszeiträume.')+
  `<div class="grid kpis">${recent.map(r=>kpi(`${r.days} Tage`,num(r.current),`${signedPct(r.delta)} ggü. Vorperiode`)).join('')}${kpi('Ø pro aktivem Tag',s.average_commits_per_active_day===null?'–':Number(s.average_commits_per_active_day).toLocaleString('de-DE',{maximumFractionDigits:2}),`Median ${num(a.median_commits_per_active_day)}`)}${kpi('Wochenendanteil',pct(s.weekend_share),'gemäß Arbeitstagen')}${kpi('Außerhalb Arbeitszeit',pct(s.outside_work_time_share),'gemäß Konfiguration')}</div>`+
  `<div class="grid grid-2"><div class="card"><h3>Commits nach Wochentag</h3><div class="sub">Zeitstempel: ${esc(D.meta.history.activity_timestamp||'author')}</div>${barList(a.weekdays,'weekday','commits',7,num,'repositorySet')}</div><div class="card"><h3>Commits nach Stunde</h3><div class="sub">Stunde in Analyse-Zeitzone</div>${barList(a.hours.map(r=>({...r,label:String(r.hour).padStart(2,'0')+':00'})),'label','commits',24,num,'repositorySet')}</div></div>`+
  `<div class="card mt"><h3>Wochentag × Uhrzeit</h3><div class="sub">Dunklere Felder bedeuten mehr Commits</div>${heatmap(a.weekday_hour_heatmap)}</div>`+
  `<div class="grid grid-2 mt"><div class="card"><h3>Monatlicher Verlauf</h3><div class="sub">Fehlende Monate werden als null dargestellt</div>${lineChart(a.monthly,'key','commits')}</div><div class="card"><h3>Serien und Lücken</h3><div class="sub">Auf Basis lokaler Aktivitätstage</div><div class="stat-row">${stat('Längste Serie',`${num(a.longest_streak.days)} Tage`)}${stat('Serienbeginn',date(a.longest_streak.start))}${stat('Serienende',date(a.longest_streak.end))}${stat('Längste Lücke',`${num(a.longest_gap.days_without_commits)} Tage`)}${stat('Nach',date(a.longest_gap.after))}${stat('Vor',date(a.longest_gap.before))}</div></div></div>`+
  `<div class="grid grid-2 mt"><div class="card"><h3>Aktivste Kalendertage</h3>${dataTable(a.busiest_days,[{key:'date',label:'Datum',format:date,crossfilter:'repositorySet'},{key:'commits',label:'Commits',num:true,format:num},{key:'authors',label:'Autoren',num:true,format:num},{key:'repositories',label:'Repos',num:true,format:num},{key:'insertions',label:'+',num:true,format:num},{key:'deletions',label:'−',num:true,format:num}],{limit:25})}</div><div class="card"><h3>Jahresübersicht</h3>${dataTable(a.yearly,[{key:'year',label:'Jahr',crossfilter:'repositorySet'},{key:'commits',label:'Commits',num:true,format:num},{key:'authors',label:'Autoren',num:true,format:num},{key:'repositories',label:'Repos',num:true,format:num},{key:'insertions',label:'+',num:true,format:num},{key:'deletions',label:'−',num:true,format:num}])}</div></div>`;
}

function renderRepositories(){
  const rows=filteredRepositories(),s=filteredSummary(rows);
  const cols=[
    {key:'name',label:'Repository',crossfilter:'repository'},{key:'classification',label:'Freigabe'},{key:'activity_status',label:'Aktivität',format:v=>`<span class="badge ${esc(v)}">${esc(v)}</span>`},
    {key:'commits',label:'Commits',num:true,format:num},{key:'authors',label:'Autoren',num:true,format:num},
    {key:'active_days',label:'Aktive Tage',num:true,format:num},{key:'top_author',label:'Top-Autor'},
    {key:'top_author_share',label:'Top-Anteil',num:true,format:pct},{key:'bus_factor_50',label:'BF50',num:true,format:num},
    {key:'top_language',label:'Hauptsprache'},{key:'comment_density',label:'Kommentar-Dichte',num:true,format:pct},{key:'churn',label:'Churn',num:true,format:num},
    {key:'last_commit',label:'Letzter Commit',format:date},{key:'head_branch',label:'HEAD-Branch'},{key:'default_branch',label:'Standardbranch'},{key:'local_branches',label:'Branches',num:true,format:num},
    {key:'ci_systems',label:'CI',format:v=>esc(cellValue(v||[]))},{key:'licenses',label:'Lizenz',format:v=>esc(cellValue(v||[]))},{key:'tags',label:'Tags',num:true,format:num},{key:'status',label:'Datensatz',format:v=>`<span class="badge ${esc(v)}">${esc(v)}</span>`}
  ];
  document.getElementById('page-repositories').innerHTML=pageHead('Repositories','Vergleich aller gefundenen Repositories mit Aktivität, Konzentration, Sprache und Datenhinweisen.')+
  `<div class="grid grid-3"><div class="card"><h3>Commit-Verteilung</h3><div class="sub">Top 15 Repositories</div>${barList(rows,'name','commits',15,num,'repository')}</div><div class="card"><h3>Churn-Verteilung</h3><div class="sub">Additionen plus Deletionen</div>${barList([...rows].sort((a,b)=>b.churn-a.churn),'name','churn',15,num,'repository')}</div><div class="card"><h3>Repository-Bestand</h3><div class="sub">Gefilterte Gesamtsummen</div><div class="stat-row">${stat('HEAD-Dateien',num(s.tree_files))}${stat('HEAD-Größe',bytes(s.tree_bytes))}${stat('Codezeilen',num(s.code_lines))}${stat('Kommentarzeilen',num(s.comment_lines))}${stat('Kommentar-Dichte',pct(s.comment_density))}</div></div></div>`+
  `<div class="card mt"><h3>Repository-Matrix</h3><div class="sub">Spaltenköpfe sortieren; Suchfeld filtert sichtbare Zeilen</div>${dataTable(rows,cols,{limit:10000})}</div>`+
  (D.quality.repository_warnings.length?`<div class="card mt"><h3>Repository-Hinweise</h3>${D.quality.repository_warnings.map(r=>`<div class="notice"><strong>${esc(r.repository)}</strong><br>${r.warnings.map(esc).join('<br>')}</div>`).join('')}</div>`:'');
}

function renderContributors(){
  const c=D.contributors,s=D.summary;
  const cols=[
    {key:'name',label:'Autor',crossfilter:'repositorySet'},{key:'email',label:'E-Mail'},{key:'commits',label:'Commits',num:true,format:num},
    {key:'share',label:'Anteil',num:true,format:pct},{key:'repositories',label:'Repos',num:true,format:num},
    {key:'active_days',label:'Aktive Tage',num:true,format:num},{key:'merges',label:'Merges',num:true,format:num},
    {key:'insertions',label:'+',num:true,format:num},{key:'deletions',label:'−',num:true,format:num},
    {key:'churn',label:'Churn',num:true,format:num},{key:'first_commit',label:'Erster Commit',format:date},
    {key:'last_commit',label:'Letzter Commit',format:date},{key:'is_bot',label:'Bot',format:v=>v?'ja':'nein'}
  ];
  document.getElementById('page-contributors').innerHTML=pageHead('Autoren','Identitäten nach .mailmap und Aliasregeln; Konzentrationswerte sind rein deskriptiv.')+
  `<div class="grid kpis">${kpi('Autoren',num(s.authors),'im effektiven Datensatz')}${kpi('Top-Autor-Anteil',pct(s.top_author_share),'Anteil an Commits')}${kpi('Bus Factor 50',num(s.bus_factor_50),'Autoren für 50 %')}${kpi('Bus Factor 80',num(s.bus_factor_80),'Autoren für 80 %')}${kpi('Gini',s.author_gini===null?'–':Number(s.author_gini).toLocaleString('de-DE',{maximumFractionDigits:3}),'0 gleich · 1 konzentriert')}${kpi('HHI',s.author_hhi===null?'–':Number(s.author_hhi).toLocaleString('de-DE',{maximumFractionDigits:3}),'Summe quadrierter Anteile')}</div>`+
  `<div class="grid grid-2"><div class="card"><h3>Commit-Anteile</h3><div class="sub">Top 20 Autoren</div>${barList(c.rows,'name','commits',20,num,'repositorySet')}</div><div class="card"><h3>Churn nach Autor</h3><div class="sub">Top 20 nach Additionen plus Deletionen</div>${barList([...c.rows].sort((a,b)=>b.churn-a.churn),'name','churn',20,num,'repositorySet')}</div></div>`+
  `<div class="card mt"><h3>Autorenmatrix</h3>${dataTable(c.rows,cols,{limit:10000})}</div>`+
  `<div class="card mt"><h3>Mögliche Identitätsduplikate</h3><div class="sub">Hinweise für Aliasregeln; nicht automatisch zusammengeführt</div>${c.identity_hints.length?dataTable(c.identity_hints,[{key:'kind',label:'Typ'},{key:'name',label:'Name'},{key:'email',label:'E-Mail'},{key:'values',label:'Varianten'},{key:'commits',label:'Commits',num:true,format:num}],{limit:200}):empty('Keine offensichtlichen Identitätsvarianten gefunden oder Autoren wurden anonymisiert.')}</div>`;
}

function renderCollaboration(){
  const g=D.collaboration||{}, references=(g.reference_names||[]).join(', '), found=(g.references_found||[]).join(', ');
  if(!g.enabled){
    document.getElementById('page-collaboration').innerHTML='';
    return;
  }
  const path=row=>(row.path||[]).map((step,index)=>index?`${esc(step.via_repository)} → ${esc(step.author)}`:esc(step.author)).join(' → ')||'–';
  document.getElementById('page-collaboration').innerHTML=pageHead('Netzwerkanalyse','Optionale kürzeste Verbindungen zwischen Autoren über gemeinsam bearbeitete Repositories.')+
  `<div class="grid kpis">${kpi('Referenz',esc(found||references),found?'im Netzwerk gefunden':'nicht im Netzwerk gefunden')}${kpi('Autoren',num(g.authors),'in der Netzwerkanalyse')}${kpi('Erreichbar',num(g.connected_authors),'von der Referenz')}${kpi('Max. Distanz',num(g.max_distance),'innerhalb der Komponente')}${kpi('Ausgeschlossen',num(g.excluded_memberships),'Bots, Service-Accounts oder zu geringe Beiträge')}</div>`+
  `<div class="card"><h3>Referenzdistanz</h3><div class="sub">Jede Stufe verbindet zwei Autoren über ein gemeinsames Repository. Das ist technische Zusammenarbeit, kein Beleg persönlicher Bekanntschaft.</div>${dataTable(g.rows||[],[{key:'author',label:'Autor',crossfilter:'repositorySet'},{key:'distance',label:'Distanz',num:true,format:num},{key:'commits',label:'Commits',num:true,format:num},{key:'repositories',label:'Repos',num:true,format:num},{key:'path',label:'Verbindungsweg',get:row=>row,format:path,crossfilter:'repositorySet'}],{limit:500,empty:'Keine Autoren im Netzwerk.'})}</div>`+
  `<div class="card mt"><h3>Gemeinsame Commit-Beiträge</h3><div class="sub">Autorenpaare mit Beiträgen im selben Repository innerhalb des konfigurierten Zeitfensters; kein Nachweis persönlicher Zusammenarbeit.</div>${dataTable(g.direct_pairs||[],[{key:'author',label:'Autor',crossfilter:'repositorySet'},{key:'co_author',label:'Co-Autor',crossfilter:'repositorySet'},{key:'repository',label:'Repository',crossfilter:'repository'},{key:'commits',label:'Beiträge zusammen',num:true,format:num}],{limit:500,empty:'Keine zeitlich überlappenden Beiträge.'})}</div>`+
  `<div class="notice"><strong>Modell:</strong> mindestens ${num(g.model?.min_commits_per_author_repository)} Commits je Autor/Repository · maximal ${num(g.model?.max_contribution_gap_days)} Tage zwischen Beitragszeiträumen · Service-Accounts ${g.model?.exclude_service_accounts?'ausgeschlossen':'zugelassen'}.</div>`+
  (g.truncated?'<div class="notice">Die Anzeige ist begrenzt; die vollständige Distanz kann über den JSON-Export genutzt werden.</div>':'');
}

function renderCode(){
  const c=D.code,rows=filteredRepositories(),s=filteredSummary(rows),comments=filteredLanguages(rows),fileTypes=filteredFileTypes(rows);
  document.getElementById('page-code').innerHTML=pageHead('Code & Hotspots','Historischer Churn, aktueller HEAD-Bestand, Commit-Konventionen und häufig geänderte Dateien.')+
  `<div class="grid kpis">${kpi('Additionen',num(s.additions),'gefilterte Repositories')}${kpi('Deletionen',num(s.deletions),'gefilterte Repositories')}${kpi('Kommentar-Dichte',pct(s.comment_density),'Kommentar- zu Codezeilen')}${kpi('Kommentarzeilen',num(s.comment_lines),'HEAD, erkannte Dateien')}${kpi('Codezeilen',num(s.code_lines),'HEAD, ohne Leerzeilen')}${kpi('Churn p95',num(c.churn_per_non_merge_commit.p95),'portfolio-weit')}</div>`+
  `<div class="grid grid-3"><div class="card"><h3>Commit-Typen</h3><div class="sub">Heuristische Klassifikation des Betreffs</div>${barList(c.commit_types,'label','commits',20,num,'repositorySet')}</div><div class="card"><h3>Commit-Größen</h3><div class="sub">Churn pro Nicht-Merge-Commit</div>${barList(c.commit_sizes,'bucket','commits',20,num,'repositorySet')}</div><div class="card"><h3>Churn-Verteilung</h3><div class="sub">Nicht-Merge-Commits mit bekannten Stats</div><div class="stat-row">${stat('Mittel',num(c.churn_per_non_merge_commit.mean))}${stat('Median',num(c.churn_per_non_merge_commit.median))}${stat('p90',num(c.churn_per_non_merge_commit.p90))}${stat('p95',num(c.churn_per_non_merge_commit.p95))}${stat('Maximum',num(c.churn_per_non_merge_commit.max))}${stat('Stats bekannt',pct(c.stats_known_share))}</div></div></div>`+
  `<div class="grid grid-2 mt"><div class="card"><h3>Sprachen im aktuellen HEAD</h3><div class="sub">Gewichtung nach Blob-Größe</div>${barList(comments,'language','bytes',20,bytes,'language')}</div><div class="card"><h3>Kommentar-Dichte nach Sprache</h3><div class="sub">Kommentarzeilen / (Kommentar- + Codezeilen)</div>${dataTable(comments,[{key:'language',label:'Sprache',crossfilter:'language'},{key:'files',label:'Dateien',num:true,format:num},{key:'code_lines',label:'Codezeilen',num:true,format:num},{key:'comment_lines',label:'Kommentarzeilen',num:true,format:num},{key:'comment_density',label:'Dichte',num:true,format:pct},{key:'repositories',label:'Repos',num:true,format:num}],{limit:100})}</div></div>`+
  `<div class="grid grid-2 mt"><div class="card"><h3>Dateitypen im aktuellen HEAD</h3><div class="sub">Klick filtert Dateityp; Shift/Ctrl/Cmd kombiniert</div>${barList(fileTypes,'file_type','bytes',20,bytes,'fileType')}</div><div class="card"><h3>Dateityp-Matrix</h3>${dataTable(fileTypes,[{key:'file_type',label:'Dateityp',crossfilter:'fileType'},{key:'files',label:'Dateien',num:true,format:num},{key:'bytes',label:'Größe',num:true,format:bytes},{key:'repositories',label:'Repos',num:true,format:num}],{limit:100})}</div></div>`+
  `<div class="card mt"><h3>Erkannte Kommentararten</h3><div class="sub">Zeilenkommentare, Blockkommentare und Python-Dokumentationsstrings werden getrennt ausgewiesen.</div>${dataTable(comments.flatMap(x=>Object.entries(x.comment_types||{}).map(([kind,comment_lines])=>({language:x.language,kind,comment_lines}))),[{key:'language',label:'Sprache',crossfilter:'language'},{key:'kind',label:'Art'},{key:'comment_lines',label:'Kommentarzeilen',num:true,format:num}],{limit:200})}</div>`+
  `<div class="card mt"><h3>Datei-Hotspots</h3><div class="sub">Häufig geänderte Pfade; hohe Aktivität ist kein automatischer Qualitätsmangel</div>${dataTable(c.hot_files,[{key:'repository',label:'Repository',crossfilter:'repository'},{key:'path',label:'Pfad'},{key:'language',label:'Sprache'},{key:'touches',label:'Touches',num:true,format:num},{key:'authors',label:'Autoren',num:true,format:num},{key:'churn',label:'Churn',num:true,format:num},{key:'last_activity',label:'Letzte Aktivität',format:date}],{limit:500})}</div>`+
  `<div class="card mt"><h3>Commit-Nachrichten</h3><div class="sub">Nur verfügbar, wenn der Scan mit --store-subjects durchgeführt wurde.</div>${c.subjects_available?dataTable(c.recent_subjects,[{key:'activity_at',label:'Zeitpunkt',format:datetime},{key:'repository',label:'Repository',crossfilter:'repository'},{key:'author',label:'Autor'},{key:'subject',label:'Nachricht'},{key:'message_type',label:'Typ'},{key:'message_scope',label:'Scope'}],{limit:500,empty:'Keine gespeicherten Commit-Nachrichten.'}):empty('Commit-Nachrichten wurden nicht gespeichert. Für einen neuen Snapshot --store-subjects verwenden.')}</div>`+
  `<div class="grid grid-2 mt"><div class="card"><h3>Top-Verzeichnisse</h3>${dataTable(c.top_directories,[{key:'directory',label:'Verzeichnis',crossfilter:'repositorySet'},{key:'touches',label:'Touches',num:true,format:num},{key:'repositories',label:'Repos',num:true,format:num},{key:'churn',label:'Churn',num:true,format:num}],{limit:200})}</div><div class="card"><h3>Commit-Scopes</h3>${dataTable(c.top_scopes,[{key:'scope',label:'Scope',crossfilter:'repositorySet'},{key:'commits',label:'Commits',num:true,format:num}],{limit:100})}</div></div>`;
}

function renderReleases(){
  const r=D.releases,s=r.summary||{};
  document.getElementById('page-releases').innerHTML=pageHead('Releases & Tags','Git-Tags mit Creator-Datum; Tags sind nicht zwingend semantische Produkt-Releases.')+
  `<div class="grid kpis">${kpi('Tags',num(s.tags),'alle analysierten Repos')}${kpi('Datierte Tags',num(s.dated_tags),'mit Creator-Datum')}${kpi('Repos mit Tags',num(s.repositories),'')}${kpi('Erster Tag',date(s.first),'')}${kpi('Letzter Tag',date(s.last),'')}${kpi('Tag-Abdeckung',D.summary.repositories?pct(Number(s.repositories||0)/D.summary.repositories):'–','Repos mit mindestens einem Tag')}</div>`+
  `<div class="card"><h3>Tag-Liste</h3>${dataTable(r.rows,[{key:'repository',label:'Repository',crossfilter:'repository'},{key:'name',label:'Tag'},{key:'created_at',label:'Erstellt',format:datetime},{key:'object_hash',label:'Objekt',format:v=>`<span style="font-family:var(--mono)">${esc(String(v||'').slice(0,12))}</span>`}],{limit:500})}</div>`;
}

function renderQuality(){
  const q=D.quality,m=D.meta,h=m.history||{};
  const historyText=JSON.stringify(h,null,2), workText=JSON.stringify(m.work_time||{},null,2), privacyText=JSON.stringify(m.privacy||{},null,2), profileText=JSON.stringify(m.profile||{},null,2);
  document.getElementById('page-quality').innerHTML=pageHead('Datenqualität & Methodik','Grenzen, Scanfehler, Zeitzonen und genaue Einstellungen der Analyse.')+
  `<div class="grid grid-2"><div class="card"><h3>Allgemeine Hinweise</h3>${q.warnings.length?q.warnings.map(w=>`<div class="notice">${esc(w)}</div>`).join(''):'<div class="notice good">Keine allgemeinen Warnungen.</div>'}</div><div class="card"><h3>Letzter Lauf</h3><div class="stat-row">${stat('Status',esc(q.latest_run.status||'–'))}${stat('Gefunden',num(q.latest_run.repositories_found))}${stat('Neu gescannt',num(q.latest_run.repositories_scanned))}${stat('Cache',num(q.latest_run.repositories_cached))}${stat('Fehler',num(q.latest_run.repositories_failed))}${stat('Lauf-ID',num(q.latest_run.id))}</div></div></div>`+
  `<div class="grid grid-2 mt"><div class="card"><h3>Scanfehler und Discovery-Hinweise</h3>${q.errors.length?dataTable(q.errors,[{key:'path',label:'Pfad'},{key:'stage',label:'Phase'},{key:'message',label:'Meldung'},{key:'created_at',label:'Zeit',format:datetime}],{limit:1000}):empty('Keine protokollierten Fehler im letzten Lauf.')}</div><div class="card"><h3>Zeitzonen-Offsets</h3><div class="sub">Offset der für Aktivität verwendeten Zeitstempel</div>${dataTable(q.timezone_offsets.map(r=>({...r,label:(Number(r.offset_minutes)>=0?'+':'')+(Number(r.offset_minutes)/60).toLocaleString('de-DE')+' h'})),[{key:'label',label:'UTC-Offset'},{key:'commits',label:'Commits',num:true,format:num}])}</div></div>`+
  `<div class="grid grid-2 mt"><div class="card"><h3>Historienparameter</h3><div class="code">${esc(historyText)}</div></div><div class="card"><h3>Arbeitszeitmodell</h3><div class="code">${esc(workText)}</div></div><div class="card"><h3>Datenschutz</h3><div class="code">${esc(privacyText)}</div></div><div class="card"><h3>Öffentliches Profil</h3><div class="code">${esc(profileText)}</div></div></div>`+
  `<div class="card mt"><h3>Interpretationsgrenzen</h3><p>Commits, Churn und Aktivitätszeiten sind technische Messwerte. Sie sind keine valide Einzelpersonen-Leistungsbewertung. Merge-Strategien, Squashing, importierte Historien, Bots, Zeitzonen, Pair Programming, Monorepos und Repository-Spiegel können die Werte erheblich beeinflussen.</p><p>Der „Bus Factor“ in diesem Bericht bezeichnet lediglich, wie viele Autoren zusammen 50 beziehungsweise 80 Prozent der Commits erzeugt haben. Er misst weder Wissensverteilung noch tatsächliches Ausfallrisiko.</p><p>Sprachen im aktuellen HEAD werden anhand von Dateiendungen und Blob-Größen klassifiziert. Historische Sprachaktivität basiert auf Dateiänderungen. Generierte Dateien und vendorte Abhängigkeiten werden nicht automatisch inhaltlich erkannt.</p></div>`;
}

function setupNav(){
  document.querySelectorAll('[data-optional-page="collaboration"]').forEach(button=>{button.hidden=!(D.collaboration&&D.collaboration.enabled);});
  document.getElementById('page-collaboration').hidden=!(D.collaboration&&D.collaboration.enabled);
  document.querySelectorAll('.nav button').forEach(button=>button.addEventListener('click',()=>{
    document.querySelectorAll('.nav button').forEach(b=>{b.classList.toggle('active',b===button);if(b===button)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
    document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id===`page-${button.dataset.page}`));
    window.scrollTo({top:0,behavior:'smooth'});
  }));
}
function setupTheme(){
  const root=document.documentElement, button=document.getElementById('theme-button');
  let saved='auto'; try { saved=localStorage.getItem('gitanalytics-theme')||'auto'; } catch (_) {}
  root.dataset.theme=saved;
  button.addEventListener('click',()=>{const next={auto:'light',light:'dark',dark:'auto'}[root.dataset.theme||'auto']; root.dataset.theme=next; try { localStorage.setItem('gitanalytics-theme',next); } catch (_) {} button.textContent=`Darstellung: ${next}`;});
  button.textContent=`Darstellung: ${saved}`;
}
function setupLanguage(){
  const select=document.getElementById('language-select');let saved='de';try{saved=localStorage.getItem('gitanalytics-language')||'de';}catch(_){}select.value=saved;applyI18n(saved);select.addEventListener('change',()=>{try{localStorage.setItem('gitanalytics-language',select.value);}catch(_){}applyI18n(select.value);});
}
function init(){
  document.title=(D.meta.title||'GitAnalytics')+' – GitAnalytics';
  document.getElementById('report-title').textContent=D.meta.title||'GitAnalytics';
  document.getElementById('report-subtitle').textContent=`Erzeugt ${datetime(D.meta.generated_at)} · GitAnalytics ${D.meta.tool_version||''}`;
  document.getElementById('side-meta').innerHTML=`<strong>${num(D.summary.repositories)} Repositories</strong><br>${num(D.summary.commits)} Commits<br>${date(D.summary.first_commit)} – ${date(D.summary.last_commit)}`;
  renderActivity(); renderContributors(); renderCollaboration(); renderReleases(); renderQuality();
  setupNav(); setupTheme(); setupLanguage(); setupFilters(); activateTables();
}
init();
</script>
</body>
</html>
'''


def write_html(path: Path, report: dict[str, Any]) -> None:
    atomic_write_text(path, render_html(report))
