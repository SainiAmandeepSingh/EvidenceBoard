import marimo

__generated_with = "0.21.1"
app = marimo.App(width="full")


# ── Cell 1: Marimo import ────────────────────────────────────────────────────
@app.cell
def _():
    import marimo as mo
    return (mo,)


# ── Cell 2: Data loading and all computation ─────────────────────────────────
# Loads MC3_graph.json and computes data structures for all three pages:
#   Page 1 (EvidenceBoard): entity records, relationships, ghost links
#   Page 2 (Timeline):      communication heatmap matrix (entity x day)
#   Page 3 (Suspicion):     ranked suspicion scores per entity
@app.cell
def _():
    import json as _json
    from collections import defaultdict as _dd

    with open("data/MC3_graph.json") as _f:
        _raw = _json.load(_f)

    _nodes = _raw["nodes"]
    _edges = _raw["edges"]
    _nmap  = {n["id"]: n for n in _nodes}

    _ent_nodes  = [n for n in _nodes if n["type"] == "Entity"]
    _rel_nodes  = [n for n in _nodes if n["type"] == "Relationship"]
    _comm_nodes = [n for n in _nodes if n.get("sub_type") == "Communication"]

    # Entity <-> Relationship membership
    _r2e = _dd(list)
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _s.get("type") == "Entity" and _t.get("type") == "Relationship":
            _r2e[_e["target"]].append(_e["source"])
        if _s.get("type") == "Relationship" and _t.get("type") == "Entity":
            _r2e[_e["source"]].append(_e["target"])

    # Communication -> Relationship evidence chains
    _r2c = _dd(list)
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _s.get("sub_type") == "Communication" and _t.get("type") == "Relationship":
            _r2c[_e["target"]].append(_e["source"])

    # Sender and receiver lookups for each Communication node
    _csnd, _crcv = {}, {}
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _e.get("type") == "sent" and _s.get("type") == "Entity" and _t.get("sub_type") == "Communication":
            _csnd[_e["target"]] = _e["source"]
        if _e.get("type") == "received" and _s.get("sub_type") == "Communication" and _t.get("type") == "Entity":
            _crcv[_e["source"]] = _e["target"]

    # Entity-pair communication counts (used for ghost link detection)
    _pair = _dd(list)
    for _cid, _snd in _csnd.items():
        _rcv = _crcv.get(_cid)
        if _rcv and _snd != _rcv:
            _pair[tuple(sorted([_snd, _rcv]))].append(_cid)

    # Build relationship objects with full evidence chains
    MAX_EV = 1
    all_rels = []
    for _rn in _rel_nodes:
        _rid  = _rn["id"]
        _ents = list(dict.fromkeys(_r2e.get(_rid, [])))
        if len(_ents) < 2:
            continue
        _comms = _r2c.get(_rid, [])
        _ev    = len(_comms)
        MAX_EV = max(MAX_EV, _ev)
        _cdets = []
        for _cid in _comms[:8]:
            _cn = _nmap.get(_cid, {})
            _cdets.append({
                "ts":   (_cn.get("timestamp") or "")[:16],
                "from": _csnd.get(_cid, "Unknown"),
                "to":   _crcv.get(_cid, "Unknown"),
                "text": (_cn.get("content") or "")[:200],
                "inf":  bool(_cn.get("is_inferred", True)),
            })
        all_rels.append({
            "id":    _rid,
            "sub":   _rn.get("sub_type", "Unknown"),
            "ents":  _ents[:2],
            "ev":    _ev,
            "comms": _cdets,
        })

    # Conflict entities: have BOTH Suspicious AND Colleagues/Friends
    _ert = _dd(set)
    for _r in all_rels:
        for _eid in _r["ents"]:
            _ert[_eid].add(_r["sub"])
    _conflicts = frozenset(
        _eid for _eid, _st in _ert.items()
        if "Suspicious" in _st and ("Colleagues" in _st or "Friends" in _st)
    )

    # Ghost links: entity pairs with 5+ comms but no relationship node
    _existing = {tuple(sorted(_r["ents"][:2])) for _r in all_rels}
    all_ghosts = [
        {"a": _p[0], "b": _p[1], "n": len(_c)}
        for _p, _c in _pair.items()
        if len(_c) >= 5 and _p not in _existing
    ]

    # Colour maps (exact values used in all three pages)
    _EC = {"Person":"#1D9E75","Organization":"#534AB7","Vessel":"#185FA5",
           "Group":"#BA7517","Location":"#888780"}
    _RC = {"Suspicious":"#E24B4A","Colleagues":"#1D9E75","Friends":"#1D9E75",
           "Operates":"#534AB7","AccessPermission":"#BA7517","Coordinates":"#185FA5",
           "Jurisdiction":"#185FA5","Reports":"#3B8BD4","Unfriendly":"#D85A30"}

    # Entity records (positions assigned by D3 force simulation at runtime)
    all_ents = []
    for _en in _ent_nodes:
        _eid = _en["id"]
        all_ents.append({
            "id":       _eid,
            "label":    _en.get("label", _eid),
            "sub":      _en.get("sub_type", "Unknown"),
            "hcolor":   _EC.get(_en.get("sub_type", ""), "#888780"),
            "conflict": _eid in _conflicts,
            "types":    sorted(_ert.get(_eid, set())),
        })
    for _r in all_rels:
        _r["color"] = _RC.get(_r["sub"], "#888780")

    all_subtypes = sorted(set(_r["sub"] for _r in all_rels))

    # ── Page 2: Communication timeline data ──────────────────────────────────
    # Build a matrix of (entity x date) communication counts
    _all_comms = []
    for _cn in _comm_nodes:
        _cid  = _cn["id"]
        _ts   = (_cn.get("timestamp") or "")[:16]
        _date = _ts[:10]
        _snd  = _csnd.get(_cid, "")
        _rcv  = _crcv.get(_cid, "")
        if _snd and _rcv and _date:
            _all_comms.append({
                "ts":      _ts,
                "date":    _date,
                "sender":  _snd,
                "to":      _rcv,
                "content": (_cn.get("content") or "")[:150],
            })
    _all_comms.sort(key=lambda x: x["ts"])

    # Top 25 senders by total message count
    _etotals = _dd(int)
    for _c in _all_comms:
        _etotals[_c["sender"]] += 1
    _top25 = sorted(_etotals.keys(), key=lambda x: -_etotals[x])[:25]
    _all_dates = sorted(set(_c["date"] for _c in _all_comms))

    # Build cell data: {entity, date, count, sample messages}
    _heat = _dd(lambda: _dd(list))
    for _c in _all_comms:
        if _c["sender"] in _top25:
            _heat[_c["sender"]][_c["date"]].append({
                "ts": _c["ts"],
                "to": _c["to"],
                "content": _c["content"],
            })

    heat_data = {
        "entities": _top25,
        "dates":    _all_dates,
        "cells": [
            {"entity": _ent, "date": _d, "count": len(_msgs), "msgs": _msgs[:4]}
            for _ent, _dates in _heat.items()
            for _d, _msgs in _dates.items()
        ],
        "totals":    {_eid: _etotals[_eid] for _eid in _top25},
        "colors":    {_eid: _EC.get(_nmap.get(_eid, {}).get("sub_type", ""), "#888780") for _eid in _top25},
        "conflicts": {_eid: (_eid in _conflicts) for _eid in _top25},
    }

    # ── Page 3: Suspicion analysis data ──────────────────────────────────────
    # Rank entities by total suspicious evidence
    _ss = _dd(lambda: {"count": 0, "ev": 0, "rels": []})
    for _r in all_rels:
        if _r["sub"] == "Suspicious":
            for _eid in _r["ents"]:
                _ss[_eid]["count"] += 1
                _ss[_eid]["ev"]    += _r["ev"]
                _partner = [x for x in _r["ents"] if x != _eid]
                _ss[_eid]["rels"].append({
                    "partner": _partner[0] if _partner else "Unknown",
                    "ev":      _r["ev"],
                    "color":   _r["color"],
                    "comms":   _r["comms"][:3],
                })

    susp_data = []
    for _eid, _info in _ss.items():
        _en = _nmap.get(_eid, {})
        susp_data.append({
            "id":       _eid,
            "label":    _en.get("label", _eid),
            "sub":      _en.get("sub_type", "Unknown"),
            "color":    _EC.get(_en.get("sub_type", ""), "#888780"),
            "conflict": _eid in _conflicts,
            "count":    _info["count"],
            "ev":       _info["ev"],
            "rels":     sorted(_info["rels"], key=lambda r: -r["ev"]),
        })
    susp_data.sort(key=lambda x: -(x["ev"] + x["count"] * 2))

    return all_ents, all_ghosts, all_rels, all_subtypes, MAX_EV, heat_data, susp_data


