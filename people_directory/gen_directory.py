#!/usr/bin/env python3
"""Read people.json + org_categories.json + extra_data.json (next to this script)
and write ai-safety-people-directory.html — a self-contained, light-mode, tabbed
AI Safety Directory: People / Organizations / Papers / Conferences / Fellowships /
Datasets. Run parse_raw.py then parse_extra.py first.
"""
import json, os, re, collections, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
people = json.load(open(os.path.join(BASE, "people.json")))
orgcat = json.load(open(os.path.join(BASE, "org_categories.json")))
extra = json.load(open(os.path.join(BASE, "extra_data.json")))

for p in people:
    p["name"] = p.get("name", "").replace(" ... ", " ").replace("...", "").strip()
    if not p.get("category"):
        p["category"] = orgcat.get(p.get("org", ""), "Other")

# ---- cross-tab links (2026-07-04) --------------------------------------
# Precompute person<->paper matches (by normalized title, plus roster names
# found in the manifest authors field), person->conference and
# person->fellowship reverse lookups. The JS renders these as nav chips.
def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

papers = extra["papers"]
for pap in papers:
    # seed with parse_extra's header-scan author matches, then augment below
    pap["rp"] = list(pap.get("rp_seed") or [])
ptitle_norm = [(_norm(pap["title"]), pap) for pap in papers]
authors_lc = [((pap.get("authors") or "").lower(), pap) for pap in papers]

for person in people:
    person["ptab"] = []     # Papers-tab titles matching this person's papers
    for pp in person.get("papers") or []:
        t = _norm(pp.get("t") or "")
        if not t:
            continue
        for tn, pap in ptitle_norm:
            if tn and (t == tn or (len(t) > 20 and len(tn) > 20
                                   and (t in tn or tn in t))):
                if pap["title"] not in person["ptab"]:
                    person["ptab"].append(pap["title"])
                    if person["name"] not in pap["rp"]:
                        pap["rp"].append(person["name"])
                break
    nlc = person["name"].lower()
    person["inAuthors"] = any(nlc in a for a, _ in authors_lc if a)
    if person["inAuthors"]:
        for a, pap in authors_lc:
            if a and nlc in a and person["name"] not in pap["rp"]:
                pap["rp"].append(person["name"])

_confmap, _fellmap = {}, {}
for c in extra["conferences"]:
    for pe in c["people"]:
        _confmap.setdefault(pe["n"], []).append(c["name"])
for f in extra["fellowships"]:
    for pe in f["people"]:
        _fellmap.setdefault(pe["n"], []).append(f["name"])
for person in people:
    person["confs"] = _confmap.get(person["name"], [])
    person["fellows"] = _fellmap.get(person["name"], [])
# fellowship -> related conferences (union of its participants' conference
# appearances; order = first seen, i.e. roughly by participant prominence)
for f in extra["fellowships"]:
    seen = []
    for pe in f["people"]:
        for cn in _confmap.get(pe["n"], []):
            if cn not in seen:
                seen.append(cn)
    f["confs"] = seen
# -------------------------------------------------------------------------

# ---- tag vocabularies with counts (multi-select chips, 2026-07-04) ----
focus_counter = collections.Counter()
for p in people:
    for f in [x.strip() for x in p.get("focus", "").split(";") if x.strip()]:
        focus_counter[f] += 1
# Papers: tags (frontmatter ∪ wiki_concepts) + subcategory as a pseudo-tag so
# chips cover all 448 papers, not just the ~60 with frontmatter tags.
paper_tag_counter = collections.Counter()
for pap in papers:
    seen = set()
    for t in pap.get("tags") or []:
        if t not in seen:
            paper_tag_counter[t] += 1
            seen.add(t)
    sb = pap.get("sub")
    if sb and sb not in seen:
        paper_tag_counter[sb] += 1
conf_tag_counter = collections.Counter()
for c in extra["conferences"]:
    for t in c.get("focus") or []:
        conf_tag_counter[t] += 1
fellow_tag_counter = collections.Counter()
for f in extra["fellowships"]:
    for t in f.get("focus_areas") or []:
        fellow_tag_counter[t] += 1
ds_tag_counter = collections.Counter()
for ds in extra["datasets"]:
    for t in ds.get("tags") or []:
        ds_tag_counter[t] += 1
cats = sorted({p["category"] for p in people})

data = {
    "people": people, "categories": cats,
    "focusTags": focus_counter.most_common(),
    "paperTags": paper_tag_counter.most_common(),
    "confTags": conf_tag_counter.most_common(),
    "fellowTags": fellow_tag_counter.most_common(),
    "datasetTags": ds_tag_counter.most_common(),
    "count": len(people),
    "orgCount": len({p.get("org", "") for p in people if p.get("org")}),
    "snapshot": datetime.date.today().isoformat(),
    "papers": extra["papers"], "orgGroups": extra["orgGroups"], "orgs": extra["orgs"],
    "conferences": extra["conferences"], "fellowships": extra["fellowships"],
    "datasets": extra["datasets"], "notionFetched": extra.get("notionFetched", ""),
    "dsNames": [d["name"].lower() for d in extra["datasets"]],
}
# drop internal-only fields from the embedded payload (rp now holds the merged
# people links; pid was only needed for the chunk lookup in parse_extra)
for pap in extra["papers"]:
    pap.pop("rp_seed", None)
    pap.pop("pid", None)
