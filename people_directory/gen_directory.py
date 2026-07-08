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

# 2026-07-08: papers with a blank manifest author but matched tracked-people
# authors (pap["rp"], built above from the header-scan seed + title/author
# matches) show those names on the Papers-tab author line, and count as
# "has author" for the Metadata-health pill (see _corpus_stats). This is a
# DISPLAY + METRIC change only — nothing is written back to source metadata,
# so it stays self-maintaining: recomputed each run from the freshly rebuilt
# RAG chunks and the current people set. The names are the tracked-people
# SUBSET of the author list, not necessarily the full byline.
_tracked_author_pids = set()
for pap in papers:
    if not (pap.get("authors") or "").strip() and pap.get("rp"):
        pap["authors"] = ", ".join(pap["rp"])
        if pap.get("pid"):
            _tracked_author_pids.add(pap["pid"])

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

# ---- Stats-tab corpus snapshot (2026-07-05) ------------------------------
# Computed fresh from manifest.csv + vault log.md at generation time (never
# hand-edited — WORKFLOW.md invariant 9). Live counterparts (index_stats,
# list_categories/concepts/tags) are fetched in-page via the Cowork MCP
# bridge; these snapshot fields are the fallback and cover what the MCP
# doesn't expose (years, source types, risk, tokens, log activity, health).
def _corpus_stats(tracked_author_pids=frozenset()):
    import csv as _csv, glob as _glob
    man = os.path.join(BASE, "..", "01_data", "index", "manifest.csv")
    # vault log.md: Mac path when run locally, mount path when run in the
    # Cowork sandbox (session prefix varies, hence the glob)
    _cands = [os.path.expanduser("~/Desktop/AI Safety/AI Safety/log.md")] \
        + _glob.glob("/sessions/*/mnt/AI Safety--AI Safety/log.md")
    log_md = next((p for p in _cands if os.path.exists(p)), _cands[0])
    try:
        rows = [r for r in _csv.DictReader(open(man, encoding="utf-8"))
                if r.get("category") != "_index"]
    except OSError:
        return None
    years = collections.Counter((r["published"] or "")[:4] for r in rows if r["published"].strip())
    stype = collections.Counter(r["source_type"] or "(none)" for r in rows)
    risk = collections.Counter()
    for r in rows:
        for part in (r.get("risk_category") or "").split("|"):
            if part.strip():
                risk[part.strip()] += 1
    tokcat = collections.Counter()
    filecat = collections.Counter()
    for r in rows:
        tokcat[r["category"]] += int(r.get("n_tokens") or 0)
        filecat[r["category"]] += 1
    log_month, log_kind = collections.Counter(), collections.Counter()
    try:
        for m, k in re.findall(r"^## \[(\d{4}-\d{2})-\d{2}\] (\w+)",
                               open(log_md, encoding="utf-8").read(), re.M):
            log_month[m] += 1
            log_kind[k] += 1
    except OSError:
        pass
    return {
        "generated": datetime.date.today().isoformat(),
        "nSources": len(rows),
        "years": dict(sorted(years.items())),
        "sourceType": dict(stype.most_common()),
        "risk": dict(risk.most_common()),
        "tokensByCat": dict(tokcat.most_common()),
        "filesByCat": dict(filecat.most_common()),
        "logByMonth": dict(sorted(log_month.items())),
        "logByKind": dict(log_kind.most_common()),
        "health": {
            # a paper counts as "has author" if the manifest author is set OR
            # we matched tracked-people authors for it (2026-07-08); the latter
            # is display-only enrichment, but for health it means we do have an
            # author signal, so it shouldn't read as a metadata gap.
            "missing author": sum(1 for r in rows if not r["author"].strip()
                                  and r.get("file_id") not in tracked_author_pids),
            "missing published date": sum(1 for r in rows if not r["published"].strip()),
            "missing tags": sum(1 for r in rows if not r["tags"].strip()),
            "missing source URL": sum(1 for r in rows if not r["source_url"].strip()),
            "missing source_type": sum(1 for r in rows if not r["source_type"].strip()),
        },
    }

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
    "datasets": extra["datasets"], "policies": extra["policies"],
    "notionFetched": extra.get("notionFetched", ""),
    "dsNames": [d["name"].lower() for d in extra["datasets"]],
    "stats": _corpus_stats(_tracked_author_pids),
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
<title>The AI Safety Directory</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Spectral:wght@500;600&family=Libre+Franklin:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box}
html,body{margin:0}
body{background:#f6f3ec}
::selection{background:#e7d3c6}
input::placeholder{color:#a49b88}
select{-webkit-appearance:none;appearance:none;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6'><path d='M0 0l5 6 5-6z' fill='%238a8272'/></svg>");background-repeat:no-repeat;background-position:right 11px center;padding-right:26px!important}
@keyframes aisdFade{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
.aisd-tab:hover{color:#232019!important}
.aisd-row:hover{background:#efe8db!important}
.aisd-back:hover{color:#a75a38!important}
.aisd-title-link:hover{color:#a75a38!important}
.aisd-navchip:hover{border-color:#a75a38!important;color:#a75a38!important}
.aisd-sidelink:hover{background:#f0e2d8!important}
.aisd-primary:hover{border-color:#c9beac!important;background:#f4eddc!important}
</style>
</head>
<body>
<div id="app"></div>
<script>
window.__AISD_DATA = /*DATA*/;

function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}

class DCLogic{
  constructor(props){ this.props=props||{}; this.state={}; this._el=null; this._hnd=[]; }
  _mount(el){
    this._el=el; var self=this;
    el.addEventListener('click',function(e){ var t=e.target.closest&&e.target.closest('[data-h]'); if(t){ var f=self._hnd[+t.getAttribute('data-h')]; if(f){ f(e); } } });
    el.addEventListener('change',function(e){ var t=e.target.closest&&e.target.closest('[data-ch]'); if(t){ var f=self._hnd[+t.getAttribute('data-ch')]; if(f){ f(e); } } });
    el.addEventListener('input',function(e){ var t=e.target; if(t&&t.getAttribute&&t.getAttribute('data-inp')!=null){ var f=self._hnd[+t.getAttribute('data-inp')]; if(f){ f(e); } } });
    this._render();
    if(this.componentDidMount){ this.componentDidMount(); }
  }
  setState(patch,cb){ if(typeof patch==='function'){ patch=patch(this.state); } Object.assign(this.state,patch); this._render(); if(cb){ cb(); } }
  forceUpdate(){ this._render(); }
  _render(){
    var ae=document.activeElement, wasQ=!!(ae&&ae.id==='aisd-q'), caret=wasQ?ae.selectionStart:0;
    this._hnd=[];
    var v=this.renderVals();
    this._el.innerHTML=viewHTML(v,this._hnd);
    if(wasQ){ var q=document.getElementById('aisd-q'); if(q){ q.focus(); try{ q.setSelectionRange(caret,caret); }catch(e){} } }
  }
}

class Component extends DCLogic {
  constructor(props){
    super(props);
    const def = {
      tab:'people', sel:null,
      people:{q:'',cat:'all',focus:[],focusMode:'all',sort:'name'},
      orgs:{q:'',group:'all'},
      papers:{q:'',cat:'all',kind:'all',year:'all',tags:[],tagsMode:'all',sort:'date'},
      policy:{q:'',org:'all',kind:'all',year:'all'},
      confs:{q:'',year:'all',type:'all',tags:[],tagsMode:'all'},
      fellows:{q:'',tags:[],tagsMode:'all'},
      datasets:{q:'',year:'all',tags:[],tagsMode:'all'},
      expand:{}
    };
    try{ const s=JSON.parse(localStorage.getItem('aisd_redesign_v1')); if(s){ for(const k in s){ if(def[k]&&typeof def[k]==='object'&&!Array.isArray(def[k])) Object.assign(def[k],s[k]); else def[k]=s[k]; } } }catch(e){}
    def.sel=null; def.expand=def.expand||{};
    this.state=def;
    this.TONE={green:{bg:'#dbeee0',color:'#2f6d43'},amber:{bg:'#f2e6cd',color:'#8a5f14'},purple:{bg:'#e4e3f2',color:'#4f4e94'},teal:{bg:'#d7ebe8',color:'#276b64'},gray:{bg:'#e9e3d6',color:'#6a6355'},clay:{bg:'#f0e0d6',color:'#9a4f2f'}};
    this.KIND={
      person:{label:'Researcher',color:'#a75a38',tint:'#f0e2d8'},
      org:{label:'Organization',color:'#2e7d76',tint:'#dcece9'},
      paper:{label:'Paper',color:'#7a6a2f',tint:'#ece5cf'},
      policy:{label:'Policy',color:'#5b5aa0',tint:'#e4e3f2'},
      conf:{label:'Conference',color:'#b06a2f',tint:'#f0e2d2'},
      fellow:{label:'Fellowship',color:'#4a7a52',tint:'#dfebdc'},
      dataset:{label:'Dataset',color:'#8a5670',tint:'#eddde6'}
    };
  }
  componentDidMount(){ if(!window.__AISD_DATA){ this._t=setInterval(()=>{ if(window.__AISD_DATA){ clearInterval(this._t); this.forceUpdate(); } },40); } }
  componentWillUnmount(){ clearInterval(this._t); }
  data(){ return window.__AISD_DATA; }
  persist(){ try{ const {expand,sel,...rest}=this.state; localStorage.setItem('aisd_redesign_v1',JSON.stringify(rest)); }catch(e){} }
  join(a){ return a.filter(Boolean).join(' \u00b7 '); }
  initials(n){ const p=String(n||'').split(/\s+/).filter(Boolean); return (((p[0]||'')[0]||'')+((p[p.length-1]||'')[0]||'')).toUpperCase(); }
  fmtN(n){ return n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'k':String(n); }
  badge(label,t){ const x=this.TONE[t]||this.TONE.gray; return {label,bg:x.bg,color:x.color}; }
  priTone(p){ return p==='High'?'green':p==='Medium'?'amber':'gray'; }
  statusTone(s){ const l=String(s).toLowerCase(); return l.indexOf('open')>=0?'green':l.indexOf('closed')>=0?'gray':'amber'; }
  kmono(k){ return {person:'',org:'',paper:'PA',policy:'PO',conf:'CF',fellow:'FE',dataset:'DS'}[k]; }

  setTabFn(t){ this.setState({tab:t,sel:null},()=>this.persist()); try{window.scrollTo(0,0);}catch(e){} }
  setCur(key,val){ const t=this.state.tab; this.setState(s=>({[t]:{...s[t],[key]:val}}),()=>this.persist()); }
  toggleChip(tab,key,val){ this.setState(s=>{ const st={...s[tab]}; const a=st[key].slice(); const i=a.indexOf(val); if(i>=0)a.splice(i,1); else a.push(val); st[key]=a; return {[tab]:st}; },()=>this.persist()); }
  clearChips(tab,key){ this.setState(s=>({[tab]:{...s[tab],[key]:[]}}),()=>this.persist()); }
  setChipMode(tab,mkey){ this.setState(s=>{ const st={...s[tab]}; st[mkey]=st[mkey]==='any'?'all':'any'; return {[tab]:st}; },()=>this.persist()); }
  toggleExpand(tab){ this.setState(s=>({expand:{...s.expand,[tab]:!s.expand[tab]}})); }
  open(sel){ this.setState({sel}); try{window.scrollTo(0,0);}catch(e){} }
  back(){ this.setState({sel:null}); }
  pmap(){ if(!this._pm){ this._pm={}; (this.data().people||[]).forEach(p=>{ this._pm[p.name]=p; }); } return this._pm; }
  openPersonByName(n){ const p=this.pmap()[n]; if(p) this.open({type:'person',item:p}); else this.gotoTab('people',n); }
  gotoTab(tab,q){
    const resets={papers:{cat:'all',kind:'all',year:'all',tags:[]},confs:{year:'all',type:'all',tags:[]},orgs:{group:'all'},datasets:{year:'all',tags:[]},policy:{org:'all',kind:'all',year:'all'},people:{cat:'all',focus:[]},fellows:{tags:[]}};
    this.setState(s=>{ const st={...s[tab],q}; Object.assign(st,resets[tab]||{}); st.q=q; return {[tab]:st,tab,sel:null}; },()=>this.persist());
    try{window.scrollTo(0,0);}catch(e){}
  }
  tagsMatch(sel,mode,haveLc,extraLc){ const f=t=>{ t=t.toLowerCase(); return haveLc.indexOf(t)>=0||(extraLc&&extraLc.indexOf(t)>=0); }; return mode==='any'?sel.some(f):sel.every(f); }
  uniq(arr){ const o=[],seen={}; arr.forEach(x=>{ if(x&&!seen[x]){seen[x]=1;o.push(x);} }); return o; }

  peopleChips(list,cap){ cap=cap||60; const out=(list||[]).slice(0,cap).map(pp=>{ const n=typeof pp==='string'?pp:pp.n; const sub=typeof pp==='string'?'':(pp.r||pp.note||''); return {label:n,sub,onClick:()=>this.openPersonByName(n)}; }); if((list||[]).length>cap) out.push({label:'+'+((list.length)-cap)+' more',sub:'',onClick:()=>{}}); return out; }
  navChips(list,tab){ return (list||[]).map(x=>({label:x.length>46?x.slice(0,44)+'\u2026':x,sub:'',onClick:()=>this.gotoTab(tab,x)})); }

  chipStyle(active){ return active?{bg:'#a75a38',color:'#fdfbf6',border:'#a75a38'}:{bg:'#fdfbf6',color:'#6f685c',border:'#d3ccbc'}; }
  buildChips(tab,key,vocab){
    const st=this.state[tab], sel=st[key], expanded=!!this.state.expand[tab], limit=16;
    const vis=expanded?vocab:vocab.slice(0,limit);
    const items=vis.map(v=>({label:v[0],count:v[1],...this.chipStyle(sel.indexOf(v[0])>=0),onClick:()=>this.toggleChip(tab,key,v[0])}));
    sel.forEach(t=>{ if(!vis.some(v=>v[0]===t)) items.push({label:t,count:'',...this.chipStyle(true),onClick:()=>this.toggleChip(tab,key,t)}); });
    const cs=this.chipStyle(sel.length===0);
    return { has:true, items,
      clearBg:cs.bg, clearColor:cs.color, clearBorder:cs.border, onClear:()=>this.clearChips(tab,key),
      showExpand:vocab.length>limit, expandLabel:expanded?'\u2212 fewer':('+'+(vocab.length-limit)+' more'), onExpand:()=>this.toggleExpand(tab),
      showMode:sel.length>1, modeLabel:'match: '+((st[key+'Mode']||'all')==='any'?'ANY':'ALL'), onMode:()=>this.setChipMode(tab,key+'Mode') };
  }

  // ---------- ROW ADAPTERS ----------
  rowBase(k){ const cc=this.props.colorCodeKinds??true; const K=this.KIND[k]; return { kindLabel:K.label, kindColor: cc?K.color:'#8a8272', monoBg: cc?K.tint:'#e9e3d6', monoColor: cc?K.color:'#6a6355', monogram:this.kmono(k), badges:[], tags:[], hasTags:false }; }
  finishTags(r,tags){ const sft=this.props.showFocusTags??true; r.tags=(tags||[]).filter(Boolean).slice(0,5); r.hasTags=sft&&r.tags.length>0; return r; }

  personRow(p){ const r=this.rowBase('person'); r.monogram=this.initials(p.name); r.title=p.name; r.subtitle=this.join([p.org, (p.currentOrg&&p.currentOrg!==p.org)?('\u2192 now '+p.currentOrg):'']); r.meta=p.category; r.onClick=()=>this.open({type:'person',item:p}); if(p.isNew)r.badges=[this.badge('new','green')]; return this.finishTags(r,(p.focus||'').split(';').map(x=>x.trim())); }
  orgRow(o){ const r=this.rowBase('org'); r.monogram=this.initials(o.name); r.title=o.name; r.subtitle=o.people.length?(o.people.length+' tracked researcher'+(o.people.length===1?'':'s')):'No tracked researchers'; r.meta=o.group; r.onClick=()=>this.open({type:'org',item:o}); return r; }
  paperRow(p){ const r=this.rowBase('paper'); r.kindLabel=p.kind==='benchmark'?'Benchmark':'Paper'; r.title=p.title; r.subtitle=this.join([p.authors,p.date,p.sub]); r.meta=(p.date||'').slice(0,4); r.onClick=()=>this.open({type:'paper',item:p}); const b=[]; if(p.kind==='benchmark')b.push(this.badge('benchmark','teal')); if(p.dataset)b.push(this.badge('dataset','purple')); r.badges=b; return this.finishTags(r,p.tags); }
  policyRow(p){ const r=this.rowBase('policy'); r.kindLabel=p.kind==='framework'?'Framework':'Commentary'; r.title=p.title; r.subtitle=this.join([p.date,p.sub]); r.meta=''; r.onClick=()=>this.open({type:'policy',item:p}); r.badges=[this.badge(p.kind==='framework'?'framework':'commentary',p.kind==='framework'?'purple':'gray')]; return r; }
  confRow(c){ const r=this.rowBase('conf'); r.title=c.name; r.subtitle=this.join([c.year,c.loc,c.type]); r.meta=c.people.length?(c.people.length+' from roster'):(c.type||''); r.onClick=()=>this.open({type:'conf',item:c}); if(c.pri)r.badges=[this.badge(c.pri+' priority',this.priTone(c.pri))]; return this.finishTags(r,c.focus); }
  fellowRow(f){ const r=this.rowBase('fellow'); r.title=f.name; r.subtitle=this.join([f.funder, f.deadline?('deadline '+f.deadline):'']); r.meta=f.people.length+' '+(f.people.length===1?'person':'people'); r.onClick=()=>this.open({type:'fellow',item:f}); if(f.status)r.badges=[this.badge(f.status,this.statusTone(f.status))]; return this.finishTags(r,f.focus_areas); }
  datasetRow(d){ const r=this.rowBase('dataset'); r.title=d.name; r.subtitle=this.join([d.year, d.people.length+' associated researcher'+(d.people.length===1?'':'s')]); r.meta=String(d.year||''); r.onClick=()=>this.open({type:'dataset',item:d}); if(!d.url)r.badges=[this.badge('search','gray')]; return this.finishTags(r,d.tags); }

  // ---------- FILTERS ----------
  filterPeople(){ const D=this.data(),s=this.state.people; let list=D.people.filter(p=>{
      if(s.cat!=='all'&&p.category!==s.cat)return false;
      if(s.focus.length){ const have=(p.focus||'').split(';').map(x=>x.trim().toLowerCase()).filter(Boolean); if(!this.tagsMatch(s.focus,s.focusMode,have))return false; }
      if(s.q){ const hay=(p.name+' '+p.org+' '+p.focus+' '+p.notable+' '+p.currentOrg+' '+p.tools+' '+p.benchmarks).toLowerCase(); if(hay.indexOf(s.q.toLowerCase())<0)return false; }
      return true; });
    const key=s.sort==='org'?'org':s.sort==='cat'?'category':'name'; list=list.slice().sort((a,b)=>(a[key]||'').localeCompare(b[key]||'')); return list; }
  filterOrgs(){ const D=this.data(),s=this.state.orgs,q=s.q.toLowerCase(); return D.orgs.filter(o=>{ if(s.group!=='all'&&o.group!==s.group)return false; if(q&&(o.name+' '+o.group+' '+o.people.join(' ')).toLowerCase().indexOf(q)<0)return false; return true; }); }
  filterPapers(){ const D=this.data(),s=this.state.papers,q=s.q.toLowerCase(); let list=D.papers.filter(p=>{
      if(s.cat!=='all'&&p.cat!==s.cat)return false;
      if(s.kind!=='all'&&p.kind!==s.kind)return false;
      if(s.year!=='all'){ const y=(p.date||'').slice(0,4)||'undated'; if(y!==s.year)return false; }
      if(s.tags.length){ const have=(p.tags||[]).map(t=>t.toLowerCase()); if(!this.tagsMatch(s.tags,s.tagsMode,have,(p.sub+' '+p.cat).toLowerCase()))return false; }
      if(q&&(p.title+' '+p.authors+' '+(p.tags||[]).join(' ')+' '+p.sub+' '+(p.dataset||'')+' '+(p.rp||[]).join(' ')).toLowerCase().indexOf(q)<0)return false;
      return true; });
    if(s.sort==='title')list=list.slice().sort((a,b)=>a.title.localeCompare(b.title)); return list; }
  monthYear(d){ if(!d)return ''; const m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']; const y=d.slice(0,4); const mo=parseInt(d.slice(5,7),10); return (mo>=1&&mo<=12?m[mo-1]+' ':'')+y; }
  shortPolicyTitle(org,title){ let t=String(title||''); const lo=org.toLowerCase(); const lt=t.toLowerCase(); if(lt.startsWith(lo+"'s ")) t=t.slice(org.length+3); else if(lt.startsWith(lo+' ')) t=t.slice(org.length+1); return t.trim()||title; }
  filterPolicyGroups(){ const D=this.data(),s=this.state.policy,q=s.q.toLowerCase(); const list=D.policies.filter(p=>{ if(s.org!=='all'&&p.org!==s.org)return false; if(s.kind!=='all'&&p.kind!==s.kind)return false; if(s.year!=='all'){ const y=(p.date||'').slice(0,4)||'undated'; if(y!==s.year)return false; } if(q&&(p.title+' '+p.org+' '+(p.summary||'')+' '+(p.sub||'')).toLowerCase().indexOf(q)<0)return false; return true; });
    const groups={},order=[]; list.forEach(p=>{ if(!groups[p.org]){groups[p.org]=[];order.push(p.org);} groups[p.org].push(p); });
    const nf=o=>groups[o].filter(p=>p.kind==='framework').length;
    order.sort((a,b)=>{ if(nf(b)!==nf(a))return nf(b)-nf(a); if(groups[b].length!==groups[a].length)return groups[b].length-groups[a].length; return a.localeCompare(b); });
    const cc=this.props.colorCodeKinds??true, K=this.KIND.policy;
    return { total:list.length, groups: order.map(org=>{
      const docs=groups[org].slice().sort((a,b)=>{ const fa=a.kind==='framework'?0:1, fb=b.kind==='framework'?0:1; if(fa!==fb)return fa-fb; return (b.date||'').localeCompare(a.date||''); });
      const primary=docs[0], rest=docs.slice(1);
      const pb=this.badge(primary.kind==='framework'?'framework':'commentary', primary.kind==='framework'?'purple':'gray');
      return { org, monogram:this.initials(org), monoBg: cc?K.tint:'#e9e3d6', monoColor: cc?K.color:'#6a6355',
        countLabel: docs.length+' doc'+(docs.length===1?'':'s'),
        primaryTitle: this.shortPolicyTitle(org,primary.title), primaryDate: this.monthYear(primary.date),
        primaryBadgeLabel: pb.label, primaryBadgeBg: pb.bg, primaryBadgeColor: pb.color,
        onPrimary: ()=>this.open({type:'policy',item:primary}),
        hasVersions: rest.length>0,
        versions: rest.map(p=>({ label:this.shortPolicyTitle(org,p.title), dateLabel:this.monthYear(p.date), onClick:()=>this.open({type:'policy',item:p}) })) };
    }) }; }
  filterConfs(){ const D=this.data(),s=this.state.confs,q=s.q.toLowerCase(); return D.conferences.filter(c=>{ if(s.year!=='all'&&c.year!==s.year)return false; if(s.type!=='all'&&c.type!==s.type)return false; if(s.tags.length){ const have=(c.focus||[]).map(t=>t.toLowerCase()); if(!this.tagsMatch(s.tags,s.tagsMode,have))return false; } if(q){ const hay=(c.name+' '+c.loc+' '+c.series+' '+(c.focus||[]).join(' ')+' '+(c.people||[]).map(p=>p.n).join(' ')).toLowerCase(); if(hay.indexOf(q)<0)return false; } return true; }); }
  filterFellows(){ const D=this.data(),s=this.state.fellows,q=s.q.toLowerCase(); return D.fellowships.filter(f=>{ if(s.tags.length){ const have=(f.focus_areas||[]).map(t=>t.toLowerCase()); if(!this.tagsMatch(s.tags,s.tagsMode,have))return false; } if(!q)return true; return (f.name+' '+(f.program_full||'')+' '+(f.funder||'')+' '+(f.focus||'')+' '+(f.status||'')+' '+(f.focus_areas||[]).join(' ')+' '+(f.people||[]).map(p=>p.n+' '+(p.note||'')).join(' ')).toLowerCase().indexOf(q)>=0; }); }
  filterDatasets(){ const D=this.data(),s=this.state.datasets,q=s.q.toLowerCase(); return D.datasets.filter(d=>{ if(s.year!=='all'&&String(d.year||'')!==s.year)return false; if(s.tags.length){ const have=(d.tags||[]).map(t=>t.toLowerCase()); if(!this.tagsMatch(s.tags,s.tagsMode,have))return false; } if(!q)return true; return (d.name+' '+(d.desc||'')+' '+(d.tags||[]).join(' ')+' '+(d.year||'')+' '+(d.people||[]).join(' ')).toLowerCase().indexOf(q)>=0; }); }

  // ---------- OPTIONS ----------
  opts(){ if(this._opts)return this._opts; const D=this.data();
    const pcats=this.uniq(D.papers.map(p=>p.cat)).sort();
    const pyears=this.uniq(D.papers.map(p=>(p.date||'').slice(0,4)).filter(y=>y)).sort().reverse();
    const porgs=this.uniq(D.policies.map(p=>p.org)).sort();
    const polyears=this.uniq(D.policies.map(p=>(p.date||'').slice(0,4)).filter(y=>y)).sort().reverse();
    const cyears=this.uniq(D.conferences.map(c=>c.year).filter(Boolean)).sort().reverse();
    const ctypes=this.uniq(D.conferences.map(c=>c.type).filter(Boolean)).sort();
    const dyears=this.uniq(D.datasets.map(d=>String(d.year||'')).filter(Boolean)).sort().reverse();
    this._opts={pcats,pyears,porgs,polyears,cyears,ctypes,dyears}; return this._opts; }
  mkSel(key,value,options){ return {value,options,onChange:e=>this.setCur(key,e.target.value)}; }
  yearOpts(arr,undated){ const o=[{v:'all',label:'All years'}].concat(arr.map(y=>({v:y,label:y}))); if(undated)o.push({v:'undated',label:'Undated'}); return o; }

  // ---------- DETAIL BUILDERS ----------
  dLede(t){ return {isLede:true,text:t}; }
  dFact(l,v){ return {isFact:true,label:l,value:v}; }
  dChips(l,items){ return {isChips:true,label:l,items}; }
  dTags(l,items){ return {isTags:true,label:l,items}; }
  dLinks(items){ return {isLinks:true,items}; }
  linkList(pairs){ return pairs.filter(p=>p[1]).map(p=>({label:p[0],href:p[1]})); }

  personDetail(p){ const cc=this.props.colorCodeKinds??true; const K=this.KIND.person; const main=[],side=[];
    if(p.role)main.push(this.dFact('Role',p.role));
    if(p.blurb)main.push(this.dLede(p.blurb));
    if(p.notable)main.push(this.dFact('Notable work',p.notable));
    if(p.tools)main.push(this.dFact('Tools / open source',p.tools));
    const bms=(p.benchmarks||'').split(';').map(x=>x.trim()).filter(Boolean); if(bms.length)main.push(this.dChips('Benchmarks',bms.map(b=>({label:b,sub:'',onClick:()=>this.gotoTab('datasets',b)}))));
    if(p.frameworks)main.push(this.dFact('Standards',p.frameworks));
    if(p.talks)main.push(this.dFact('Talks',p.talks));
    if(p.awards)main.push(this.dFact('Awards',p.awards));
    if(p.affiliations)main.push(this.dFact('Academic affiliation',p.affiliations));
    if(p.confs&&p.confs.length)main.push(this.dChips('Conferences',this.navChips(p.confs,'confs')));
    if(p.fellows&&p.fellows.length)main.push(this.dChips('Fellowships',this.navChips(p.fellows,'fellows')));
    let paps=(p.ptab||[]).map(t=>({label:t.length>46?t.slice(0,44)+'\u2026':t,sub:'',onClick:()=>this.gotoTab('papers',t)})); if(p.inAuthors)paps.push({label:'Papers by '+p.name.split(' ')[0],sub:'',onClick:()=>this.gotoTab('papers',p.name)}); if(paps.length)main.push(this.dChips('In the Papers tab',paps));
    if(!main.length)main.push(this.dLede('No further detail recorded for this researcher.'));
    side.push(this.dFact('Category',p.category));
    side.push(this.dFact('Organization',p.org));
    if(p.currentOrg&&p.currentOrg!==p.org)side.push(this.dFact('Now at',p.currentOrg));
    const foc=(p.focus||'').split(';').map(x=>x.trim()).filter(Boolean); if(foc.length)side.push(this.dTags('Focus',foc));
    const links=this.linkList([['Website',p.site],['LinkedIn',p.linkedin],['X',p.x]]); if(links.length)side.push(this.dLinks(links));
    return { kindLabel:'Researcher', kindColor:cc?K.color:'#8a8272', title:p.name, titleHref:'', hasLink:false, noLink:true, subtitle:p.org, badges:p.isNew?[this.badge('new','green')]:[], main, side }; }

  orgDetail(o){ const cc=this.props.colorCodeKinds??true; const K=this.KIND.org; const main=[],side=[];
    if(o.people.length)main.push(this.dChips('In the People directory ('+o.people.length+')',this.peopleChips(o.people)));
    else main.push(this.dLede('No tracked researchers recorded at this organization.'));
    side.push(this.dFact('Group',o.group)); side.push(this.dFact('Tracked researchers',String(o.people.length)));
    return { kindLabel:'Organization', kindColor:cc?K.color:'#8a8272', title:o.name, titleHref:'', hasLink:false, noLink:true, subtitle:o.group, badges:[], main, side }; }

  paperDetail(p){ const cc=this.props.colorCodeKinds??true; const K=this.KIND.paper; const main=[],side=[];
    if(p.summary)main.push(this.dLede(p.summary)); else main.push(this.dLede('No summary recorded.'));
    if((p.tags||[]).length)main.push(this.dTags('Tags',p.tags));
    if((p.rp||[]).length)main.push(this.dChips('In the People directory ('+p.rp.length+')',this.peopleChips(p.rp)));
    side.push(this.dFact('Wiki category',p.cat+(p.sub?' \u2192 '+p.sub:'')));
    if(p.date)side.push(this.dFact('Date',p.date));
    side.push(this.dFact('Type',p.kind==='benchmark'?'Benchmark':'Paper'));
    if(p.dataset)side.push(this.dFact('Matched dataset',p.dataset));
    if(p.url)side.push(this.dLinks([{label:'View paper',href:p.url}]));
    const badges=[]; if(p.kind==='benchmark')badges.push(this.badge('benchmark','teal')); if(p.dataset)badges.push(this.badge('dataset','purple'));
    return { kindLabel:p.kind==='benchmark'?'Benchmark':'Paper', kindColor:cc?K.color:'#8a8272', title:p.title, titleHref:p.url||'', hasLink:!!p.url, noLink:!p.url, subtitle:this.join([p.authors,p.date]), badges, main, side }; }

  policyDetail(p){ const cc=this.props.colorCodeKinds??true; const K=this.KIND.policy; const main=[],side=[];
    main.push(this.dLede(p.summary||'No summary recorded.'));
    side.push(this.dFact('Developer',p.org)); if(p.sub)side.push(this.dFact('Section',p.sub)); if(p.date)side.push(this.dFact('Date',p.date));
    side.push(this.dFact('Type',p.kind==='framework'?'Framework':'Commentary'));
    if(p.url)side.push(this.dLinks([{label:'View document',href:p.url}]));
    return { kindLabel:'Policy', kindColor:cc?K.color:'#8a8272', title:p.title, titleHref:p.url||'', hasLink:!!p.url, noLink:!p.url, subtitle:this.join([p.org,p.date]), badges:[this.badge(p.kind==='framework'?'framework':'commentary',p.kind==='framework'?'purple':'gray')], main, side }; }

  confDetail(c){ const cc=this.props.colorCodeKinds??true; const K=this.KIND.conf; const main=[],side=[];
    if(c.rec)main.push(this.dFact('Why it matters',c.rec));
    if(c.notes)main.push(this.dFact('Notes',c.notes));
    if(c.people&&c.people.length)main.push(this.dChips('Roster participants ('+c.people.length+')',this.peopleChips(c.people)));
    else main.push(this.dLede('No roster participants recorded for this conference.'));
    if(c.year)side.push(this.dFact('Year',c.year)); if(c.loc)side.push(this.dFact('Location',c.loc)); if(c.type)side.push(this.dFact('Type',c.type)); if(c.pri)side.push(this.dFact('Priority',c.pri)); if(c.series)side.push(this.dFact('Series',c.series));
    if((c.focus||[]).length)side.push(this.dTags('Focus',c.focus));
    if(c.url)side.push(this.dLinks([{label:'Website',href:c.url}]));
    return { kindLabel:'Conference', kindColor:cc?K.color:'#8a8272', title:c.name, titleHref:c.url||'', hasLink:!!c.url, noLink:!c.url, subtitle:this.join([c.year,c.loc,c.type]), badges:c.pri?[this.badge(c.pri+' priority',this.priTone(c.pri))]:[], main, side }; }

  fellowDetail(f){ const cc=this.props.colorCodeKinds??true; const K=this.KIND.fellow; const main=[],side=[];
    if(f.program_full&&f.program_full!==f.name)main.push(this.dFact('Program',f.program_full));
    if(f.focus)main.push(this.dLede(f.focus));
    if(f.funding)main.push(this.dFact('Funding',f.funding));
    if(f.people&&f.people.length)main.push(this.dChips('Roster participants ('+f.people.length+')',this.peopleChips(f.people)));
    if(f.confs&&f.confs.length)main.push(this.dChips('Seen at conferences',this.navChips(f.confs,'confs')));
    if(f.funder)side.push(this.dFact('Funder',f.funder)); if(f.status)side.push(this.dFact('Status',f.status)); if(f.deadline)side.push(this.dFact('Deadline',f.deadline));
    if((f.focus_areas||[]).length)side.push(this.dTags('Focus areas',f.focus_areas));
    if(f.link)side.push(this.dLinks([{label:'Website',href:f.link}]));
    return { kindLabel:'Fellowship', kindColor:cc?K.color:'#8a8272', title:f.name, titleHref:f.link||'', hasLink:!!f.link, noLink:!f.link, subtitle:this.join([f.funder,f.status]), badges:f.status?[this.badge(f.status,this.statusTone(f.status))]:[], main, side }; }

  datasetDetail(d){ const cc=this.props.colorCodeKinds??true; const K=this.KIND.dataset; const main=[],side=[]; const url=d.url||('https://www.google.com/search?q='+encodeURIComponent('"'+d.name+'" AI benchmark dataset'));
    if(d.desc)main.push(this.dLede(d.desc)); else main.push(this.dLede('No description recorded.'));
    if(d.people&&d.people.length)main.push(this.dChips('Associated researchers ('+d.people.length+')',this.peopleChips(d.people)));
    if(d.year)side.push(this.dFact('Year',String(d.year)));
    if((d.tags||[]).length)side.push(this.dTags('Tags',d.tags));
    side.push(this.dLinks([{label:d.url?'View dataset':'Web search',href:url}]));
    return { kindLabel:'Dataset', kindColor:cc?K.color:'#8a8272', title:d.name, titleHref:url, hasLink:true, noLink:false, subtitle:this.join([d.year, d.people.length+' researcher'+(d.people.length===1?'':'s')]), badges:[], main, side }; }

  buildDetail(sel){ const it=sel.item; switch(sel.type){ case 'person':return this.personDetail(it); case 'org':return this.orgDetail(it); case 'paper':return this.paperDetail(it); case 'policy':return this.policyDetail(it); case 'conf':return this.confDetail(it); case 'fellow':return this.fellowDetail(it); case 'dataset':return this.datasetDetail(it); } return null; }

  // ---------- STATS ----------
  barBlock(title,src,obj,max){ let e=Object.keys(obj).map(k=>[k,obj[k]]); e.sort((a,b)=>b[1]-a[1]); if(max)e=e.slice(0,max); const top=Math.max.apply(null,e.map(x=>x[1]).concat([1])); return { title, src, isBar:true, entries:e.map(x=>({label:x[0],valLabel:this.fmtN(x[1]),pct:Math.max(2,Math.round(100*x[1]/top))+'%'})) }; }
  colBlock(title,src,obj){ const ks=Object.keys(obj); const top=Math.max.apply(null,ks.map(k=>obj[k]).concat([1])); return { title, src, isCol:true, entries:ks.map(k=>({label:k,valLabel:this.fmtN(obj[k]),pct:Math.max(3,Math.round(130*obj[k]/top))+'px'})) }; }
  buildStats(){ const D=this.data(),S=D.stats; if(!S)return {cards:[],blocks:[],note:'Snapshot unavailable.'}; const snap='snapshot '+S.generated;
    const sum=o=>Object.keys(o).reduce((a,k)=>a+o[k],0);
    const cards=[ {v:this.fmtN(S.nSources),l:'sources in manifest'}, {v:String(Object.keys(S.years).length),l:'publication years'}, {v:this.fmtN(sum(S.tokensByCat)),l:'tokens (by category)'}, {v:String(Object.keys(S.sourceType).length),l:'source types'}, {v:String(Object.keys(S.risk).length),l:'risk categories'} ];
    const blocks=[ this.barBlock('Source types',snap,S.sourceType), this.barBlock('Risk categories',snap,S.risk,12), this.barBlock('Tokens by category',snap,S.tokensByCat,12), this.barBlock('Files by category',snap,S.filesByCat,12), this.colBlock('Publication year of sources',snap,S.years), this.colBlock('Log activity by month',snap,S.logByMonth) ];
    const hp=Object.keys(S.health).map(k=>{ const v=S.health[k]; const t=v?this.TONE.amber:this.TONE.green; return {label:v+' '+k, bg:t.bg, color:t.color, border:v?'#e8d3a8':'#c3e0cd'}; });
    blocks.push({ title:'Metadata health', src:snap, isPills:true, pills:hp });
    const lk=Object.keys(S.logByKind).map(k=>({label:k+' '+S.logByKind[k], bg:'#f0ece2', color:'#6a6355', border:'#e0d8c8'}));
    blocks.push({ title:'Log entries by kind', src:snap, isPills:true, pills:lk });
    return { cards, blocks, note:'Corpus snapshot from manifest.csv + log.md \u00b7 '+S.generated }; }

  renderVals(){
    const D=this.data();
    const safe={ loading:!D, tabs:[], rows:[], groups:[], selects:[], chips:{has:false,items:[]}, stats:{cards:[],blocks:[],note:''}, mastheadMeta: D?'':'Loading directory\u2026', isBrowse:true, isDetail:false, isRowsMode:false, isGroupsMode:false, isStatsMode:false, hasChips:false, isEmpty:false, searchPlaceholder:'', query:'', countLabel:'', onSearch:()=>{}, onBack:()=>this.back(), backLabel:'', detail:{main:[],side:[],badges:[],hasSide:false,hasBadges:false,hasLink:false,noLink:true,kindColor:'#a75a38',title:'',subtitle:'',kindLabel:''} };
    if(!D) return safe;

    const st=this.state, tab=st.tab, cc=this.props.colorCodeKinds??true;
    const tabsDef=[['people','People',D.count],['orgs','Organizations',D.orgs.length],['papers','Papers',D.papers.length],['policy','Policy',D.policies.length],['confs','Conferences',D.conferences.length],['fellows','Fellowships',D.fellowships.length],['datasets','Datasets',D.datasets.length],['stats','Stats','']];
    const tabs=tabsDef.map(t=>({ label:t[1], count:t[2]===''?'':String(t[2]), color: tab===t[0]?'#232019':'#8a8272', border: tab===t[0]?'#a75a38':'transparent', onClick:()=>this.setTabFn(t[0]) }));
    const mastheadMeta=D.count+' researchers \u00b7 '+D.orgs.length+' orgs \u00b7 '+D.papers.length+' papers \u00b7 '+D.policies.length+' policies \u00b7 '+D.conferences.length+' conferences \u00b7 '+D.fellowships.length+' fellowships \u00b7 '+D.datasets.length+' datasets \u2014 snapshot '+D.snapshot;

    const out={ ...safe, loading:false, tabs, mastheadMeta, onBack:()=>this.back() };

    if(st.sel){ out.isDetail=true; out.isBrowse=false; const d=this.buildDetail(st.sel)||safe.detail; out.detail={ ...d, hasSide:(d.side&&d.side.length>0), hasBadges:(d.badges&&d.badges.length>0) }; out.backLabel='Back to '+(tabsDef.find(t=>t[0]===tab)||[,'directory'])[1]; return out; }

    out.isBrowse=true; out.isDetail=false;
    const cur=st[tab]||{}; out.query=cur.q||''; out.onSearch=e=>this.setCur('q',e.target.value);
    const O=this.opts();
    const PH={people:'Search name, org, focus, or notable work',orgs:'Search organizations or people',papers:'Search title, author, or tag',policy:'Search policies, developers, or text',confs:'Search conferences, locations, or people',fellows:'Search programs or people',datasets:'Search benchmarks / datasets or people',stats:''};
    out.searchPlaceholder=PH[tab]||'Search';

    if(tab==='stats'){ out.isStatsMode=true; out.stats=this.buildStats(); out.searchPlaceholder=''; out.selects=[]; out.hasChips=false; out.query=''; out.onSearch=()=>{}; out.countLabel=''; return out; }

    if(tab==='people'){
      const list=this.filterPeople(); out.rows=list.map(p=>this.personRow(p)); out.isRowsMode=true; out.isEmpty=list.length===0;
      out.selects=[ this.mkSel('cat',cur.cat,[{v:'all',label:'All categories'}].concat(D.categories.map(c=>({v:c,label:c})))), this.mkSel('sort',cur.sort,[{v:'name',label:'Sort: name'},{v:'org',label:'Sort: org'},{v:'cat',label:'Sort: category'}]) ];
      out.chips=this.buildChips('people','focus',D.focusTags); out.hasChips=true; out.countLabel=list.length+' of '+D.people.length;
    } else if(tab==='orgs'){
      const list=this.filterOrgs(); out.rows=list.map(o=>this.orgRow(o)); out.isRowsMode=true; out.isEmpty=list.length===0;
      out.selects=[ this.mkSel('group',cur.group,[{v:'all',label:'All groups'}].concat(D.orgGroups.map(g=>({v:g,label:g})))) ];
      out.hasChips=false; out.countLabel=list.length+' of '+D.orgs.length;
    } else if(tab==='papers'){
      const list=this.filterPapers(); out.rows=list.map(p=>this.paperRow(p)); out.isRowsMode=true; out.isEmpty=list.length===0;
      out.selects=[ this.mkSel('cat',cur.cat,[{v:'all',label:'All wiki categories'}].concat(O.pcats.map(c=>({v:c,label:c})))), this.mkSel('kind',cur.kind,[{v:'all',label:'Papers + benchmarks'},{v:'paper',label:'Papers only'},{v:'benchmark',label:'Benchmarks only'}]), this.mkSel('year',cur.year,this.yearOpts(O.pyears,true)), this.mkSel('sort',cur.sort,[{v:'date',label:'Sort: newest'},{v:'title',label:'Sort: title'}]) ];
      out.chips=this.buildChips('papers','tags',D.paperTags); out.hasChips=true; out.countLabel=list.length+' of '+D.papers.length;
    } else if(tab==='policy'){
      const g=this.filterPolicyGroups(); out.groups=g.groups; out.isGroupsMode=true; out.isEmpty=g.total===0;
      out.selects=[ this.mkSel('org',cur.org,[{v:'all',label:'All developers'}].concat(O.porgs.map(o=>({v:o,label:o})))), this.mkSel('kind',cur.kind,[{v:'all',label:'Frameworks + commentary'},{v:'framework',label:'Frameworks only'},{v:'commentary',label:'Commentary only'}]), this.mkSel('year',cur.year,this.yearOpts(O.polyears,true)) ];
      out.hasChips=false; out.countLabel=g.total+' of '+D.policies.length;
    } else if(tab==='confs'){
      const list=this.filterConfs(); out.rows=list.map(c=>this.confRow(c)); out.isRowsMode=true; out.isEmpty=list.length===0;
      out.selects=[ this.mkSel('year',cur.year,[{v:'all',label:'All years'}].concat(O.cyears.map(y=>({v:y,label:y})))), this.mkSel('type',cur.type,[{v:'all',label:'All types'}].concat(O.ctypes.map(t=>({v:t,label:t})))) ];
      out.chips=this.buildChips('confs','tags',D.confTags); out.hasChips=true; out.countLabel=list.length+' of '+D.conferences.length;
    } else if(tab==='fellows'){
      const list=this.filterFellows(); out.rows=list.map(f=>this.fellowRow(f)); out.isRowsMode=true; out.isEmpty=list.length===0;
      out.selects=[]; out.chips=this.buildChips('fellows','tags',D.fellowTags); out.hasChips=true; out.countLabel=list.length+' of '+D.fellowships.length+' programs';
    } else if(tab==='datasets'){
      const list=this.filterDatasets(); out.rows=list.map(d=>this.datasetRow(d)); out.isRowsMode=true; out.isEmpty=list.length===0;
      out.selects=[ this.mkSel('year',cur.year,[{v:'all',label:'All years'}].concat(O.dyears.map(y=>({v:y,label:y})))) ];
      out.chips=this.buildChips('datasets','tags',D.datasetTags); out.hasChips=true; out.countLabel=list.length+' of '+D.datasets.length;
    }
    return out;
  }
}

/* ---------------- render / DOM layer (vanilla port of the DC template) ---------------- */
function hchip(o,fn){ return o; }
function mainBlock(bl,h){
  if(bl.isLede) return '<p style="font-family:\'Spectral\',Georgia,serif;font-size:16.5px;line-height:1.62;color:#3d382f;margin:0 0 20px;">'+esc(bl.text)+'</p>';
  if(bl.isFact) return '<div style="margin:0 0 16px;"><div style="font-family:\'IBM Plex Mono\',monospace;font-size:9.5px;letter-spacing:0.11em;text-transform:uppercase;color:#a49b88;">'+esc(bl.label)+'</div><div style="font-size:14.5px;color:#2f2b23;line-height:1.5;margin-top:4px;">'+esc(bl.value)+'</div></div>';
  if(bl.isChips){ var items=bl.items.map(function(it){ return '<span class="aisd-navchip" data-h="'+h(it.onClick)+'" style="display:inline-flex;gap:5px;align-items:baseline;font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;color:#5b5648;background:#efe8db;border:1px solid #e0d8c8;border-radius:999px;padding:4px 11px;cursor:pointer;">'+esc(it.label)+'<span style="opacity:0.5;font-size:10px;">'+esc(it.sub)+'</span></span>'; }).join('');
    return '<div style="margin:0 0 18px;"><div style="font-family:\'IBM Plex Mono\',monospace;font-size:9.5px;letter-spacing:0.11em;text-transform:uppercase;color:#a49b88;">'+esc(bl.label)+'</div><div style="display:flex;flex-wrap:wrap;gap:7px;margin-top:10px;">'+items+'</div></div>'; }
  if(bl.isTags){ var tg=bl.items.map(function(t){ return '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;color:#7d766a;background:#ebe3d3;border-radius:5px;padding:2px 9px;">'+esc(t)+'</span>'; }).join('');
    return '<div style="margin:0 0 18px;"><div style="font-family:\'IBM Plex Mono\',monospace;font-size:9.5px;letter-spacing:0.11em;text-transform:uppercase;color:#a49b88;">'+esc(bl.label)+'</div><div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;">'+tg+'</div></div>'; }
  return '';
}
function sideBlock(bl,h){
  if(bl.isFact) return '<div style="margin-bottom:16px;"><div style="font-family:\'IBM Plex Mono\',monospace;font-size:9px;letter-spacing:0.11em;text-transform:uppercase;color:#a49b88;">'+esc(bl.label)+'</div><div style="font-size:13.5px;color:#2f2b23;margin-top:4px;line-height:1.45;">'+esc(bl.value)+'</div></div>';
  if(bl.isTags){ var tg=bl.items.map(function(t){ return '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:10px;color:#7d766a;background:#ebe3d3;border-radius:5px;padding:2px 8px;">'+esc(t)+'</span>'; }).join('');
    return '<div style="margin-bottom:16px;"><div style="font-family:\'IBM Plex Mono\',monospace;font-size:9px;letter-spacing:0.11em;text-transform:uppercase;color:#a49b88;margin-bottom:8px;">'+esc(bl.label)+'</div><div style="display:flex;flex-wrap:wrap;gap:6px;">'+tg+'</div></div>'; }
  if(bl.isLinks){ var lk=bl.items.map(function(it){ return '<a class="aisd-sidelink" href="'+esc(it.href)+'" target="_blank" rel="noopener" style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;text-decoration:none;color:#a75a38;border:1px solid #e0cfc3;border-radius:8px;padding:7px 13px;display:inline-block;">'+esc(it.label)+'</a>'; }).join('');
    return '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;">'+lk+'</div>'; }
  return '';
}
function badgePill(b,fs,pad,ls){ return '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:'+fs+';letter-spacing:'+ls+';text-transform:uppercase;padding:'+pad+';border-radius:999px;background:'+b.bg+';color:'+b.color+';">'+esc(b.label)+'</span>'; }
function detailHTML(v,h){
  var d=v.detail,o=[];
  o.push('<div style="max-width:1180px;margin:0 auto;padding:24px 28px 96px;animation:aisdFade .25s ease;">');
  o.push('<span class="aisd-back" data-h="'+h(v.onBack)+'" style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;letter-spacing:0.06em;text-transform:uppercase;color:#8a8272;cursor:pointer;">← '+esc(v.backLabel)+'</span>');
  o.push('<div style="display:flex;flex-wrap:wrap;gap:44px;margin-top:22px;align-items:flex-start;">');
  o.push('<div style="flex:1;min-width:340px;">');
  o.push('<div style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;letter-spacing:0.16em;text-transform:uppercase;color:'+d.kindColor+';">'+esc(d.kindLabel)+'</div>');
  if(d.hasLink) o.push('<a class="aisd-title-link" href="'+esc(d.titleHref)+'" target="_blank" rel="noopener" style="font-family:\'Spectral\',Georgia,serif;font-size:31px;font-weight:600;color:#232019;line-height:1.1;margin:9px 0 0;display:block;text-decoration:none;">'+esc(d.title)+'</a>');
  else o.push('<h2 style="font-family:\'Spectral\',Georgia,serif;font-size:31px;font-weight:600;color:#232019;line-height:1.1;margin:9px 0 0;">'+esc(d.title)+'</h2>');
  o.push('<div style="font-size:14.5px;color:#6f685c;margin-top:9px;line-height:1.5;">'+esc(d.subtitle)+'</div>');
  if(d.hasBadges){ o.push('<div style="display:flex;flex-wrap:wrap;gap:7px;margin-top:13px;">'); d.badges.forEach(function(b){ o.push(badgePill(b,'9.5px','3px 9px','0.05em')); }); o.push('</div>'); }
  o.push('<div style="height:1px;background:#e4dece;margin:24px 0;"></div>');
  d.main.forEach(function(bl){ o.push(mainBlock(bl,h)); });
  o.push('</div>');
  if(d.hasSide){
    o.push('<div style="width:290px;flex-shrink:0;"><div style="border:1px solid #e4dece;border-radius:14px;background:#fdfbf6;padding:22px 24px;">');
    d.side.forEach(function(bl){ o.push(sideBlock(bl,h)); });
    o.push('</div></div>');
  }
  o.push('</div></div>');
  return o.join('');
}
function rowHTML(row,h){
  var bad=row.badges.map(function(b){ return '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:9px;letter-spacing:0.05em;text-transform:uppercase;padding:2px 7px;border-radius:999px;background:'+b.bg+';color:'+b.color+';">'+esc(b.label)+'</span>'; }).join('');
  var tags=row.hasTags?('<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:9px;">'+row.tags.map(function(t){ return '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:10px;color:#7d766a;background:#ebe3d3;border-radius:5px;padding:2px 8px;">'+esc(t)+'</span>'; }).join('')+'</div>'):'';
  return '<div class="aisd-row" data-h="'+h(row.onClick)+'" style="display:grid;grid-template-columns:46px minmax(0,1fr) auto;gap:18px;align-items:start;padding:17px 8px;border-top:1px solid #e4dece;cursor:pointer;">'
    +'<div style="width:46px;height:46px;border-radius:11px;display:flex;align-items:center;justify-content:center;font-family:\'IBM Plex Mono\',monospace;font-weight:500;font-size:13px;background:'+row.monoBg+';color:'+row.monoColor+';">'+esc(row.monogram)+'</div>'
    +'<div style="min-width:0;"><div style="display:flex;flex-wrap:wrap;gap:9px;align-items:baseline;"><span style="font-family:\'Spectral\',Georgia,serif;font-size:19.5px;font-weight:500;color:#232019;line-height:1.2;">'+esc(row.title)+'</span><span style="font-family:\'IBM Plex Mono\',monospace;font-size:9.5px;letter-spacing:0.1em;text-transform:uppercase;color:'+row.kindColor+';padding-top:2px;">'+esc(row.kindLabel)+'</span>'+bad+'</div>'
    +'<div style="font-size:13px;color:#6f685c;margin-top:5px;line-height:1.45;">'+esc(row.subtitle)+'</div>'+tags+'</div>'
    +'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:10px;color:#98917f;text-align:right;white-space:nowrap;padding-top:5px;max-width:160px;overflow:hidden;text-overflow:ellipsis;">'+esc(row.meta)+'</div>'
    +'</div>';
}
function groupHTML(g,h){
  var o=[];
  o.push('<div style="border:1px solid #e4dece;border-radius:16px;background:#fdfbf6;padding:22px 26px 24px;margin-top:16px;">');
  o.push('<div style="display:flex;align-items:center;gap:14px;"><div style="width:44px;height:44px;border-radius:11px;display:flex;align-items:center;justify-content:center;font-family:\'IBM Plex Mono\',monospace;font-weight:500;font-size:13px;background:'+g.monoBg+';color:'+g.monoColor+';flex-shrink:0;">'+esc(g.monogram)+'</div><div style="flex:1;font-family:\'Spectral\',Georgia,serif;font-size:21px;font-weight:600;color:#232019;">'+esc(g.org)+'</div><span style="font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;color:#98917f;white-space:nowrap;">'+esc(g.countLabel)+'</span></div>');
  o.push('<div class="aisd-primary" data-h="'+h(g.onPrimary)+'" style="display:flex;align-items:center;gap:16px;margin-top:16px;padding:16px 20px;border:1px solid #e6ddc9;border-radius:12px;background:#f8f3e7;cursor:pointer;"><div style="flex:1;min-width:0;"><div style="display:flex;flex-wrap:wrap;gap:10px;align-items:baseline;"><span style="font-family:\'Spectral\',Georgia,serif;font-size:19px;font-weight:600;color:#232019;line-height:1.25;">'+esc(g.primaryTitle)+'</span><span style="font-family:\'IBM Plex Mono\',monospace;font-size:9px;letter-spacing:0.05em;text-transform:uppercase;padding:2px 8px;border-radius:999px;background:'+g.primaryBadgeBg+';color:'+g.primaryBadgeColor+';">'+esc(g.primaryBadgeLabel)+'</span><span style="font-family:\'IBM Plex Mono\',monospace;font-size:8.5px;letter-spacing:0.08em;text-transform:uppercase;color:#9a4f2f;background:#f0e0d6;padding:2px 8px;border-radius:999px;">latest</span></div></div><span style="font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:#6f685c;white-space:nowrap;">'+esc(g.primaryDate)+'</span><span style="color:#a75a38;font-size:17px;line-height:1;">→</span></div>');
  if(g.hasVersions){
    o.push('<div style="font-family:\'IBM Plex Mono\',monospace;font-size:9px;letter-spacing:0.12em;text-transform:uppercase;color:#a49b88;margin:18px 0 10px;">Earlier versions &amp; commentary</div><div style="display:flex;flex-wrap:wrap;gap:8px;">');
    g.versions.forEach(function(vv){ o.push('<span class="aisd-navchip" data-h="'+h(vv.onClick)+'" style="display:inline-flex;gap:9px;align-items:baseline;white-space:nowrap;font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;color:#5b5648;background:#efe8db;border:1px solid #e0d8c8;border-radius:8px;padding:6px 12px;cursor:pointer;">'+esc(vv.label)+'<span style="opacity:0.55;font-size:10.5px;">'+esc(vv.dateLabel)+'</span></span>'); });
    o.push('</div>');
  }
  o.push('</div>');
  return o.join('');
}
function statsHTML(S){
  var o=[];
  o.push('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:24px 0 6px;">');
  S.cards.forEach(function(c){ o.push('<div style="border:1px solid #e4dece;border-radius:12px;background:#fdfbf6;padding:16px 18px;"><div style="font-family:\'Spectral\',Georgia,serif;font-size:26px;font-weight:600;color:#232019;letter-spacing:-0.01em;">'+esc(c.v)+'</div><div style="font-family:\'IBM Plex Mono\',monospace;font-size:10px;color:#98917f;margin-top:3px;letter-spacing:0.03em;">'+esc(c.l)+'</div></div>'); });
  o.push('</div>');
  o.push('<div style="font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;color:#a49b88;margin:8px 0 16px;">'+esc(S.note)+'</div>');
  o.push('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px;">');
  S.blocks.forEach(function(b){
    o.push('<div style="border:1px solid #e4dece;border-radius:12px;background:#fdfbf6;padding:18px 20px;">');
    o.push('<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px;"><span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#4a463d;">'+esc(b.title)+'</span><span style="font-family:\'IBM Plex Mono\',monospace;font-size:9.5px;color:#a49b88;">'+esc(b.src)+'</span></div>');
    if(b.isBar){ b.entries.forEach(function(e){ o.push('<div style="display:flex;align-items:center;gap:10px;padding:3px 0;font-size:12px;"><span style="width:44%;flex:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#4a463d;">'+esc(e.label)+'</span><span style="flex:1;height:12px;background:#eae3d4;border-radius:6px;overflow:hidden;"><span style="display:block;height:100%;border-radius:6px;background:#a75a38;width:'+e.pct+';"></span></span><span style="width:42px;text-align:right;font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#7d766a;">'+esc(e.valLabel)+'</span></div>'); }); }
    else if(b.isCol){ o.push('<div style="display:flex;align-items:flex-end;gap:2px;margin-top:12px;padding-bottom:2px;">'); b.entries.forEach(function(e){ o.push('<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:4px;min-width:0;"><span style="font-family:\'IBM Plex Mono\',monospace;font-size:8.5px;color:#7d766a;">'+esc(e.valLabel)+'</span><span style="width:100%;background:#a75a38;border-radius:2px 2px 0 0;height:'+e.pct+';min-height:3px;"></span><span style="font-size:8.5px;color:#98917f;transform:rotate(-45deg);transform-origin:top center;white-space:nowrap;margin-top:4px;height:24px;">'+esc(e.label)+'</span></div>'); }); o.push('</div>'); }
    else if(b.isPills){ o.push('<div style="display:flex;flex-wrap:wrap;gap:6px;">'); b.pills.forEach(function(p){ o.push('<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;border-radius:999px;padding:4px 11px;border:1px solid '+p.border+';background:'+p.bg+';color:'+p.color+';">'+esc(p.label)+'</span>'); }); o.push('</div>'); }
    o.push('</div>');
  });
  o.push('</div>');
  return o.join('');
}
function browseHTML(v,h){
  var o=[];
  o.push('<div style="max-width:1180px;margin:0 auto;padding:6px 28px 0;"><div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;padding:16px 0 14px;border-bottom:1px solid #e4dece;">');
  o.push('<input id="aisd-q" type="text" value="'+esc(v.query)+'" data-inp="'+h(v.onSearch)+'" placeholder="'+esc(v.searchPlaceholder)+'" style="flex:1;min-width:240px;border:none;background:transparent;border-bottom:1.5px solid #d3ccbc;padding:8px 2px;font-size:17px;font-family:\'Spectral\',Georgia,serif;color:#232019;outline:none;">');
  v.selects.forEach(function(sel){
    var opts=sel.options.map(function(op){ return '<option value="'+esc(op.v)+'"'+(op.v===sel.value?' selected':'')+'>'+esc(op.label)+'</option>'; }).join('');
    o.push('<select data-ch="'+h(sel.onChange)+'" style="border:1px solid #d3ccbc;background:#fdfbf6;border-radius:8px;padding:8px 10px;font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#4a463d;cursor:pointer;max-width:230px;">'+opts+'</select>');
  });
  o.push('<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#98917f;white-space:nowrap;">'+esc(v.countLabel)+'</span>');
  o.push('</div></div>');
  if(v.hasChips){
    var c=v.chips;
    o.push('<div style="max-width:1180px;margin:0 auto;padding:26px 28px 24px;"><div style="display:flex;flex-wrap:wrap;gap:9px 7px;align-items:center;">');
    o.push('<span data-h="'+h(c.onClear)+'" style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;padding:5px 12px;border-radius:999px;border:1px solid '+c.clearBorder+';background:'+c.clearBg+';color:'+c.clearColor+';cursor:pointer;">All</span>');
    c.items.forEach(function(ci){ o.push('<span data-h="'+h(ci.onClick)+'" style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;padding:5px 11px;border-radius:999px;border:1px solid '+ci.border+';background:'+ci.bg+';color:'+ci.color+';cursor:pointer;">'+esc(ci.label)+' <span style="opacity:0.5;font-size:9.5px;">'+esc(ci.count)+'</span></span>'); });
    if(c.showExpand) o.push('<span data-h="'+h(c.onExpand)+'" style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;padding:5px 12px;border-radius:999px;background:#ece5d6;color:#6f685c;cursor:pointer;font-weight:500;">'+esc(c.expandLabel)+'</span>');
    if(c.showMode) o.push('<span data-h="'+h(c.onMode)+'" style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;padding:5px 12px;border-radius:999px;background:#efe1d8;color:#9a4f2f;cursor:pointer;font-weight:500;">'+esc(c.modeLabel)+'</span>');
    o.push('</div></div>');
  }
  o.push('<div style="max-width:1180px;margin:0 auto;padding:2px 28px 96px;">');
  if(v.isRowsMode){
    v.rows.forEach(function(row){ o.push(rowHTML(row,h)); });
    if(v.isEmpty) o.push('<div style="text-align:center;color:#a49b88;padding:64px 20px;font-family:\'Spectral\',Georgia,serif;font-size:17px;">No entries match these filters.</div>');
  } else if(v.isGroupsMode){
    v.groups.forEach(function(g){ o.push(groupHTML(g,h)); });
    if(v.isEmpty) o.push('<div style="text-align:center;color:#a49b88;padding:64px 20px;font-family:\'Spectral\',Georgia,serif;font-size:17px;">No policies match these filters.</div>');
  } else if(v.isStatsMode){
    o.push(statsHTML(v.stats));
  }
  o.push('</div>');
  return o.join('');
}
function viewHTML(v,HND){
  function h(fn){ HND.push(fn); return HND.length-1; }
  var o=[];
  o.push('<div style="min-height:100vh;background:#f6f3ec;font-family:\'Libre Franklin\',system-ui,sans-serif;color:#232019;-webkit-font-smoothing:antialiased;">');
  o.push('<div style="max-width:1180px;margin:0 auto;padding:36px 28px 18px;display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap;">');
  o.push('<div><div style="font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;letter-spacing:0.24em;text-transform:uppercase;color:#a75a38;margin-bottom:9px;">A living index of the field</div><h1 style="font-family:\'Spectral\',Georgia,serif;font-weight:600;font-size:35px;line-height:1.02;margin:0;color:#232019;letter-spacing:-0.015em;">The AI Safety Directory</h1></div>');
  o.push('<div style="font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;line-height:1.75;color:#8a8272;text-align:right;max-width:340px;">'+esc(v.mastheadMeta)+'</div>');
  o.push('</div>');
  o.push('<div style="position:sticky;top:0;z-index:20;background:#f6f3ec;border-bottom:1px solid #d8d0bf;"><div style="max-width:1180px;margin:0 auto;padding:0 22px;display:flex;gap:0;flex-wrap:wrap;">');
  v.tabs.forEach(function(tab){ o.push('<div class="aisd-tab" data-h="'+h(tab.onClick)+'" style="padding:15px 12px 13px;cursor:pointer;font-family:\'IBM Plex Mono\',monospace;font-size:11px;letter-spacing:0.07em;text-transform:uppercase;color:'+tab.color+';border-bottom:2px solid '+tab.border+';display:flex;gap:6px;align-items:center;"><span>'+esc(tab.label)+'</span><span style="opacity:0.5;font-size:10px;">'+esc(tab.count)+'</span></div>'); });
  o.push('</div></div>');
  if(v.loading){ o.push('<div style="max-width:1180px;margin:0 auto;padding:64px 28px;font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:#a49b88;">'+esc(v.mastheadMeta||'Loading…')+'</div>'); }
  else if(v.isDetail){ o.push(detailHTML(v,h)); }
  else { o.push(browseHTML(v,h)); }
  o.push('</div>');
  return o.join('');
}

var COMP=new Component({colorCodeKinds:true, showFocusTags:true});
COMP._mount(document.getElementById('app'));
</script>
</body>
</html>
"""

HTML = HTML.replace("/*DATA*/", DATA_JSON)
out = os.path.join(BASE, "ai-safety-people-directory.html")
open(out, "w", encoding="utf-8").write(HTML)
print("wrote", out, len(HTML), "bytes")
print(f"people {len(people)} | orgs {len(data['orgs'])} | papers {len(data['papers'])} | "
      f"confs {len(data['conferences'])} | fellowships {len(data['fellowships'])} | datasets {len(data['datasets'])}")

# 2026-07-08: emit the Metadata-health snapshot as a standalone JSON so the
# weekly health-trend task (health_trend.py) can log/diff it without re-parsing
# the HTML. Mirrors exactly the pills shown on the Stats tab (author-adjusted).
_st = data.get("stats") or {}
_snap = {
    "generated": _st.get("generated") or datetime.date.today().isoformat(),
    "nSources": _st.get("nSources"),
    "health": _st.get("health", {}),
}
with open(os.path.join(BASE, "health_snapshot.json"), "w", encoding="utf-8") as _hf:
    json.dump(_snap, _hf, ensure_ascii=False, indent=2)
print("wrote health_snapshot.json:", _snap["health"])