# ── Cell 3: EvidenceBoard controls (created here, read in Cell 4) ────────────
@app.cell
def _(mo, all_subtypes, MAX_EV):
    threshold     = mo.ui.slider(1, MAX_EV, value=1, label="Min. evidence", show_value=True)
    etype_filter  = mo.ui.dropdown(
        ["All","Person","Organization","Vessel","Group","Location"],
        value="All", label="Entity type",
    )
    rtype_filter  = mo.ui.dropdown(
        ["All"] + all_subtypes, value="All", label="Relationship type",
    )
    ghost_toggle  = mo.ui.switch(value=True, label="Ghost links")
    conflict_only = mo.ui.switch(value=False, label="Conflicts only")
    return conflict_only, etype_filter, ghost_toggle, rtype_filter, threshold


# ── Cell 4: Build all three pages and assemble into tabs ─────────────────────
@app.cell
def _(mo, all_ents, all_rels, all_ghosts, MAX_EV,
      heat_data, susp_data,
      threshold, etype_filter, rtype_filter, ghost_toggle, conflict_only):
    import json as _js

    # ── Page 1 filter ─────────────────────────────────────────────────────────
    _ef = etype_filter.value
    _rf = rtype_filter.value
    _sg = ghost_toggle.value
    _mn = threshold.value
    _co = conflict_only.value

    _ve = [e for e in all_ents if (_ef == "All" or e["sub"] == _ef) and (not _co or e["conflict"])]
    _vi = {e["id"] for e in _ve}
    _vr = [r for r in all_rels if r["ev"] >= _mn and (_rf == "All" or r["sub"] == _rf)
           and r["ents"][0] in _vi and r["ents"][1] in _vi]
    _vg = [g for g in all_ghosts if _sg and g["a"] in _vi and g["b"] in _vi]

    # Remove isolated entities (no visible connections)
    _conn = set()
    for _r in _vr:
        _conn.add(_r["ents"][0]); _conn.add(_r["ents"][1])
    for _g in _vg:
        _conn.add(_g["a"]); _conn.add(_g["b"])
    _ve = [e for e in _ve if e["id"] in _conn]
    _nc = sum(1 for e in _ve if e["conflict"])

    # Serialise to JSON for injection into JavaScript
    _p1_data = (
        "var E="   + _js.dumps(_ve,  ensure_ascii=False) + ";\n"
        "var R="   + _js.dumps(_vr,  ensure_ascii=False) + ";\n"
        "var GH="  + _js.dumps(_vg,  ensure_ascii=False) + ";\n"
        "var MEV=" + str(MAX_EV) + ";\n"
    )
    _p2_data = "var HEAT=" + _js.dumps(heat_data,  ensure_ascii=False) + ";\n"
    _p3_data = "var SUSP=" + _js.dumps(susp_data, ensure_ascii=False) + ";\n"

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 1 JAVASCRIPT — EvidenceBoard with D3 force simulation
    # ════════════════════════════════════════════════════════════════════════
    _p1_js = r"""
var REL_COLORS = {Suspicious:'#E24B4A',Colleagues:'#1D9E75',Friends:'#1D9E75',
  Operates:'#534AB7',AccessPermission:'#BA7517',Coordinates:'#185FA5',
  Jurisdiction:'#185FA5',Reports:'#3B8BD4',Unfriendly:'#D85A30'};
var CW=124, CH=54, HH=17;

// Stroke width encodes evidence count (Ware 2004 — line width channel)
function strokeW(ev){ return Math.max(2,Math.min(10,ev*0.6+1.5)); }
// Stroke opacity encodes inference confidence (MacEachren et al. 2012)
function strokeO(ev){ return Math.max(0.35,Math.min(0.95,ev/MEV*2+0.35)); }
function trunc(s,n){ return s&&s.length>n?s.slice(0,n-1)+'\u2026':(s||''); }

// ── Investigation queue ───────────────────────────────────────────────────────
// Analyst can escalate relationships to a persistent review list
var queue = [];
var currentRel = null;

function escalate() {
  if (!currentRel) return;
  var exists = queue.some(function(q){ return q.id === currentRel.id; });
  if (!exists) { queue.push(currentRel); }
  renderQueue();
  // Show confirmation in panel
  var qb = document.getElementById('queue-banner');
  qb.style.display = 'block';
  qb.textContent = 'Added to investigation queue (' + queue.length + ' total)';
  setTimeout(function(){ qb.style.display = 'none'; }, 2000);
}

function removeFromQueue(idx) {
  queue.splice(idx, 1);
  renderQueue();
}

function renderQueue() {
  var qEl = document.getElementById('queue-section');
  if (!queue.length) { qEl.innerHTML = ''; return; }
  var h = '<div style="border-top:1px solid #d3d1c7;margin-top:14px;padding-top:10px;">'
    + '<div style="font-size:10px;font-weight:600;color:#3d3d3a;margin-bottom:6px;">'
    + 'Investigation queue (' + queue.length + ')</div>';
  queue.forEach(function(r, i) {
    var col = r.color || '#888780';
    h += '<div style="background:#f8f7f4;border-radius:5px;padding:6px 9px;margin-bottom:5px;'
      + 'display:flex;justify-content:space-between;align-items:flex-start;">'
      + '<div>'
      + '<span style="font-size:9.5px;font-weight:600;color:'+col+';">'+r.sub+'</span>'
      + '<div style="font-size:9px;color:#73726c;margin-top:1px;">'+r.ents.join(' and ')+'</div>'
      + '<div style="font-size:8.5px;color:#888780;">Evidence: '+r.ev+'</div>'
      + '</div>'
      + '<button onclick="removeFromQueue('+i+')" '
      + 'style="font-size:11px;color:#888780;background:none;border:none;cursor:pointer;'
      + 'padding:0 4px;line-height:1;">x</button></div>';
  });
  h += '</div>';
  qEl.innerHTML = h;
}

// ── Evidence detail panel ────────────────────────────────────────────────────
function clearPanel() {
  currentRel = null;
  document.getElementById('pb').innerHTML =
    '<p class="pp">Click any string to see its evidence chain.<br>'
    + 'Click any entity card to see its connections.<br>'
    + 'Click background to reset.</p>';
  document.getElementById('queue-section').innerHTML = '';
  renderQueue();
}

function showRel(r) {
  currentRel = r;
  var col = r.color || '#888780';
  var pct = Math.round(r.ev / MEV * 100);
  var lbl = pct < 30 ? 'Low' : pct < 65 ? 'Medium' : 'High';
  var h =
    '<div style="background:'+col+'18;border:1px solid '+col+'55;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    + '<div style="font-size:11px;font-weight:600;color:'+col+';">'+r.sub+' relationship</div>'
    + '<div style="font-size:10px;color:#73726c;margin-top:2px;">'+(r.ents||[]).join(' and ')+'</div></div>'
    + '<div style="font-size:10px;font-weight:600;margin:6px 0 3px;">Evidence confidence</div>'
    + '<div style="height:8px;background:#f1efe8;border-radius:4px;overflow:hidden;">'
    + '<div style="height:100%;width:'+Math.min(100,pct)+'%;background:'+col+';opacity:.85;border-radius:4px;"></div></div>'
    + '<div style="display:flex;justify-content:space-between;font-size:9px;color:#888780;margin:2px 0 10px;">'
    + '<span>'+lbl+' ('+pct+'%)</span><span>'+r.ev+' of '+MEV+' max</span></div>'
    + '<div style="font-size:10px;font-weight:600;margin-bottom:6px;">Supporting communications ('+(r.comms||[]).length+')</div>';
  (r.comms||[]).forEach(function(c) {
    h += '<div style="background:#f8f7f4;border-radius:5px;padding:7px 9px;margin-bottom:6px;">'
      + '<div style="font-size:9px;font-weight:600;color:#534AB7;">'+c.ts+'  '+c.from+' to '+c.to+'</div>'
      + '<div style="font-size:10px;color:#3d3d3a;line-height:1.5;margin-top:3px;">\u201c'+trunc(c.text,180)+'\u201d</div>'
      + '<div style="font-size:8.5px;color:#888780;margin-top:2px;font-style:italic;">is_inferred: '+c.inf+'</div></div>';
  });
  h += '<div style="display:flex;gap:6px;margin-top:10px;">'
    + '<button onclick="escalate()" style="flex:1;padding:7px;border-radius:5px;font-size:10px;font-weight:600;cursor:pointer;'
    + 'border:1px solid '+col+';background:'+col+'18;color:'+col+';">Add to queue</button>'
    + '<button onclick="clearPanel()" style="flex:1;padding:7px;border-radius:5px;font-size:10px;cursor:pointer;'
    + 'border:1px solid #d3d1c7;background:transparent;color:#888780;">Dismiss</button></div>'
    + '<div id="queue-banner" style="display:none;margin-top:6px;padding:5px 8px;background:#E1F5EE;'
    + 'border-radius:4px;font-size:9.5px;color:#085041;"></div>';
  document.getElementById('pb').innerHTML = h;
  renderQueue();
}

function showEnt(e) {
  var col = e.hcolor || '#888780';
  var badge = e.conflict
    ? '<div style="margin-top:6px;font-size:9.5px;background:#FCEBEB;border-radius:4px;padding:5px 8px;color:#791F1F;line-height:1.5;">'
      + '\u26A0 This entity has both a Suspicious and a Colleagues or Friends relationship. '
      + 'This contradiction is a key investigative signal (Task 2).</div>' : '';
  var h = '<div style="background:'+col+'18;border:1px solid '+col+'55;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    + '<div style="font-size:12px;font-weight:600;color:'+col+';">'+e.label+'</div>'
    + '<div style="font-size:10px;color:#73726c;margin-top:2px;">'+e.sub+'</div>'+badge+'</div>'
    + '<div style="font-size:10px;font-weight:600;margin-bottom:6px;">Relationship types</div>';
  if (e.types && e.types.length) {
    e.types.forEach(function(t) {
      var tc = REL_COLORS[t] || '#888780';
      h += '<span style="display:inline-block;margin:0 4px 4px 0;padding:3px 8px;border-radius:12px;'
        + 'font-size:9px;font-weight:600;background:'+tc+'20;color:'+tc+';border:1px solid '+tc+'55;">'+t+'</span>';
    });
  }
  document.getElementById('pb').innerHTML = h;
  renderQueue();
}

function showGhost(g) {
  document.getElementById('pb').innerHTML =
    '<div style="background:#8887801a;border:1px dashed #888780;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    + '<div style="font-size:11px;font-weight:600;color:#73726c;">Predicted missing relationship</div>'
    + '<div style="font-size:10px;color:#888780;margin-top:2px;">'+g.a+' and '+g.b+'</div></div>'
    + '<div style="font-size:11px;color:#3d3d3a;line-height:1.7;margin-bottom:8px;">These entities exchanged '
    + '<strong>'+g.n+' communications</strong> but no relationship node was inferred in the knowledge graph. '
    + 'This is a predicted data gap.</div>'
    + '<div style="font-size:9.5px;color:#888780;background:#f8f7f4;padding:8px;border-radius:5px;line-height:1.6;">'
    + 'Dashed texture encodes epistemic uncertainty. MacEachren et al. (2012), doi:10.1145/2254556.2254592</div>'
    + '<div style="display:flex;gap:6px;margin-top:12px;">'
    + '<button onclick="alert(\'Flagged for review\')" style="flex:1;padding:7px;border-radius:5px;font-size:10px;'
    + 'font-weight:600;cursor:pointer;border:1px solid #534AB7;background:#EEEDFE;color:#534AB7;">Review</button>'
    + '<button onclick="clearPanel()" style="flex:1;padding:7px;border-radius:5px;font-size:10px;cursor:pointer;'
    + 'border:1px solid #d3d1c7;background:transparent;color:#888780;">Dismiss</button></div>';
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
var tip = document.getElementById('tip');
function showTip(html,x,y){
  tip.innerHTML=html; tip.style.display='block';
  tip.style.left=Math.min(x+14,window.innerWidth-tip.offsetWidth-10)+'px';
  tip.style.top=(y-10)+'px';
}
function hideTip(){ tip.style.display='none'; }

// ── Canvas ────────────────────────────────────────────────────────────────────
var W = window.innerWidth - 264;
var H = window.innerHeight - 82;
var svg   = d3.select('#svg').attr('width',W).attr('height',H);
var zoomG = svg.append('g');

// Zoom and pan — d3.zoom handles scroll, click-drag, and touch
var zoomB = d3.zoom().scaleExtent([0.15,5])
  .on('zoom', function(ev){ zoomG.attr('transform',ev.transform); });
svg.call(zoomB);

// Three rendering layers: ghost strings behind, rel strings in middle, cards on top
var ghostL = zoomG.append('g');
var linkL  = zoomG.append('g');
var cardL  = zoomG.append('g');

// Node position map (used for ghost link tick updates)
var nodeById = {};

// Simulation nodes with random starting positions within canvas bounds
var simNodes = E.map(function(e) {
  var n = Object.assign({},e,{x:W/2+(Math.random()-.5)*W*.5,y:H/2+(Math.random()-.5)*H*.5});
  nodeById[e.id]=n; return n;
});

// D3 link arrays reference entities by id
var simLinks  = R.map(function(r){ return {data:r,source:r.ents[0],target:r.ents[1]}; });
var simGhosts = GH.map(function(g){ return {data:g,source:g.a,target:g.b}; });

// Force simulation: repulsion, link attraction, center gravity, collision
var sim = d3.forceSimulation(simNodes)
  .force('link', d3.forceLink(simLinks).id(function(d){return d.id;})
    .distance(function(d){ return 160+(1-d.data.ev/MEV)*100; }).strength(0.5))
  .force('charge', d3.forceManyBody().strength(-700).distanceMax(600))
  .force('center', d3.forceCenter(W/2,H/2))
  .force('collision', d3.forceCollide().radius(80).strength(0.9))
  .alphaDecay(0.025);

// ── Focus mode ────────────────────────────────────────────────────────────────
var focusedId=null, focusedLink=null;

function dimAll(){
  linkL.selectAll('.rl').attr('stroke-opacity',0.07);
  ghostL.selectAll('.gh').attr('stroke-opacity',0.05);
  cardL.selectAll('.ec').attr('opacity',0.1);
}
function resetFocus(){
  focusedId=null; focusedLink=null;
  linkL.selectAll('.rl')
    .attr('stroke-opacity',function(d){return strokeO(d.data.ev);})
    .attr('stroke-width',function(d){return strokeW(d.data.ev);});
  ghostL.selectAll('.gh').attr('stroke-opacity',0.5).attr('stroke-width',2);
  cardL.selectAll('.ec').attr('opacity',1);
}
function focusEntity(eid){
  focusedId=eid; dimAll();
  linkL.selectAll('.rl').each(function(d){
    var src=typeof d.source==='object'?d.source.id:d.source;
    var tgt=typeof d.target==='object'?d.target.id:d.target;
    if(src===eid||tgt===eid){
      d3.select(this).attr('stroke-opacity',strokeO(d.data.ev)).attr('stroke-width',strokeW(d.data.ev)+1);
      var nb=src===eid?tgt:src;
      cardL.selectAll('.ec').filter(function(n){return n.id===nb;}).attr('opacity',1);
    }
  });
  ghostL.selectAll('.gh').each(function(d){
    var sa=typeof d.source==='object'?(d.source.id||d.source):d.source;
    var ta=typeof d.target==='object'?(d.target.id||d.target):d.target;
    if(sa===eid||ta===eid){
      d3.select(this).attr('stroke-opacity',0.8).attr('stroke-width',3);
      var nb=sa===eid?ta:sa;
      cardL.selectAll('.ec').filter(function(n){return n.id===nb;}).attr('opacity',1);
    }
  });
  cardL.selectAll('.ec').filter(function(d){return d.id===eid;}).attr('opacity',1);
}
function focusLink(r){
  focusedLink=r; dimAll();
  linkL.selectAll('.rl').filter(function(d){return d.data===r;})
    .attr('stroke-opacity',1).attr('stroke-width',strokeW(r.ev)+2);
  cardL.selectAll('.ec').filter(function(d){return d.id===r.ents[0]||d.id===r.ents[1];}).attr('opacity',1);
}

// ── Ghost strings ─────────────────────────────────────────────────────────────
var ghostPaths = ghostL.selectAll('.gh').data(simGhosts).join('line').attr('class','gh')
  .attr('stroke','#888780').attr('stroke-width',2).attr('stroke-dasharray','8,6')
  .attr('stroke-opacity',0.5).style('cursor','pointer')
  .on('mouseenter',function(ev,d){
    if(!focusedId&&!focusedLink) d3.select(this).attr('stroke-width',4).attr('stroke-opacity',.85);
    showTip('<strong>Predicted missing</strong><br>'+d.data.a+' and '+d.data.b+'<br>'+d.data.n+' comms, no relationship node',ev.clientX,ev.clientY);
  })
  .on('mousemove',function(ev){showTip(tip.innerHTML,ev.clientX,ev.clientY);})
  .on('mouseleave',function(ev,d){
    if(!focusedId&&!focusedLink) d3.select(this).attr('stroke-width',2).attr('stroke-opacity',.5);
    hideTip();
  })
  .on('click',function(ev,d){ev.stopPropagation();resetFocus();showGhost(d.data);});

// ── Relationship strings ──────────────────────────────────────────────────────
var relPaths = linkL.selectAll('.rl').data(simLinks).join('line').attr('class','rl')
  .attr('stroke',function(d){return d.data.color;})
  .attr('stroke-width',function(d){return strokeW(d.data.ev);})
  .attr('stroke-opacity',function(d){return strokeO(d.data.ev);})
  .style('cursor','pointer')
  .on('mouseenter',function(ev,d){
    if(!focusedId&&!focusedLink) d3.select(this).attr('stroke-width',strokeW(d.data.ev)+3).attr('stroke-opacity',1);
    showTip('<strong>'+d.data.sub+'</strong><br>'+d.data.ents.join(' and ')+'<br>Evidence: '+d.data.ev+' of '+MEV,ev.clientX,ev.clientY);
  })
  .on('mousemove',function(ev){showTip(tip.innerHTML,ev.clientX,ev.clientY);})
  .on('mouseleave',function(ev,d){
    if(!focusedId&&!focusedLink) d3.select(this).attr('stroke-width',strokeW(d.data.ev)).attr('stroke-opacity',strokeO(d.data.ev));
    hideTip();
  })
  .on('click',function(ev,d){ev.stopPropagation();focusLink(d.data);showRel(d.data);});

// ── Drop shadow filter ────────────────────────────────────────────────────────
var defs=svg.append('defs');
var flt=defs.append('filter').attr('id','sh').attr('x','-20%').attr('y','-20%').attr('width','140%').attr('height','140%');
flt.append('feDropShadow').attr('dx','0').attr('dy','1.5').attr('stdDeviation','2.5').attr('flood-color','#00000020');

// ── Entity cards ──────────────────────────────────────────────────────────────
var cards = cardL.selectAll('.ec').data(simNodes).join('g').attr('class','ec')
  .style('cursor','pointer')
  .on('mouseenter',function(ev,d){
    d3.select(this).select('.cb').attr('stroke-width',d.conflict?3:1.5);
    showTip('<strong>'+d.label+'</strong><br>'+d.sub+(d.conflict?' <span style="color:#ffb3b0;">\u26A0 conflict</span>':''),ev.clientX,ev.clientY);
  })
  .on('mousemove',function(ev){showTip(tip.innerHTML,ev.clientX,ev.clientY);})
  .on('mouseleave',function(ev,d){
    d3.select(this).select('.cb').attr('stroke-width',d.conflict?2:.5);
    hideTip();
  })
  .on('click',function(ev,d){
    ev.stopPropagation();
    if(focusedId===d.id){resetFocus();clearPanel();}
    else{focusEntity(d.id);showEnt(d);}
  })
  .call(d3.drag()
    .on('start',function(ev,d){if(!ev.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y;hideTip();})
    .on('drag', function(ev,d){d.fx=ev.x;d.fy=ev.y;})
    .on('end',  function(ev,d){if(!ev.active)sim.alphaTarget(0);d.fx=null;d.fy=null;})
  );

// Card body (white background)
cards.append('rect').attr('class','cb').attr('width',CW).attr('height',CH).attr('rx',8)
  .attr('x',-CW/2).attr('y',-CH/2).attr('fill','#ffffff').attr('filter','url(#sh)')
  .attr('stroke',function(d){return d.conflict?'#E24B4A':'#d3d1c7';})
  .attr('stroke-width',function(d){return d.conflict?2:.5;});
// Coloured header band
cards.append('rect').attr('width',CW).attr('height',HH).attr('rx',8).attr('x',-CW/2).attr('y',-CH/2)
  .attr('fill',function(d){return d.hcolor;});
cards.append('rect').attr('width',CW).attr('height',HH/2).attr('x',-CW/2).attr('y',-CH/2+HH/2)
  .attr('fill',function(d){return d.hcolor;});
// Entity label
cards.append('text').attr('y',-CH/2+HH/2).attr('text-anchor','middle').attr('dominant-baseline','central')
  .attr('font-size','10.5').attr('font-weight','600').attr('fill','white').attr('font-family','system-ui,sans-serif')
  .text(function(d){return trunc(d.label,16);});
// Subtype
cards.append('text').attr('y',-CH/2+HH+12).attr('text-anchor','middle').attr('dominant-baseline','central')
  .attr('font-size','10').attr('fill','#888780').attr('font-family','system-ui,sans-serif')
  .text(function(d){return d.sub;});
// Relationship types or conflict label
cards.append('text').attr('y',-CH/2+HH+27).attr('text-anchor','middle').attr('dominant-baseline','central')
  .attr('font-size','9.5').attr('font-weight',function(d){return d.conflict?'600':'400';})
  .attr('fill',function(d){return d.conflict?'#E24B4A':'#888780';}).attr('font-family','system-ui,sans-serif')
  .text(function(d){return d.conflict?'\u26A0 conflict':trunc(d.types.slice(0,2).join(', ')||'\u2014',22);});
// Red badge for conflict entities
cards.filter(function(d){return d.conflict;})
  .append('circle').attr('cx',CW/2-8).attr('cy',-CH/2+8).attr('r',5).attr('fill','#E24B4A');

// ── Zoom control buttons ──────────────────────────────────────────────────────
d3.select('#bi').on('click',function(){svg.transition().duration(300).call(zoomB.scaleBy,1.4);});
d3.select('#bo').on('click',function(){svg.transition().duration(300).call(zoomB.scaleBy,.7);});
d3.select('#br').on('click',function(){svg.transition().duration(500).call(zoomB.transform,d3.zoomIdentity);});
svg.on('click',function(){resetFocus();clearPanel();});

// ── Tick: update positions each physics step ──────────────────────────────────
sim.on('tick',function(){
  relPaths
    .attr('x1',function(d){return d.source.x;}).attr('y1',function(d){return d.source.y;})
    .attr('x2',function(d){return d.target.x;}).attr('y2',function(d){return d.target.y;});
  ghostPaths
    .attr('x1',function(d){var s=typeof d.source==='object'?d.source:nodeById[d.source];return s?s.x:0;})
    .attr('y1',function(d){var s=typeof d.source==='object'?d.source:nodeById[d.source];return s?s.y:0;})
    .attr('x2',function(d){var t=typeof d.target==='object'?d.target:nodeById[d.target];return t?t.x:0;})
    .attr('y2',function(d){var t=typeof d.target==='object'?d.target:nodeById[d.target];return t?t.y:0;});
  cards.attr('transform',function(d){return 'translate('+d.x+','+d.y+')';});
});
"""

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 2 JAVASCRIPT — Communication timeline heatmap
    # ════════════════════════════════════════════════════════════════════════
    _p2_js = r"""
var entities  = HEAT.entities;
var dates     = HEAT.dates;
var colors    = HEAT.colors;
var conflicts = HEAT.conflicts;
var totals    = HEAT.totals;

// Build cell lookup: entity+date -> {count, msgs}
var cellMap = {};
HEAT.cells.forEach(function(c){
  cellMap[c.entity+'|'+c.date] = c;
});

var tip = document.getElementById('tip2');
function showTip(html,x,y){
  tip.innerHTML=html; tip.style.display='block';
  tip.style.left=Math.min(x+14,window.innerWidth-tip.offsetWidth-10)+'px';
  tip.style.top=(y-10)+'px';
}
function hideTip(){ tip.style.display='none'; }

// Find max count for colour scale
var maxCount = 0;
HEAT.cells.forEach(function(c){ if(c.count>maxCount) maxCount=c.count; });

// Layout constants
var ML=170, MT=60, MR=20, MB=30;
var W=window.innerWidth-MR-ML-20;
var H=window.innerHeight-MT-MB-120;
var cellW=Math.max(18, Math.floor(W/dates.length));
var cellH=Math.max(16, Math.floor(H/entities.length));
var svgW=ML+dates.length*cellW+MR;
var svgH=MT+entities.length*cellH+MB;

var svg=d3.select('#heatsvg').attr('width',svgW).attr('height',svgH);

// Colour scale: light cream to deep teal (Ware 2004 — luminance for ordered data)
var colScale=d3.scaleSequential().domain([0,maxCount]).interpolator(d3.interpolate('#f1efe8','#085041'));

// ── Date column labels ────────────────────────────────────────────────────────
svg.selectAll('.dlbl').data(dates).join('text').attr('class','dlbl')
  .attr('x',function(d,i){return ML+i*cellW+cellW/2;})
  .attr('y',MT-8).attr('text-anchor','middle')
  .attr('font-size','9').attr('fill','#73726c').attr('font-family','system-ui,sans-serif')
  .text(function(d){return d.slice(5);});  // show MM-DD only

// ── Entity row labels ─────────────────────────────────────────────────────────
svg.selectAll('.elbl').data(entities).join('g').attr('class','elbl')
  .attr('transform',function(d,i){return 'translate(0,'+(MT+i*cellH+cellH/2)+')';})
  .call(function(g){
    // Conflict badge (small dot)
    g.filter(function(d){return conflicts[d];})
      .append('circle').attr('cx',8).attr('cy',0).attr('r',4).attr('fill','#E24B4A');
    // Entity name label
    g.append('text')
      .attr('x',16).attr('dominant-baseline','central')
      .attr('font-size','10').attr('font-family','system-ui,sans-serif')
      .attr('font-weight',function(d){return conflicts[d]?'600':'400';})
      .attr('fill',function(d){return colors[d]||'#3d3d3a';})
      .text(function(d){return d.length>20?d.slice(0,19)+'\u2026':d;});
    // Total count badge on right
    g.append('text')
      .attr('x',ML-8).attr('dominant-baseline','central').attr('text-anchor','end')
      .attr('font-size','8.5').attr('fill','#888780').attr('font-family','system-ui,sans-serif')
      .text(function(d){return totals[d]||0;});
  });

// ── Heatmap cells ─────────────────────────────────────────────────────────────
// Each cell shows communication count for one entity on one day
var cellData=[];
entities.forEach(function(ent,ei){
  dates.forEach(function(dt,di){
    cellData.push({entity:ent,date:dt,ei:ei,di:di,key:ent+'|'+dt});
  });
});

svg.selectAll('.cell').data(cellData).join('rect').attr('class','cell')
  .attr('x',function(d){return ML+d.di*cellW+1;})
  .attr('y',function(d){return MT+d.ei*cellH+1;})
  .attr('width',cellW-2).attr('height',cellH-2).attr('rx',2)
  .attr('fill',function(d){
    var c=cellMap[d.key];
    return c?colScale(c.count):'#f1efe8';
  })
  .style('cursor',function(d){return cellMap[d.key]?'pointer':'default';})
  .on('mouseenter',function(ev,d){
    var c=cellMap[d.key];
    if(!c) return;
    showTip('<strong>'+d.entity+'</strong><br>'+d.date+'<br>'+c.count+' communication'+(c.count!==1?'s':''),ev.clientX,ev.clientY);
    d3.select(this).attr('stroke','#1D9E75').attr('stroke-width',1.5);
  })
  .on('mousemove',function(ev){showTip(tip.innerHTML,ev.clientX,ev.clientY);})
  .on('mouseleave',function(){hideTip(); d3.select(this).attr('stroke',null);})
  .on('click',function(ev,d){
    var c=cellMap[d.key];
    if(!c) return;
    var h='<div style="font-size:11px;font-weight:600;color:#3d3d3a;margin-bottom:6px;">'
      +d.entity+' on '+d.date+'</div>'
      +'<div style="font-size:10px;color:#888780;margin-bottom:8px;">'+c.count+' communication'+(c.count!==1?'s':'')+'</div>';
    c.msgs.forEach(function(m){
      h+='<div style="background:#f8f7f4;border-radius:5px;padding:6px 8px;margin-bottom:6px;">'
        +'<div style="font-size:9px;font-weight:600;color:#534AB7;">'+m.ts+'  to '+m.to+'</div>'
        +'<div style="font-size:10px;color:#3d3d3a;line-height:1.5;margin-top:2px;">\u201c'
        +(m.content.length>160?m.content.slice(0,159)+'\u2026':m.content)+'\u201d</div></div>';
    });
    document.getElementById('cpanel').innerHTML=h;
  });

// ── Grid lines between rows ───────────────────────────────────────────────────
entities.forEach(function(ent,i){
  if(i>0)
    svg.append('line')
      .attr('x1',ML).attr('x2',ML+dates.length*cellW)
      .attr('y1',MT+i*cellH).attr('y2',MT+i*cellH)
      .attr('stroke','#e8e6e0').attr('stroke-width',.5);
});

// ── Colour scale legend bar ───────────────────────────────────────────────────
var legX=ML, legY=svgH-MB+6, legW=Math.min(200,dates.length*cellW);
var legGrad=svg.append('defs').append('linearGradient').attr('id','legGrad');
legGrad.append('stop').attr('offset','0%').attr('stop-color','#f1efe8');
legGrad.append('stop').attr('offset','100%').attr('stop-color','#085041');
svg.append('rect').attr('x',legX).attr('y',legY).attr('width',legW).attr('height',8)
  .attr('rx',3).attr('fill','url(#legGrad)');
svg.append('text').attr('x',legX).attr('y',legY-3).attr('font-size','8').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text('0');
svg.append('text').attr('x',legX+legW).attr('y',legY-3).attr('text-anchor','end').attr('font-size','8').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text(maxCount+' comms');
"""

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 3 JAVASCRIPT — Suspicion analysis ranked bar chart
    # ════════════════════════════════════════════════════════════════════════
    _p3_js = r"""
var tip3=document.getElementById('tip3');
function showTip3(html,x,y){
  tip3.innerHTML=html; tip3.style.display='block';
  tip3.style.left=Math.min(x+14,window.innerWidth-tip3.offsetWidth-10)+'px';
  tip3.style.top=(y-10)+'px';
}
function hideTip3(){ tip3.style.display='none'; }

// Show detail panel for a clicked entity
function showSuspDetail(d) {
  var col = d.color || '#888780';
  var h = '<div style="background:'+col+'18;border:1px solid '+col+'55;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    + '<div style="font-size:12px;font-weight:600;color:'+col+';">'+d.label+'</div>'
    + '<div style="font-size:10px;color:#73726c;margin-top:2px;">'+d.sub
    + (d.conflict?' <span style="color:#E24B4A;font-weight:600;">\u26A0 conflict entity</span>':'')+'</div></div>'
    + '<div style="font-size:10px;color:#3d3d3a;margin-bottom:8px;">Total suspicious evidence: <strong>'+d.ev+'</strong>  '
    + 'Suspicious connections: <strong>'+d.count+'</strong></div>'
    + '<div style="font-size:10px;font-weight:600;margin-bottom:6px;">Suspicious relationships</div>';
  d.rels.forEach(function(r){
    h += '<div style="background:#f8f7f4;border-radius:5px;padding:7px 9px;margin-bottom:6px;">'
      + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">'
      + '<span style="font-size:10px;font-weight:600;color:#E24B4A;">with '+r.partner+'</span>'
      + '<span style="font-size:9px;color:#888780;">'+r.ev+' evidence</span></div>';
    if (r.comms && r.comms.length) {
      h += '<div style="font-size:9px;color:#534AB7;font-weight:600;margin-bottom:2px;">Sample communication:</div>'
        + '<div style="font-size:9.5px;color:#3d3d3a;line-height:1.5;">\u201c'
        + (r.comms[0].text||'').slice(0,140)+'\u2026\u201d</div>';
    }
    h += '</div>';
  });
  document.getElementById('sp').innerHTML = h;
}

var top = SUSP.slice(0, 18); // Show top 18 entities by suspicion score
var maxEv = top.length ? top[0].ev : 1;

var ML=180, MT=20, MR=40, MB=20;
var BAR_H=30, BAR_GAP=6;
var BAR_AREA_W=window.innerWidth-ML-MR-280;
var svgW=ML+BAR_AREA_W+MR;
var svgH=MT+(top.length*(BAR_H+BAR_GAP))+MB+40;

var svg3=d3.select('#ssvg').attr('width',svgW).attr('height',svgH);

// Scale for bar width
var scX=d3.scaleLinear().domain([0,maxEv]).range([0,BAR_AREA_W]);

// ── Bars ──────────────────────────────────────────────────────────────────────
var barG = svg3.selectAll('.bg').data(top).join('g').attr('class','bg')
  .attr('transform',function(d,i){return 'translate(0,'+(MT+i*(BAR_H+BAR_GAP))+')';})
  .style('cursor','pointer')
  .on('mouseenter',function(ev,d){
    d3.select(this).select('.bar').attr('opacity',.85);
    showTip3('<strong>'+d.label+'</strong><br>Evidence: '+d.ev+'<br>Connections: '+d.count,ev.clientX,ev.clientY);
  })
  .on('mousemove',function(ev){showTip3(tip3.innerHTML,ev.clientX,ev.clientY);})
  .on('mouseleave',function(){d3.select(this).select('.bar').attr('opacity',1);hideTip3();})
  .on('click',function(ev,d){showSuspDetail(d);});

// Entity name label (left side)
barG.append('text').attr('x',ML-8).attr('y',BAR_H/2)
  .attr('text-anchor','end').attr('dominant-baseline','central')
  .attr('font-size','10.5').attr('font-family','system-ui,sans-serif')
  .attr('font-weight',function(d){return d.conflict?'600':'400';})
  .attr('fill',function(d){return d.color||'#3d3d3a';})
  .text(function(d){return d.label.length>22?d.label.slice(0,21)+'\u2026':d.label;});

// Subtype label (smaller, below name)
barG.append('text').attr('x',ML-8).attr('y',BAR_H/2+12)
  .attr('text-anchor','end').attr('dominant-baseline','central')
  .attr('font-size','8.5').attr('fill','#888780').attr('font-family','system-ui,sans-serif')
  .text(function(d){return d.sub+(d.conflict?' \u26A0':'');});

// Conflict entities get saturated red bars, others get lighter red
barG.append('rect').attr('class','bar')
  .attr('x',ML).attr('y',4).attr('height',BAR_H-8).attr('rx',4)
  .attr('width',function(d){return Math.max(4,scX(d.ev));})
  .attr('fill',function(d){return d.conflict?'#E24B4A':'#F0A0A0';});

// Evidence count label at end of bar
barG.append('text')
  .attr('x',function(d){return ML+scX(d.ev)+6;})
  .attr('y',BAR_H/2).attr('dominant-baseline','central')
  .attr('font-size','9').attr('fill','#73726c').attr('font-family','system-ui,sans-serif')
  .text(function(d){return d.ev+' ev, '+d.count+' conn';});

// ── X axis ────────────────────────────────────────────────────────────────────
var axisY = MT + top.length*(BAR_H+BAR_GAP)+10;
svg3.append('line').attr('x1',ML).attr('x2',ML+BAR_AREA_W).attr('y1',axisY).attr('y2',axisY)
  .attr('stroke','#d3d1c7').attr('stroke-width',.5);
svg3.append('text').attr('x',ML).attr('y',axisY+14).attr('font-size','9').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text('0');
svg3.append('text').attr('x',ML+BAR_AREA_W).attr('y',axisY+14).attr('text-anchor','end').attr('font-size','9').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text('Total suspicious evidence');

// ── Legend ────────────────────────────────────────────────────────────────────
var legY=axisY+28;
svg3.append('rect').attr('x',ML).attr('y',legY).attr('width',16).attr('height',10).attr('rx',2).attr('fill','#E24B4A');
svg3.append('text').attr('x',ML+20).attr('y',legY+5).attr('dominant-baseline','central').attr('font-size','9').attr('fill','#73726c').attr('font-family','system-ui,sans-serif').text('Conflict entity (Suspicious AND Colleagues)');
svg3.append('rect').attr('x',ML+230).attr('y',legY).attr('width',16).attr('height',10).attr('rx',2).attr('fill','#F0A0A0');
svg3.append('text').attr('x',ML+250).attr('y',legY+5).attr('dominant-baseline','central').attr('font-size','9').attr('fill','#73726c').attr('font-family','system-ui,sans-serif').text('Suspicious only');
"""

    # ════════════════════════════════════════════════════════════════════════
    # HTML TEMPLATES for all three pages
    # ════════════════════════════════════════════════════════════════════════

    _p1_html = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