DATA_JSON = json.dumps(data, ensure_ascii=False)

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Safety Directory</title>
<style>
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:#faf9f7;color:#1f1e1c;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;line-height:1.5}
.wrap{max-width:1080px;margin:0 auto;padding:20px 18px 60px}
h1{font-size:22px;font-weight:600;margin:0 0 4px}
.sub{font-size:13px;color:#6b6a66;margin:0 0 12px}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.tab{font-size:13px;font-weight:600;padding:7px 14px;border-radius:999px;border:.5px solid #cfcdc5;background:#fff;color:#54524d;cursor:pointer;user-select:none}
.tab:hover{border-color:#a7a49a}
.tab.active{background:#4a3fb0;color:#fff;border-color:#4a3fb0}
.tab .n{font-weight:400;opacity:.75;font-size:11.5px;margin-left:4px}
.controls{position:sticky;top:0;background:#faf9f7;padding:10px 0 12px;z-index:5;border-bottom:.5px solid #e5e3dd;margin-bottom:16px}
.searchrow{display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
input[type=text]{flex:1;min-width:180px;height:38px;padding:0 12px;border:.5px solid #cfcdc5;border-radius:8px;font-size:14px;background:#fff}
input[type=text]:focus{outline:none;border-color:#8a7fd6;box-shadow:0 0 0 3px #ece9fb}
select{height:34px;border:.5px solid #cfcdc5;border-radius:8px;font-size:13px;background:#fff;padding:0 8px;max-width:230px}
.count{font-size:13px;color:#6b6a66;white-space:nowrap}
.chips{display:flex;flex-wrap:wrap;gap:7px}
.chip{font-size:12.5px;padding:5px 11px;border-radius:999px;border:.5px solid #cfcdc5;background:#fff;color:#54524d;cursor:pointer;user-select:none}
.chip:hover{border-color:#a7a49a}
.chip.active{background:#efecfb;color:#4a3fb0;border-color:#c3bcee}
.chip .cn{opacity:.55;font-size:10.5px;margin-left:2px}
.chip.xp,.chip.mode{background:#f1efe8;font-weight:600}
.tag.tclick{cursor:pointer;border:.5px solid transparent}
.tag.tclick:hover{background:#e6e3f7;color:#4a3fb0;border-color:#c3bcee}
.tag.ton{background:#efecfb;color:#4a3fb0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
.list{display:flex;flex-direction:column;gap:10px}
.card{background:#fff;border:.5px solid #e5e3dd;border-radius:12px;padding:14px 16px;cursor:pointer;transition:border-color .12s}
.card:hover{border-color:#c3bcee}
.card.static{cursor:default}
.chead{display:flex;gap:11px;align-items:flex-start}
.av{width:40px;height:40px;border-radius:50%;background:#efecfb;color:#4a3fb0;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:13px;flex-shrink:0}
.nm{font-weight:600;font-size:15px;margin:0}
.orgline{font-size:12.5px;color:#6b6a66;margin:2px 0 0}
.newdot{display:inline-block;font-size:10px;font-weight:600;color:#0a7d54;background:#e2f5ec;border-radius:999px;padding:1px 7px;margin-left:6px;vertical-align:1px}
.cat{display:inline-block;font-size:11px;color:#7a5a12;background:#fbf0d9;border-radius:999px;padding:2px 9px;margin-top:8px}
.badge{display:inline-block;font-size:11px;border-radius:999px;padding:2px 9px;margin-right:5px}
.b-amber{color:#7a5a12;background:#fbf0d9}
.b-green{color:#0a7d54;background:#e2f5ec}
.b-purple{color:#4a3fb0;background:#efecfb}
.b-gray{color:#54524d;background:#f1efe8}
.tags{margin-top:8px;display:flex;flex-wrap:wrap;gap:5px}
.tag{font-size:11px;color:#54524d;background:#f1efe8;border-radius:999px;padding:2px 9px}
.pp{font-size:11.5px;color:#4a3fb0;background:#efecfb;border-radius:999px;padding:2px 9px;cursor:pointer;border:.5px solid transparent}
.pp:hover{border-color:#c3bcee}
.pp .r{color:#8a7fd6;font-size:10.5px}
.detail{display:none;margin-top:12px;padding-top:12px;border-top:.5px solid #eeece6}
.card.open .detail{display:block}
.drow{font-size:12.5px;margin:0 0 6px}
.dlab{color:#8a887f}
.empty{text-align:center;color:#8a887f;padding:40px;font-size:14px}
.links{margin-top:11px;display:flex;flex-wrap:wrap;gap:8px}
.lnk{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;text-decoration:none;color:#4a3fb0;background:#fff;border:1px solid #c3bcee;border-radius:8px;padding:6px 12px;transition:background .12s,border-color .12s}
.lnk:hover{background:#efecfb;border-color:#8a7fd6}
.lnk svg{width:13px;height:13px;fill:currentColor}
.foot{margin-top:22px;font-size:11.5px;color:#9a988f}
.ptitle{font-weight:600;font-size:14.5px;margin:0}
.ptitle a{color:#1f1e1c;text-decoration:none}
.ptitle a:hover{color:#4a3fb0;text-decoration:underline}
.pmeta{font-size:12.5px;color:#6b6a66;margin:3px 0 0}
</style>
</head>
<body>
<div class="wrap">
  <h1>AI Safety Directory</h1>
  <p class="sub" id="sub"></p>
  <div class="tabs" id="tabs"></div>
  <div id="pages"></div>
  <div class="foot" id="foot"></div>
</div>
<script>
var DATA = /*DATA*/;
var people = DATA.people;
var LS = "aisafety_dir_v3";
var state = {
  tab: "people",
  people: {q:"", cat:"all", focus:[], focusMode:"all", sort:"name"},
  orgs: {q:"", group:"all"},
  papers: {q:"", cat:"all", kind:"all", year:"all", sort:"date", tags:[], tagsMode:"all"},
  confs: {q:"", year:"all", type:"all", tags:[], tagsMode:"all"},
  fellows: {q:"", tags:[], tagsMode:"all"},
  datasets: {q:"", year:"all", tags:[], tagsMode:"all"}
};
try{var saved=JSON.parse(localStorage.getItem(LS)); if(saved){for(var k in saved){if(typeof saved[k]==="object"&&state[k])Object.assign(state[k],saved[k]);else state[k]=saved[k];}}}catch(e){}
["people","papers","confs","fellows","datasets"].forEach(function(k){var st=state[k];["focus","tags"].forEach(function(f){if(f in st&&!Array.isArray(st[f]))st[f]=[];});});
function persist(){try{localStorage.setItem(LS,JSON.stringify(state));}catch(e){}}
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function initials(n){var p=n.split(/\s+/).filter(Boolean);return ((p[0]||"")[0]||"")+((p[p.length-1]||"")[0]||"");}

document.getElementById("sub").textContent = DATA.count+" researchers · "+DATA.orgs.length+" orgs · "+DATA.papers.length+" papers · "+DATA.conferences.length+" conferences · "+DATA.fellowships.length+" fellowships · "+DATA.datasets.length+" datasets · snapshot "+DATA.snapshot;

var TABS=[["people","People",DATA.count],["orgs","Organizations",DATA.orgs.length],["papers","Papers",DATA.papers.length],["confs","Conferences",DATA.conferences.length],["fellows","Fellowships",DATA.fellowships.length],["datasets","Datasets",DATA.datasets.length]];
var tabsEl=document.getElementById("tabs");
tabsEl.innerHTML=TABS.map(function(t){return '<span class="tab" data-t="'+t[0]+'">'+t[1]+'<span class="n">'+t[2]+'</span></span>';}).join("");
tabsEl.onclick=function(e){var el=e.target.closest(".tab");if(!el)return;setTab(el.getAttribute("data-t"));};
function setTab(t){state.tab=t;persist();
  [].forEach.call(tabsEl.children,function(c){c.classList.toggle("active",c.getAttribute("data-t")===t);});
  [].forEach.call(document.getElementById("pages").children,function(pg){pg.style.display=pg.id==="pg-"+t?"":"none";});
  RENDER[t]();
}
function gotoPerson(name){
  state.people.q=name;state.people.cat="all";state.people.focus=[];
  var q=document.getElementById("q-people");if(q)q.value=name;
  var cs=document.getElementById("catsel");if(cs)cs.value="all";
  if(CHIPS.people)CHIPS.people.draw();
  setTab("people");
  window.scrollTo(0,0);
}
var DSSET={};DATA.dsNames.forEach(function(n){DSSET[n]=1;});
function gotoTabQ(tab,q){
  var st=state[tab];st.q=q;
  function rst(id){var e=document.getElementById(id);if(e)e.value="all";}
  if(tab==="papers"){st.cat="all";st.kind="all";st.year="all";rst("pcatsel");rst("pkindsel");rst("pyearsel");}
  if(tab==="confs"){st.year="all";st.type="all";rst("cyearsel");rst("ctypesel");}
  if(tab==="orgs"){st.group="all";rst("groupsel");}
  if(tab==="datasets"){st.year="all";rst("dyearsel");}
  if(st.tags){st.tags=[];}
  if(CHIPS[tab])CHIPS[tab].draw();
  persist();
  var inp=document.getElementById("q-"+tab);if(inp)inp.value=q;
  setTab(tab);window.scrollTo(0,0);
}

/* ---------- multi-select tag chips (2026-07-04) ----------
   makeChips(cid, vocab, tab, key) renders a chip row: "All" (clear), each tag
   with its count, an expander past LIMIT, and an ALL/ANY match-mode toggle
   when 2+ tags are selected. Card tags rendered via tagChipHtml() toggle the
   same state. */
var CHIPS={};
var CHIP_LIMIT=18;
function makeChips(cid,vocab,tab,key,render){
  var el=document.getElementById(cid);
  var expanded=false;
  function draw(){
    var a=state[tab][key];
    var vis=expanded?vocab:vocab.slice(0,CHIP_LIMIT);
    var h='<span class="chip'+(a.length?'':' active')+'" data-a="clear">All</span>';
    h+=vis.map(function(v){
      var on=a.indexOf(v[0])>=0;
      return '<span class="chip'+(on?' active':'')+'" data-t="'+esc(v[0])+'">'+esc(v[0])+' <span class="cn">'+v[1]+'</span></span>';
    }).join("");
    a.forEach(function(t){
      if(!vis.some(function(v){return v[0]===t;}))h+='<span class="chip active" data-t="'+esc(t)+'">'+esc(t)+'</span>';
    });
    if(vocab.length>CHIP_LIMIT)h+='<span class="chip xp" data-a="x">'+(expanded?"− fewer":"+"+(vocab.length-CHIP_LIMIT)+" more")+'</span>';
    if(a.length>1)h+='<span class="chip mode" data-a="m" title="ALL: match every selected tag · ANY: match at least one">match: '+(state[tab][key+"Mode"]==="any"?"ANY":"ALL")+'</span>';
    el.innerHTML=h;
  }
  el.onclick=function(e){
    var c=e.target.closest(".chip");if(!c)return;
    var act=c.getAttribute("data-a");
    if(act==="x"){expanded=!expanded;draw();return;}
    if(act==="clear"){state[tab][key]=[];}
    else if(act==="m"){var mk=key+"Mode";state[tab][mk]=state[tab][mk]==="any"?"all":"any";}
    else{var t=c.getAttribute("data-t"),a=state[tab][key],i=a.indexOf(t);if(i>=0)a.splice(i,1);else a.push(t);}
    persist();draw();render();
  };
  CHIPS[tab]={draw:draw};
  draw();
}
var TAB_TAGKEY={people:"focus",papers:"tags",confs:"tags",fellows:"tags",datasets:"tags"};
function toggleTag(tab,tag){
  var a=state[tab][TAB_TAGKEY[tab]],i=a.indexOf(tag);
  if(i>=0)a.splice(i,1);else a.push(tag);
  persist();if(CHIPS[tab])CHIPS[tab].draw();RENDER[tab]();
}
function tagChipHtml(tab,tag){
  var on=state[tab][TAB_TAGKEY[tab]].indexOf(tag)>=0;
  return '<span class="tag tclick'+(on?' ton':'')+'" title="Filter by this tag" '
    +'onclick="event.stopPropagation();toggleTag(\''+tab+'\',\''+esc(tag).replace(/'/g,"\\'")+'\')">'+esc(tag)+'</span>';
}
function tagsMatch(sel,mode,haveLc,extraHayLc){
  var f=function(t){t=t.toLowerCase();
    return haveLc.indexOf(t)>=0||(extraHayLc&&extraHayLc.indexOf(t)>=0);};
  return mode==="any"?sel.some(f):sel.every(f);
}
function navChip(label,tab,q,tip){
  return '<span class="pp" '+(tip?'title="'+esc(tip)+'" ':'')
    +'onclick="event.stopPropagation();gotoTabQ(\''+tab+'\',\''+esc(q.replace(/'/g,"\\'"))+'\')">'
    +esc(label)+' <span class="r">▸</span></span>';
}
function navChips(list,tab,tip,max){
  max=max||8;
  var h=list.slice(0,max).map(function(x){return navChip(x,tab,x,tip);}).join(" ");
  if(list.length>max)h+=' <span class="tag">+'+(list.length-max)+' more</span>';
  return h;
}
function peopleChips(list,max){
  max=max||30;
  var h=list.slice(0,max).map(function(pp){
    var n=typeof pp==="string"?pp:pp.n, r=typeof pp==="string"?"":(pp.r||pp.note||"");
    return '<span class="pp" onclick="event.stopPropagation();gotoPerson(\''+esc(n).replace(/'/g,"\\'")+'\')">'+esc(n)+(r?' <span class="r">· '+esc(r)+'</span>':'')+'</span>';
  }).join(" ");
  if(list.length>max)h+=' <span class="tag">+'+(list.length-max)+' more</span>';
  return h;
}

/* ---------- page scaffolding ---------- */
var pages=document.getElementById("pages");
pages.innerHTML=[
'<div id="pg-people">',
'  <div class="controls"><div class="searchrow">',
'    <input id="q-people" type="text" placeholder="Search name, org, focus, or notable work">',
'    <select id="catsel"></select>',
'    <select id="sortsel"><option value="name">Sort: name</option><option value="org">Sort: org</option><option value="cat">Sort: category</option></select>',
'    <span class="count" id="count-people"></span></div>',
'  <div class="chips" id="chips-people"></div></div>',
'  <div class="grid" id="grid-people"></div>',
'</div>',
'<div id="pg-orgs" style="display:none">',
'  <div class="controls"><div class="searchrow">',
'    <input id="q-orgs" type="text" placeholder="Search organizations">',
'    <select id="groupsel"></select>',
'    <span class="count" id="count-orgs"></span></div></div>',
'  <div class="grid" id="grid-orgs"></div>',
'</div>',
'<div id="pg-papers" style="display:none">',
'  <div class="controls"><div class="searchrow">',
'    <input id="q-papers" type="text" placeholder="Search title, author, or tag">',
'    <select id="pcatsel"></select>',
'    <select id="pkindsel"><option value="all">Papers + benchmarks</option><option value="paper">Papers only</option><option value="benchmark">Benchmarks only</option></select>',
'    <select id="pyearsel"></select>',
'    <select id="psortsel"><option value="date">Sort: newest</option><option value="title">Sort: title</option></select>',
'    <span class="count" id="count-papers"></span></div>',
'  <div class="chips" id="chips-papers"></div></div>',
'  <div class="list" id="list-papers"></div>',
'</div>',
'<div id="pg-confs" style="display:none">',
'  <div class="controls"><div class="searchrow">',
'    <input id="q-confs" type="text" placeholder="Search conferences, locations, or people">',
'    <select id="cyearsel"></select>',
'    <select id="ctypesel"></select>',
'    <span class="count" id="count-confs"></span></div>',
'  <div class="chips" id="chips-confs"></div></div>',
'  <div class="list" id="list-confs"></div>',
'</div>',
'<div id="pg-fellows" style="display:none">',
'  <div class="controls"><div class="searchrow">',
'    <input id="q-fellows" type="text" placeholder="Search programs or people">',
'    <span class="count" id="count-fellows"></span></div>',
'  <div class="chips" id="chips-fellows"></div></div>',
'  <div class="list" id="list-fellows"></div>',
'</div>',
'<div id="pg-datasets" style="display:none">',
'  <div class="controls"><div class="searchrow">',
'    <input id="q-datasets" type="text" placeholder="Search benchmarks / datasets or people">',
'    <select id="dyearsel"></select>',
'    <span class="count" id="count-datasets"></span></div>',
'  <div class="chips" id="chips-datasets"></div></div>',
'  <div class="grid" id="grid-datasets"></div>',
'</div>'].join("");

function wireSearch(id,st,render){var el=document.getElementById(id);el.value=st.q;el.oninput=function(){st.q=el.value;persist();render();};}

/* ---------- PEOPLE (original page, unchanged behaviour) ---------- */
var catsel=document.getElementById("catsel");
catsel.innerHTML='<option value="all">All categories</option>'+DATA.categories.map(function(c){return '<option value="'+esc(c)+'">'+esc(c)+'</option>';}).join("");
catsel.value=state.people.cat;
catsel.onchange=function(){state.people.cat=catsel.value;persist();renderPeople();};
var sortsel=document.getElementById("sortsel");
sortsel.value=state.people.sort;
sortsel.onchange=function(){state.people.sort=sortsel.value;persist();renderPeople();};
makeChips("chips-people",DATA.focusTags,"people","focus",function(){renderPeople();});
makeChips("chips-papers",DATA.paperTags,"papers","tags",function(){renderPapers();});
makeChips("chips-confs",DATA.confTags,"confs","tags",function(){renderConfs();});
makeChips("chips-fellows",DATA.fellowTags,"fellows","tags",function(){renderFellows();});
makeChips("chips-datasets",DATA.datasetTags,"datasets","tags",function(){renderDatasets();});
wireSearch("q-people",state.people,function(){renderPeople();});

function matchesPerson(p){
  var s=state.people;
  if(s.cat!=="all" && p.category!==s.cat) return false;
  if(s.focus.length){
    var have=(p.focus||"").split(";").map(function(x){return x.trim().toLowerCase();}).filter(Boolean);
    if(!tagsMatch(s.focus,s.focusMode,have)) return false;
  }
  if(s.q){
    var hay=(p.name+" "+p.org+" "+p.focus+" "+p.notable+" "+p.currentOrg+" "+p.tools+" "+p.benchmarks).toLowerCase();
    if(hay.indexOf(s.q.toLowerCase())<0) return false;
  }
  return true;
}
var ICON={
  web:'<svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 100 20 10 10 0 000-20zm6.9 6h-2.5a15.6 15.6 0 00-1.3-3.4A8 8 0 0118.9 8zM12 4c.8 1.1 1.4 2.5 1.8 4h-3.6c.4-1.5 1-2.9 1.8-4zM4.3 14a7.9 7.9 0 010-4h2.9a17.6 17.6 0 000 4H4.3zm.8 2h2.5c.3 1.2.8 2.4 1.3 3.4A8 8 0 015.1 16zm2.5-8H5.1a8 8 0 013.8-3.4C8.4 5.6 7.9 6.8 7.6 8zM12 20c-.8-1.1-1.4-2.5-1.8-4h3.6c-.4 1.5-1 2.9-1.8 4zm2.2-6H9.8a15.7 15.7 0 010-4h4.4a15.7 15.7 0 010 4zm.6 5.4c.5-1 1-2.2 1.3-3.4h2.5a8 8 0 01-3.8 3.4zM16.8 14a17.6 17.6 0 000-4h2.9a7.9 7.9 0 010 4h-2.9z"/></svg>',
  x:'<svg viewBox="0 0 24 24"><path d="M18.9 2H22l-7.4 8.5L23 22h-6.8l-5-6.6L5.4 22H2.3l7.9-9L1.5 2h6.9l4.5 6 5.2-6zm-1.2 18h1.7L7.4 3.8H5.6L17.7 20z"/></svg>',
  li:'<svg viewBox="0 0 24 24"><path d="M20.4 3H3.6A.6.6 0 003 3.6v16.8a.6.6 0 00.6.6h16.8a.6.6 0 00.6-.6V3.6a.6.6 0 00-.6-.6zM8.3 18.3H5.5V9.5h2.8v8.8zM6.9 8.3a1.6 1.6 0 110-3.2 1.6 1.6 0 010 3.2zm11.4 10H15.5v-4.3c0-1 0-2.3-1.4-2.3s-1.6 1.1-1.6 2.3v4.4h-2.8V9.5h2.7v1.2h.1a3 3 0 012.6-1.4c2.8 0 3.3 1.9 3.3 4.3v4.7z"/></svg>',
  paper:'<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm4 18H6V4h7v5h5v11zM8 12h8v2H8v-2zm0 4h8v2H8v-2z"/></svg>'
};
function renderPeople(){
  var list=people.filter(matchesPerson);
  var s=state.people;
  list.sort(function(a,b){var k=s.sort==="org"?"org":s.sort==="cat"?"category":"name";return (a[k]||"").localeCompare(b[k]||"");});
  document.getElementById("count-people").textContent=list.length+" of "+people.length;
  var grid=document.getElementById("grid-people");
  if(!list.length){grid.innerHTML='<div class="empty">No researchers match these filters.</div>';return;}
  grid.innerHTML=list.map(function(p){
    var tags=(p.focus||"").split(";").map(function(x){return x.trim();}).filter(Boolean).slice(0,6)
      .map(function(t){return tagChipHtml("people",t);}).join("");
    if(tags&&p.focusInferred)tags+=' <span class="tag" style="opacity:.6" title="Focus tags inferred from this person\'s description">≈</span>';
    var moved=(p.currentOrg && p.currentOrg!==p.org)?'<p class="drow"><span class="dlab">Now at: </span>'+esc(p.currentOrg)+'</p>':'';
    var det="";
    function row(lab,val){return val?'<p class="drow"><span class="dlab">'+lab+': </span>'+esc(val)+'</p>':'';}
    if(p.role)det+='<p class="drow" style="font-weight:600">'+esc(p.role)+'</p>';
    if(p.blurb)det+='<p class="drow" style="color:#3f3e3a">'+esc(p.blurb)+'</p>';
    det+=row("Notable work",p.notable);
    det+=row("Tools / OSS",p.tools);
    var bms=(p.benchmarks||"").split(";").map(function(x){return x.trim();}).filter(Boolean);
    if(bms.length){det+='<p class="drow" style="margin-bottom:2px"><span class="dlab">Benchmarks:</span></p><div class="tags" style="margin:0 0 6px">'
      +bms.map(function(b){return DSSET[b.toLowerCase()]?navChip(b,"datasets",b,"View in Datasets tab"):'<span class="tag">'+esc(b)+'</span>';}).join(" ")+'</div>';}
    det+=row("Standards",p.frameworks);
    det+=row("Talks",p.talks);
    det+=row("Awards",p.awards);
    det+=row("Academic affiliation",p.affiliations);
    if(p.confs&&p.confs.length){det+='<p class="drow" style="margin-bottom:2px"><span class="dlab">Conferences:</span></p><div class="tags" style="margin:0 0 6px">'
      +navChips(p.confs,"confs","View in Conferences tab")+'</div>';}
    if(p.fellows&&p.fellows.length){det+='<p class="drow" style="margin-bottom:2px"><span class="dlab">Fellowships:</span></p><div class="tags" style="margin:0 0 6px">'
      +navChips(p.fellows,"fellows","View in Fellowships tab")+'</div>';}
    var pnav="";
    (p.ptab||[]).forEach(function(t){pnav+=navChip(t.length>46?t.slice(0,44)+"…":t,"papers",t,"View in Papers tab: "+t)+" ";});
    if(p.inAuthors)pnav+=navChip("Papers by "+p.name.split(" ")[0],"papers",p.name,"Search Papers tab by author");
    if(pnav)det+='<p class="drow" style="margin-bottom:2px"><span class="dlab">In Papers tab:</span></p><div class="tags" style="margin:0 0 6px">'+pnav+'</div>';
    det+=moved;
    if(!det)det='<p class="drow" style="color:#a8a69d">No further detail recorded.</p>';
    var lk="";
    function link(url,label,ic,tip){return url?'<a class="lnk" href="'+esc(url)+'" target="_blank" rel="noopener"'+(tip?' title="'+esc(tip)+'"':'')+' onclick="event.stopPropagation()">'+ICON[ic]+label+'</a>':'';}
    (p.papers||[]).forEach(function(pp,i){lk+=link(pp.u,(p.papers.length>1?"Paper "+(i+1):"Paper"),"paper",pp.t);});
    lk+=link(p.site,"Website","web");
    lk+=link(p.linkedin,"LinkedIn","li");
    lk+=link(p.x,"X","x");
    if(lk)det+='<div class="links">'+lk+'</div>';
    return '<div class="card" onclick="this.classList.toggle(\'open\')">'
      +'<div class="chead"><div class="av">'+esc(initials(p.name).toUpperCase())+'</div>'
      +'<div style="min-width:0"><p class="nm">'+esc(p.name)+(p.isNew?'<span class="newdot">new</span>':'')+'</p>'
      +'<p class="orgline">'+esc(p.org)+'</p></div></div>'
      +'<div><span class="cat">'+esc(p.category)+'</span></div>'
      +'<div class="tags">'+tags+'</div>'
      +'<div class="detail">'+det+'</div></div>';
  }).join("");
}

/* ---------- ORGANIZATIONS ---------- */
var groupsel=document.getElementById("groupsel");
groupsel.innerHTML='<option value="all">All groups</option>'+DATA.orgGroups.map(function(g){return '<option value="'+esc(g)+'">'+esc(g)+'</option>';}).join("");
groupsel.value=state.orgs.group;
groupsel.onchange=function(){state.orgs.group=groupsel.value;persist();renderOrgs();};
wireSearch("q-orgs",state.orgs,function(){renderOrgs();});
function renderOrgs(){
  var s=state.orgs,q=s.q.toLowerCase();
  var list=DATA.orgs.filter(function(o){
    if(s.group!=="all"&&o.group!==s.group)return false;
    if(q&&(o.name+" "+o.group+" "+o.people.join(" ")).toLowerCase().indexOf(q)<0)return false;
    return true;
  });
  document.getElementById("count-orgs").textContent=list.length+" of "+DATA.orgs.length;
  var grid=document.getElementById("grid-orgs");
  if(!list.length){grid.innerHTML='<div class="empty">No organizations match.</div>';return;}
  grid.innerHTML=list.map(function(o){
    var det='<p class="drow"><span class="dlab">Group: </span>'+esc(o.group)+'</p>';
    det+=o.people.length?'<p class="drow"><span class="dlab">In People directory ('+o.people.length+'): </span></p><div class="tags">'+peopleChips(o.people,20)+'</div>'
      :'<p class="drow" style="color:#a8a69d">No tracked researchers at this org.</p>';
    return '<div class="card" onclick="this.classList.toggle(\'open\')">'
      +'<div class="chead"><div class="av">'+esc(initials(o.name).toUpperCase())+'</div>'
      +'<div style="min-width:0"><p class="nm">'+esc(o.name)+'</p>'
      +'<p class="orgline">'+esc(o.group)+(o.people.length?' · '+o.people.length+' tracked':'')+'</p></div></div>'
      +'<div class="detail">'+det+'</div></div>';
  }).join("");
}

/* ---------- PAPERS ---------- */
var pcatsel=document.getElementById("pcatsel");
var pcats=[];DATA.papers.forEach(function(p){if(pcats.indexOf(p.cat)<0)pcats.push(p.cat);});
pcats.sort();
pcatsel.innerHTML='<option value="all">All wiki categories</option>'+pcats.map(function(c){return '<option value="'+esc(c)+'">'+esc(c)+'</option>';}).join("");
pcatsel.value=state.papers.cat;
pcatsel.onchange=function(){state.papers.cat=pcatsel.value;persist();renderPapers();};
var pkindsel=document.getElementById("pkindsel");
pkindsel.value=state.papers.kind;
pkindsel.onchange=function(){state.papers.kind=pkindsel.value;persist();renderPapers();};
var psortsel=document.getElementById("psortsel");
psortsel.value=state.papers.sort;
psortsel.onchange=function(){state.papers.sort=psortsel.value;persist();renderPapers();};
function paperYear(p){return (p.date||"").slice(0,4)||"undated";}
var pyearsel=document.getElementById("pyearsel");
var pyears=[];DATA.papers.forEach(function(p){var y=paperYear(p);if(y!=="undated"&&pyears.indexOf(y)<0)pyears.push(y);});
pyears.sort().reverse();
pyearsel.innerHTML='<option value="all">All years</option>'+pyears.map(function(y){return '<option value="'+y+'">'+y+'</option>';}).join("")+'<option value="undated">Undated</option>';
pyearsel.value=state.papers.year;
pyearsel.onchange=function(){state.papers.year=pyearsel.value;persist();renderPapers();};
wireSearch("q-papers",state.papers,function(){renderPapers();});
function renderPapers(){
  var s=state.papers,q=s.q.toLowerCase();
  var list=DATA.papers.filter(function(p){
    if(s.cat!=="all"&&p.cat!==s.cat)return false;
    if(s.kind!=="all"&&p.kind!==s.kind)return false;
    if(s.year!=="all"&&paperYear(p)!==s.year)return false;
    if(s.tags.length){
      var have=p.tags.map(function(t){return t.toLowerCase();});
      if(!tagsMatch(s.tags,s.tagsMode,have,(p.sub+" "+p.cat).toLowerCase()))return false;
    }
    if(q&&(p.title+" "+p.authors+" "+p.tags.join(" ")+" "+p.sub+" "+(p.dataset||"")+" "+(p.rp||[]).join(" ")).toLowerCase().indexOf(q)<0)return false;
    return true;
  });
  if(s.sort==="title")list=list.slice().sort(function(a,b){return a.title.localeCompare(b.title);});
  document.getElementById("count-papers").textContent=list.length+" of "+DATA.papers.length;
  var el=document.getElementById("list-papers");
  if(!list.length){el.innerHTML='<div class="empty">No papers match.</div>';return;}
  el.innerHTML=list.map(function(p){
    var t=p.url?'<a href="'+esc(p.url)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()">'+esc(p.title)+'</a>':esc(p.title);
    var meta=[p.authors,p.date,p.sub].filter(Boolean).map(esc).join(" · ");
    var tags=p.tags.map(function(x){return tagChipHtml("papers",x);}).join("");
    var det=p.summary?'<p class="drow" style="color:#3f3e3a">'+esc(p.summary)+'</p>':'<p class="drow" style="color:#a8a69d">No summary recorded.</p>';
    det+='<p class="drow"><span class="dlab">Wiki category: </span>'+esc(p.cat)+(p.sub?' → '+esc(p.sub):'')+'</p>';
    if(p.rp&&p.rp.length)det+='<p class="drow" style="margin-bottom:2px"><span class="dlab">In People directory ('+p.rp.length+'):</span></p><div class="tags">'+peopleChips(p.rp,15)+'</div>';
    return '<div class="card" onclick="this.classList.toggle(\'open\')">'
      +'<p class="ptitle">'+(p.kind==="benchmark"?'<span class="badge b-green">benchmark</span>':'')+(p.dataset?'<span class="badge b-purple" title="Matches a tracked dataset: '+esc(p.dataset)+'">dataset: '+esc(p.dataset)+'</span>':'')+t+'</p>'
      +'<p class="pmeta">'+meta+'</p>'
      +(tags?'<div class="tags">'+tags+'</div>':'')
      +'<div class="detail">'+det+'</div></div>';
  }).join("");
}

/* ---------- CONFERENCES ---------- */
var cyearsel=document.getElementById("cyearsel");
var years=[];DATA.conferences.forEach(function(c){if(c.year&&years.indexOf(c.year)<0)years.push(c.year);});
years.sort().reverse();
cyearsel.innerHTML='<option value="all">All years</option>'+years.map(function(y){return '<option value="'+y+'">'+y+'</option>';}).join("");
cyearsel.value=state.confs.year;
cyearsel.onchange=function(){state.confs.year=cyearsel.value;persist();renderConfs();};
var ctypesel=document.getElementById("ctypesel");
var ctypes=[];DATA.conferences.forEach(function(c){if(c.type&&ctypes.indexOf(c.type)<0)ctypes.push(c.type);});
ctypes.sort();
ctypesel.innerHTML='<option value="all">All types</option>'+ctypes.map(function(t){return '<option value="'+esc(t)+'">'+esc(t)+'</option>';}).join("");
ctypesel.value=state.confs.type;
ctypesel.onchange=function(){state.confs.type=ctypesel.value;persist();renderConfs();};
wireSearch("q-confs",state.confs,function(){renderConfs();});
function renderConfs(){
  var s=state.confs,q=s.q.toLowerCase();
  var list=DATA.conferences.filter(function(c){
    if(s.year!=="all"&&c.year!==s.year)return false;
    if(s.type!=="all"&&c.type!==s.type)return false;
    if(s.tags.length){
      var have=c.focus.map(function(t){return t.toLowerCase();});
      if(!tagsMatch(s.tags,s.tagsMode,have))return false;
    }
    if(q){
      var hay=(c.name+" "+c.loc+" "+c.series+" "+c.focus.join(" ")+" "+c.people.map(function(p){return p.n;}).join(" ")).toLowerCase();
      if(hay.indexOf(q)<0)return false;
    }
    return true;
  });
  document.getElementById("count-confs").textContent=list.length+" of "+DATA.conferences.length;
  var el=document.getElementById("list-confs");
  if(!list.length){el.innerHTML='<div class="empty">No conferences match.</div>';return;}
  el.innerHTML=list.map(function(c){
    var t=c.url?'<a href="'+esc(c.url)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()">'+esc(c.name)+'</a>':esc(c.name);
    var meta=[c.year,c.loc,c.type].filter(Boolean).map(esc).join(" · ");
    var badges="";
    if(c.pri)badges+='<span class="badge '+(c.pri==="High"?"b-green":c.pri==="Medium"?"b-amber":"b-gray")+'">'+esc(c.pri)+' priority</span>';
    var tags=c.focus.map(function(x){return tagChipHtml("confs",x);}).join("");
    var det="";
    if(c.rec)det+='<p class="drow"><span class="dlab">Why: </span>'+esc(c.rec)+'</p>';
    if(c.notes)det+='<p class="drow"><span class="dlab">Notes: </span>'+esc(c.notes)+'</p>';
    if(c.series)det+='<p class="drow"><span class="dlab">Series: </span>'+esc(c.series)+'</p>';
    det+=c.people.length?'<p class="drow"><span class="dlab">Roster participants ('+c.people.length+'): </span></p><div class="tags">'+peopleChips(c.people,25)+'</div>'
      :'<p class="drow" style="color:#a8a69d">No roster participants recorded.</p>';
    det+='<p class="drow" style="margin-top:8px"><span class="dlab">Source: </span>'+(c.src==="csv"?"researchers file":"Notion conference DB"+(c.src==="notion+csv"?" + researchers file":""))+'</p>';
    return '<div class="card" onclick="this.classList.toggle(\'open\')">'
      +'<p class="ptitle">'+t+'</p>'
      +'<p class="pmeta">'+meta+(c.people.length?' · '+c.people.length+' from roster':'')+'</p>'
      +'<div style="margin-top:6px">'+badges+'</div>'
      +(tags?'<div class="tags">'+tags+'</div>':'')
      +'<div class="detail">'+det+'</div></div>';
  }).join("");
}

/* ---------- FELLOWSHIPS ---------- */
wireSearch("q-fellows",state.fellows,function(){renderFellows();});
function renderFellows(){
  var s=state.fellows,q=s.q.toLowerCase();
  var list=DATA.fellowships.filter(function(f){
    if(s.tags.length){
      var have=(f.focus_areas||[]).map(function(t){return t.toLowerCase();});
      if(!tagsMatch(s.tags,s.tagsMode,have))return false;
    }
    if(!q)return true;
    return (f.name+" "+(f.program_full||"")+" "+(f.funder||"")+" "+(f.focus||"")+" "+(f.status||"")
      +" "+(f.focus_areas||[]).join(" ")
      +" "+f.people.map(function(p){return p.n+" "+(p.note||"");}).join(" ")).toLowerCase().indexOf(q)>=0;
  });
  document.getElementById("count-fellows").textContent=list.length+" of "+DATA.fellowships.length+" programs";
  var el=document.getElementById("list-fellows");
  if(!list.length){el.innerHTML='<div class="empty">No fellowship programs match.</div>';return;}
  el.innerHTML=list.map(function(f){
    var t=f.link?'<a href="'+esc(f.link)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()">'+esc(f.name)+'</a>':esc(f.name);
    var badges='<span class="badge b-purple">'+f.people.length+' '+(f.people.length===1?'person':'people')+'</span>';
    if(f.status){
      var sl=f.status.toLowerCase();
      var cls=sl.indexOf("open")>=0?"b-green":sl.indexOf("closed")>=0?"b-gray":"b-amber";
      badges+=' <span class="badge '+cls+'">'+esc(f.status)+'</span>';
    }
    var meta=[f.funder,(f.deadline?"deadline "+f.deadline:"")].filter(Boolean).map(esc).join(" · ");
    var tags=(f.focus_areas||[]).map(function(x){return tagChipHtml("fellows",x);}).join("");
    var det="";
    if(f.program_full&&f.program_full!==f.name)det+='<p class="drow"><span class="dlab">Program: </span>'+esc(f.program_full)+'</p>';
    if(f.focus)det+='<p class="drow" style="color:#3f3e3a">'+esc(f.focus)+'</p>';
    if(f.funding)det+='<p class="drow"><span class="dlab">Funding: </span>'+esc(f.funding)+'</p>';
    if(f.deadline)det+='<p class="drow"><span class="dlab">Deadline: </span>'+esc(f.deadline)+'</p>';
    det+='<p class="drow" style="margin-bottom:2px"><span class="dlab">Roster participants ('+f.people.length+'):</span></p><div class="tags" style="margin:0 0 6px">'+peopleChips(f.people,40)+'</div>';
    if(f.confs&&f.confs.length)det+='<p class="drow" style="margin-bottom:2px"><span class="dlab">Participants seen at conferences:</span></p><div class="tags" style="margin:0 0 6px">'
      +navChips(f.confs,"confs","View in Conferences tab",10)+'</div>';
    if(f.status||f.funding||f.focus)det+='<p class="drow" style="margin-top:8px"><span class="dlab">Program info: </span>Notion fellowships DB snapshot</p>';
    return '<div class="card" onclick="this.classList.toggle(\'open\')">'
      +'<p class="ptitle">'+t+'</p>'
      +(meta?'<p class="pmeta">'+meta+'</p>':'')
      +'<div style="margin-top:6px">'+badges+'</div>'
      +(tags?'<div class="tags">'+tags+'</div>':'')
      +'<div class="detail">'+det+'</div></div>';
  }).join("");
}

/* ---------- DATASETS ---------- */
wireSearch("q-datasets",state.datasets,function(){renderDatasets();});
var dyearsel=document.getElementById("dyearsel");
var dyears=[];DATA.datasets.forEach(function(d){var y=String(d.year||"");if(y&&dyears.indexOf(y)<0)dyears.push(y);});
dyears.sort().reverse();
dyearsel.innerHTML='<option value="all">All years</option>'+dyears.map(function(y){return '<option value="'+y+'">'+y+'</option>';}).join("");
dyearsel.value=state.datasets.year;
dyearsel.onchange=function(){state.datasets.year=dyearsel.value;persist();renderDatasets();};
function renderDatasets(){
  var s=state.datasets,q=s.q.toLowerCase();
  var list=DATA.datasets.filter(function(d){
    if(s.year!=="all"&&String(d.year||"")!==s.year)return false;
    if(s.tags.length){
      var have=(d.tags||[]).map(function(t){return t.toLowerCase();});
      if(!tagsMatch(s.tags,s.tagsMode,have))return false;
    }
    if(!q)return true;
    return (d.name+" "+(d.desc||"")+" "+(d.tags||[]).join(" ")+" "+(d.year||"")+" "+d.people.join(" ")).toLowerCase().indexOf(q)>=0;
  });
  document.getElementById("count-datasets").textContent=list.length+" of "+DATA.datasets.length;
  var el=document.getElementById("grid-datasets");
  if(!list.length){el.innerHTML='<div class="empty">No benchmarks / datasets match.</div>';return;}
  el.innerHTML=list.map(function(d){
    var url=d.url||("https://www.google.com/search?q="+encodeURIComponent('"'+d.name+'" AI benchmark dataset'));
    var meta=[d.year,d.people.length+" associated researcher"+(d.people.length===1?"":"s")].filter(Boolean).join(" · ");
    return '<div class="card static">'
      +'<p class="ptitle"><a href="'+esc(url)+'" target="_blank" rel="noopener">'+esc(d.name)+'</a>'
      +(d.url?'':' <span class="badge b-gray" title="No recorded URL — links to a web search">search</span>')+'</p>'
      +'<p class="pmeta">'+meta+'</p>'
      +((d.tags||[]).length?'<div class="tags" style="margin-top:6px">'+d.tags.map(function(x){return tagChipHtml("datasets",x);}).join("")+'</div>':'')
      +(d.desc?'<p class="drow" style="color:#3f3e3a;margin-top:6px">'+esc(d.desc)+'</p>':'')
      +'<div class="tags" style="margin-top:8px">'+peopleChips(d.people,15)+'</div></div>';
  }).join("");
}

var RENDER={people:renderPeople,orgs:renderOrgs,papers:renderPapers,confs:renderConfs,fellows:renderFellows,datasets:renderDatasets};
document.getElementById("foot").textContent="People & fellowships from the vault's researcher file · papers from the wiki RAG manifest · orgs from the 200-org roster · conferences from the Notion DB (snapshot "+(DATA.notionFetched||"—")+") merged with the researcher file. Refreshed weekly by a scheduled task.";
if(!RENDER[state.tab])state.tab="people";
setTab(state.tab);
</script>
</body>
</html>"""

HTML = HTML.replace("/*DATA*/", DATA_JSON)
out = os.path.join(BASE, "ai-safety-people-directory.html")
open(out, "w", encoding="utf-8").write(HTML)
print("wrote", out, len(HTML), "bytes")
print(f"people {len(people)} | orgs {len(data['orgs'])} | papers {len(data['papers'])} | "
      f"confs {len(data['conferences'])} | fellowships {len(data['fellowships'])} | datasets {len(data['datasets'])}")