html,body{margin:0;padding:0;overflow:hidden;width:100%;height:100%;
  font-family:system-ui,-apple-system,sans-serif;background:#f1efe8;}
#wrap{display:flex;flex-direction:column;height:100vh;}
#hdr{display:flex;align-items:center;justify-content:space-between;padding:7px 16px;
  background:#f8f7f4;border-bottom:1px solid #d3d1c7;flex-shrink:0;flex-wrap:wrap;gap:6px;}
#hdr-t{font-size:13px;font-weight:600;color:#1a1a18;}
#hdr-s{font-size:10px;color:#73726c;display:flex;gap:14px;flex-wrap:wrap;}
#hdr-b{display:flex;gap:4px;}
.zb{padding:3px 10px;border-radius:4px;border:1px solid #d3d1c7;background:#fff;font-size:11px;cursor:pointer;color:#3d3d3a;}
.zb:hover{background:#f1efe8;}
#main{display:flex;flex:1;min-height:0;}
#canvas{flex:1;min-width:0;overflow:hidden;}
#svg{display:block;cursor:grab;width:100%;height:100%;}
#svg:active{cursor:grabbing;}
#tip{position:fixed;display:none;background:rgba(26,26,24,.88);color:#fff;
  padding:6px 10px;border-radius:6px;font-size:11px;pointer-events:none;max-width:240px;line-height:1.5;z-index:999;}
#panel{width:264px;min-width:264px;border-left:1px solid #d3d1c7;background:#fff;display:flex;flex-direction:column;overflow:hidden;}
#ph{padding:9px 13px;font-size:11px;font-weight:600;color:#534AB7;background:#EEEDFE;border-bottom:1px solid #AFA9EC;flex-shrink:0;}
#pb{padding:11px 13px;flex:1;overflow-y:auto;}
.pp{font-size:11px;color:#888780;line-height:1.7;padding:16px 0;text-align:center;}
#leg{display:flex;gap:10px;padding:6px 16px;background:#f8f7f4;border-top:1px solid #d3d1c7;flex-wrap:wrap;align-items:center;flex-shrink:0;}
.li{display:flex;align-items:center;gap:4px;font-size:9px;color:#73726c;}
.ll{display:inline-block;width:20px;height:3px;border-radius:2px;}
.ln{font-size:9px;color:#b4b2a9;margin-left:auto;}
</style></head><body>
<div id="wrap">
  <div id="hdr">
    <span id="hdr-t">EvidenceBoard &mdash; Oceanus Investigation, Oct 2040</span>
    <div id="hdr-s">
      <span>EC entities</span><span>RC relationships</span>
      <span>CC conflicts</span><span>GC predicted missing</span>
    </div>
    <div id="hdr-b">
      <button class="zb" id="bi">+ Zoom</button>
      <button class="zb" id="bo">&minus; Zoom</button>
      <button class="zb" id="br">Reset view</button>
    </div>
  </div>
  <div id="main">
    <div id="canvas"><svg id="svg"></svg><div id="tip"></div></div>
    <div id="panel">
      <div id="ph">Evidence detail</div>
      <div id="pb">
        <p class="pp">Click any string to see its evidence chain.<br>
        Click any entity card to see its connections.<br>
        Click background to reset focus.</p>
      </div>
    </div>
  </div>
  <div id="leg">
    <div class="li"><span class="ll" style="background:#E24B4A;height:4px"></span>Suspicious</div>
    <div class="li"><span class="ll" style="background:#1D9E75"></span>Colleagues / Friends</div>
    <div class="li"><span class="ll" style="background:#534AB7;height:2.5px"></span>Operates</div>
    <div class="li"><span class="ll" style="background:#BA7517;height:2px"></span>AccessPermission</div>
    <div class="li"><span class="ll" style="background:#185FA5;height:2px"></span>Coordinates</div>
    <div class="li">
      <svg width="22" height="5"><line x1="0" y1="2.5" x2="22" y2="2.5" stroke="#888780" stroke-width="2" stroke-dasharray="5,4"/></svg>
      Predicted missing
    </div>
    <span class="ln">Drag cards &middot; Scroll to zoom &middot; Click card or string to focus &middot; Click again to reset</span>
  </div>
</div>
<script>P1_DATA P1_CODE</script>
</body></html>"""

    _p2_html = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
html,body{margin:0;padding:0;overflow:auto;width:100%;height:100%;
  font-family:system-ui,-apple-system,sans-serif;background:#f1efe8;}
#wrap{display:flex;flex-direction:column;height:100vh;}
#hdr2{padding:10px 16px;background:#f8f7f4;border-bottom:1px solid #d3d1c7;flex-shrink:0;}
#hdr2 h2{margin:0;font-size:13px;font-weight:600;color:#1a1a18;}
#hdr2 p{margin:4px 0 0;font-size:10px;color:#73726c;}
#body2{display:flex;flex:1;min-height:0;}
#heatmap-area{flex:1;overflow:auto;padding:12px 16px;}
#cpanel{width:264px;min-width:264px;padding:12px 14px;border-left:1px solid #d3d1c7;
  background:#fff;overflow-y:auto;font-size:11px;color:#888780;}
#tip2{position:fixed;display:none;background:rgba(26,26,24,.88);color:#fff;
  padding:6px 10px;border-radius:6px;font-size:11px;pointer-events:none;max-width:200px;line-height:1.5;z-index:999;}
</style></head><body>
<div id="wrap">
  <div id="hdr2">
    <h2>Communication timeline &mdash; Oct 1 to 14, 2040</h2>
    <p>Top 25 entities by total message volume. Cell colour intensity encodes daily communication count.
    Click any cell to read the messages. Conflict entities are marked with a red dot.</p>
  </div>
  <div id="body2">
    <div id="heatmap-area"><svg id="heatsvg"></svg></div>
    <div id="cpanel">Click any coloured cell to see the communications for that entity on that day.</div>
  </div>
</div>
<div id="tip2"></div>
<script>P2_DATA P2_CODE</script>
</body></html>"""

    _p3_html = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
html,body{margin:0;padding:0;overflow:hidden;width:100%;height:100%;
  font-family:system-ui,-apple-system,sans-serif;background:#f1efe8;}
#wrap3{display:flex;flex-direction:column;height:100vh;}
#hdr3{padding:10px 16px;background:#f8f7f4;border-bottom:1px solid #d3d1c7;flex-shrink:0;}
#hdr3 h2{margin:0;font-size:13px;font-weight:600;color:#1a1a18;}
#hdr3 p{margin:4px 0 0;font-size:10px;color:#73726c;}
#body3{display:flex;flex:1;min-height:0;}
#chart-area{flex:1;overflow:auto;padding:12px 0 12px 16px;}
#sp{width:280px;min-width:280px;padding:12px 14px;border-left:1px solid #d3d1c7;
  background:#fff;overflow-y:auto;font-size:11px;color:#888780;}
#tip3{position:fixed;display:none;background:rgba(26,26,24,.88);color:#fff;
  padding:6px 10px;border-radius:6px;font-size:11px;pointer-events:none;max-width:200px;line-height:1.5;z-index:999;}
</style></head><body>
<div id="wrap3">
  <div id="hdr3">
    <h2>Suspicion network analysis &mdash; Oceanus Investigation, Oct 2040</h2>
    <p>Entities ranked by total suspicious relationship evidence. Red bars are conflict entities
    (have both Suspicious and Colleagues relationships). Click any bar to see relationship details.</p>
  </div>
  <div id="body3">
    <div id="chart-area"><svg id="ssvg"></svg></div>
    <div id="sp">Click any bar to see this entity's suspicious relationships and key communications.</div>
  </div>
</div>
<div id="tip3"></div>
<script>P3_DATA P3_CODE</script>
</body></html>"""

    # ── Inject data and code into HTML templates ───────────────────────────────
    _p1_html = (_p1_html
        .replace("EC", str(len(_ve)))
        .replace("RC", str(len(_vr)))
        .replace("CC", str(_nc))
        .replace("GC", str(len(_vg)))
        .replace("P1_DATA", _p1_data)
        .replace("P1_CODE", _p1_js))

    _p2_html = _p2_html.replace("P2_DATA", _p2_data).replace("P2_CODE", _p2_js)
    _p3_html = _p3_html.replace("P3_DATA", _p3_data).replace("P3_CODE", _p3_js)

    # ── EvidenceBoard controls above Tab 1 ────────────────────────────────────
    _controls = mo.hstack(
        [threshold, etype_filter, rtype_filter, ghost_toggle, conflict_only],
        gap=2, wrap=True,
    )

    # ── Assemble three-page dashboard in tabs ─────────────────────────────────
    _tab1 = mo.vstack([_controls, mo.iframe(_p1_html, height="720px")])
    _tab2 = mo.iframe(_p2_html, height="720px")
    _tab3 = mo.iframe(_p3_html, height="720px")

    _tabs = mo.ui.tabs({
        "EvidenceBoard":           _tab1,
        "Communication timeline":  _tab2,
        "Suspicion analysis":      _tab3,
    })
    _tabs
