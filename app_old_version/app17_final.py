import marimo

__generated_with = "0.22.4"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import json as _json
    from collections import defaultdict as _dd

    # Load the MC3 knowledge graph JSON — 1,159 nodes, 3,226 edges
    # Dataset: Oceanus coastal investigation, Oct 2040 (VAST 2025 challenge)
    with open("data/MC3_graph.json") as _f:
        _raw = _json.load(_f)

    _nodes = _raw["nodes"]
    _edges = _raw["edges"]
    _nmap  = {n["id"]: n for n in _nodes}

    # Split nodes by type: entities (people, vessels, orgs, locations),
    # relationship nodes, and communication events
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

    # Entity-pair communication counts (ghost link detection)
    _pair = _dd(list)
    for _cid, _snd in _csnd.items():
        _rcv = _crcv.get(_cid)
        if _rcv and _snd != _rcv:
            _pair[tuple(sorted([_snd, _rcv]))].append(_cid)

    # Build relationship objects with evidence chains AND daily breakdown
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

        # Up to 8 comms for the detail panel
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

        # Daily breakdown for ALL comms — used for temporal burst chart
        _rel_daily = {}
        for _cid in _comms:
            _cn  = _nmap.get(_cid, {})
            _dt  = (_cn.get("timestamp") or "")[:10]
            if _dt:
                _rel_daily[_dt] = _rel_daily.get(_dt, 0) + 1

        all_rels.append({
            "id":    _rid,
            "sub":   _rn.get("sub_type", "Unknown"),
            "ents":  _ents[:2],
            "ev":    _ev,
            "comms": _cdets,
            "daily": _rel_daily,
        })

    # Conflict entities: Suspicious AND (Colleagues OR Friends)
    _ert = _dd(set)
    for _r in all_rels:
        for _eid in _r["ents"]:
            _ert[_eid].add(_r["sub"])
    # Conflict entities: have BOTH Suspicious AND Colleagues/Friends relationship
    # This contradiction is a key investigative signal for Task 2 of the VAST challenge
    _conflicts = frozenset(
        _eid for _eid, _st in _ert.items()
        if "Suspicious" in _st and ("Colleagues" in _st or "Friends" in _st)
    )

    # Ghost links: 5+ comms, no relationship node
    # Ghost links: entity pairs with 5+ communications but no relationship node
    # These represent predicted data gaps in the knowledge graph construction
    # Rendered as dashed strings using epistemic uncertainty encoding (MacEachren et al. 2012)
    _existing = {tuple(sorted(_r["ents"][:2])) for _r in all_rels}
    all_ghosts = [
        {"a": _p[0], "b": _p[1], "n": len(_c)}
        for _p, _c in _pair.items()
        if len(_c) >= 5 and _p not in _existing
    ]

    # Colour maps (single source of truth — identical to JS REL_COLORS)
    _EC = {"Person":"#1D9E75","Organization":"#534AB7","Vessel":"#185FA5",
           "Group":"#BA7517","Location":"#888780"}
    _RC = {"Suspicious":"#E24B4A","Colleagues":"#1D9E75","Friends":"#1D9E75",
           "Operates":"#534AB7","AccessPermission":"#BA7517","Coordinates":"#185FA5",
           "Jurisdiction":"#185FA5","Reports":"#3B8BD4","Unfriendly":"#D85A30"}

    # Entity records (layout assigned by D3 force at runtime)
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

    # Per-entity communication statistics: used for activity sparklines in the evidence panel
    # Tracks sent/received counts and daily breakdown across the 14-day investigation window
    # ── Per-entity communication statistics (for sparklines) ─────────────────
    _estats = _dd(lambda: {"sent": 0, "rcv": 0, "daily": {}})
    for _cid, _snd in _csnd.items():
        _cn  = _nmap.get(_cid, {})
        _dt  = (_cn.get("timestamp") or "")[:10]
        _estats[_snd]["sent"] += 1
        if _dt:
            _estats[_snd]["daily"][_dt] = _estats[_snd]["daily"].get(_dt, 0) + 1
    for _cid, _rcv in _crcv.items():
        _estats[_rcv]["rcv"] += 1
    ent_stats = dict(_estats)

    # Communication timeline data: top 25 senders x 14 dates heatmap
    # Task 1 of the VAST challenge: identify daily temporal patterns in communications
    # ── Page 2: Communication timeline ───────────────────────────────────────
    _all_comms = []
    for _cn in _comm_nodes:
        _cid  = _cn["id"]
        _ts   = (_cn.get("timestamp") or "")[:16]
        _date = _ts[:10]
        _snd  = _csnd.get(_cid, "")
        _rcv  = _crcv.get(_cid, "")
        if _snd and _rcv and _date:
            _all_comms.append({
                "ts": _ts, "date": _date,
                "sender": _snd, "to": _rcv,
                "content": (_cn.get("content") or "")[:150],
            })
    _all_comms.sort(key=lambda x: x["ts"])

    # Top 25 senders by total message count
    _etotals = _dd(int)
    for _c in _all_comms:
        _etotals[_c["sender"]] += 1
    _top25 = sorted(_etotals.keys(), key=lambda x: -_etotals[x])[:25]
    _all_dates = sorted(set(_c["date"] for _c in _all_comms))

    _heat = _dd(lambda: _dd(list))
    for _c in _all_comms:
        if _c["sender"] in _top25:
            _heat[_c["sender"]][_c["date"]].append({
                "ts": _c["ts"], "to": _c["to"], "content": _c["content"],
            })

    heat_data = {
        "entities": _top25,
        "dates":    _all_dates,
        "cells": [
            {"entity": _ent, "date": _d, "count": len(_msgs), "msgs": _msgs}
            for _ent, _dates in _heat.items()
            for _d, _msgs in _dates.items()
        ],
        "totals":    {_eid: _etotals[_eid] for _eid in _top25},
        "colors":    {_eid: _EC.get(_nmap.get(_eid,{}).get("sub_type",""), "#888780") for _eid in _top25},
        "conflicts": {_eid: (_eid in _conflicts) for _eid in _top25},
    }

    # Daily totals across all entities (for timeline bar chart)
    _dtotals = {}
    for _c in _all_comms:
        _dtotals[_c["date"]] = _dtotals.get(_c["date"], 0) + 1
    daily_totals = _dtotals

    # Suspicion analysis data: entities ranked by total suspicious relationship evidence
    # Task 2 of the VAST challenge: find anomalous entities and suspicious relationships
    # ── Page 3: Suspicion analysis ────────────────────────────────────────────
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
                    "comms":   _r["comms"],
                })

    susp_data = []
    for _eid, _info in _ss.items():
        _en = _nmap.get(_eid, {})
        susp_data.append({
            "id":       _eid,
            "label":    _en.get("label", _eid),
            "sub":      _en.get("sub_type", "Unknown"),
            "color":    _EC.get(_en.get("sub_type",""), "#888780"),
            "conflict": _eid in _conflicts,
            "count":    _info["count"],
            "ev":       _info["ev"],
            "rels":     sorted(_info["rels"], key=lambda r: -r["ev"]),
        })
    susp_data.sort(key=lambda x: -(x["ev"] + x["count"] * 2))
    return (
        MAX_EV,
        all_ents,
        all_ghosts,
        all_rels,
        all_subtypes,
        daily_totals,
        ent_stats,
        heat_data,
        susp_data,
    )


@app.cell
def _(MAX_EV, all_subtypes, mo):
    threshold     = mo.ui.slider(1, MAX_EV, value=2, label="Min. evidence", show_value=True)
    etype_filter  = mo.ui.dropdown(
        ["All","Person","Organization","Vessel","Group","Location"],
        value="All", label="Entity type",
    )
    rtype_filter  = mo.ui.dropdown(
        ["All"] + all_subtypes, value="All", label="Relationship type",
    )
    ghost_toggle  = mo.ui.switch(value=True,  label="Ghost links")
    conflict_only = mo.ui.switch(value=False, label="Conflicts only")
    return conflict_only, etype_filter, ghost_toggle, rtype_filter, threshold


@app.cell
def _(
    MAX_EV,
    all_ents,
    all_ghosts,
    all_rels,
    conflict_only,
    daily_totals,
    ent_stats,
    etype_filter,
    ghost_toggle,
    heat_data,
    mo,
    rtype_filter,
    susp_data,
    threshold,
):
    import json as _js

    # Read control values
    _ef = etype_filter.value
    _rf = rtype_filter.value
    _sg = ghost_toggle.value
    _mn = threshold.value
    _co = conflict_only.value

    # Filter entities and relationships
    _ve = [e for e in all_ents if (_ef=="All" or e["sub"]==_ef) and (not _co or e["conflict"])]
    _vi = {e["id"] for e in _ve}
    _vr = [r for r in all_rels if r["ev"]>=_mn and (_rf=="All" or r["sub"]==_rf)
           and r["ents"][0] in _vi and r["ents"][1] in _vi]
    _vg = [g for g in all_ghosts if _sg and g["a"] in _vi and g["b"] in _vi]

    # Remove isolated entities (no visible connections)
    _conn = set()
    for _r in _vr: _conn.add(_r["ents"][0]); _conn.add(_r["ents"][1])
    for _g in _vg: _conn.add(_g["a"]); _conn.add(_g["b"])
    _ve = [e for e in _ve if e["id"] in _conn]
    _nc = sum(1 for e in _ve if e["conflict"])

    # Serialise filtered Python data to JavaScript variables
    # These get injected into the HTML iframe templates as inline <script> data
    # Serialise to JavaScript
    _p1_data = (
        "var E="        + _js.dumps(_ve,         ensure_ascii=False) + ";\n"
        "var R="        + _js.dumps(_vr,         ensure_ascii=False) + ";\n"
        "var GH="       + _js.dumps(_vg,         ensure_ascii=False) + ";\n"
        "var MEV="      + str(MAX_EV)                                + ";\n"
        "var ESTATS="   + _js.dumps(ent_stats,   ensure_ascii=False) + ";\n"
        "var ALL_DATES=" + _js.dumps(heat_data["dates"], ensure_ascii=False) + ";\n"
    )
    _p2_data = (
        "var HEAT="    + _js.dumps(heat_data,   ensure_ascii=False) + ";\n"
        "var DTOTALS=" + _js.dumps(daily_totals, ensure_ascii=False) + ";\n"
    )
    _p3_data = ("var SUSP=" + _js.dumps(susp_data, ensure_ascii=False) + ";\n"
                + "var ALL_DATES3=" + _js.dumps(heat_data["dates"], ensure_ascii=False) + ";\n")

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 1: EvidenceBoard JavaScript
    # D3 v7 force simulation with entity cards and relationship strings
    # Visual encoding: stroke width = evidence count (Ware 2004)
    #                  stroke opacity = confidence level (MacEachren et al. 2012)
    # Interactive layers: focus mode, drag, zoom/pan, investigation queue
    # Layer 2: click relationship type pill to drill into specific partners
    # ════════════════════════════════════════════════════════════════════════
    _p1_js = r"""

    var REL_COLORS={Suspicious:'#E24B4A',Colleagues:'#1D9E75',Friends:'#1D9E75',
      Operates:'#534AB7',AccessPermission:'#BA7517',Coordinates:'#185FA5',
      Jurisdiction:'#185FA5',Reports:'#3B8BD4',Unfriendly:'#D85A30'};
    var CW=124,CH=54,HH=17;
    function strokeW(ev){return Math.max(2,Math.min(10,ev*0.6+1.5));}
    function strokeO(ev){return Math.max(0.35,Math.min(0.95,ev/MEV*2+0.35));}
    function trunc(s,n){return s&&s.length>n?s.slice(0,n-1)+'\u2026':(s||'');}

    var lastClickedEnt=null;
    var _backFn=null; // navigation: stores function to call when back button is pressed

    function _navBack(){if(_backFn){var fn=_backFn;_backFn=null;fn();}}

    // ── D3 sparkline ─────────────────────────────────────────────────────────────
    function renderSparkline(eid,color){
      var ctr=document.getElementById('spark-ctr');if(!ctr)return;
      d3.select(ctr).selectAll('*').remove();
      var stats=ESTATS[eid]||{},daily=stats.daily||{};
      if(!ALL_DATES.length)return;
      var maxV=1;ALL_DATES.forEach(function(d){if((daily[d]||0)>maxV)maxV=daily[d];});
      var W=232,H=50,n=ALL_DATES.length,bw=Math.max(2,Math.floor((W-n)/n));
      var peakD='',peakV=0;ALL_DATES.forEach(function(d){if((daily[d]||0)>peakV){peakV=daily[d]||0;peakD=d;}});
      var svg=d3.select(ctr).append('svg').attr('width',W).attr('height',H+16);
      svg.append('line').attr('x1',0).attr('y1',H-2).attr('x2',W).attr('y2',H-2).attr('stroke','#d3d1c7').attr('stroke-width',0.5);
      ALL_DATES.forEach(function(d,i){
    var v=daily[d]||0,bh=v>0?Math.max(3,Math.round(v/maxV*(H-10))):2,op=v>0?(0.45+v/maxV*0.5):0.12;
    var fill=v>0?(color||'#1D9E75'):'#e0ddd6';
    var bar=svg.append('rect').attr('x',i*(bw+1)).attr('y',H-bh-2).attr('width',bw).attr('height',bh).attr('fill',fill).attr('opacity',op).attr('rx',1).style('cursor',v>0?'pointer':'default');
    if(v>0){bar.on('mouseenter',function(ev){d3.select(this).attr('opacity',1).attr('stroke','#333').attr('stroke-width',0.5);var t=document.getElementById('tip');if(t){t.innerHTML='<strong>'+d.slice(8)+'-'+d.slice(5,7)+'</strong><br>'+v+' comm'+(v!==1?'s':'');t.style.display='block';t.style.left=Math.min(ev.clientX+14,window.innerWidth-150)+'px';t.style.top=(ev.clientY-10)+'px';}}).on('mouseleave',function(){d3.select(this).attr('opacity',op).attr('stroke',null);var t=document.getElementById('tip');if(t)t.style.display='none';});}
    if(d===peakD&&peakV>0)svg.append('text').attr('x',i*(bw+1)+bw/2).attr('y',H-bh-4).attr('text-anchor','middle').attr('font-size','7.5').attr('fill',color||'#1D9E75').attr('font-family','system-ui').text(d.slice(8)+'-'+d.slice(5,7));
      });
      svg.append('text').attr('x',0).attr('y',H+13).attr('font-size','7.5').attr('fill','#888780').attr('font-family','system-ui').text(ALL_DATES[0].slice(8)+'-'+ALL_DATES[0].slice(5,7));
      svg.append('text').attr('x',W).attr('y',H+13).attr('text-anchor','end').attr('font-size','7.5').attr('fill','#888780').attr('font-family','system-ui').text(ALL_DATES[ALL_DATES.length-1].slice(8)+'-'+ALL_DATES[ALL_DATES.length-1].slice(5,7));
    }

    // ── D3 burst chart ────────────────────────────────────────────────────────────
    function renderBurst(r){
      var ctr=document.getElementById('burst-ctr');if(!ctr)return;
      d3.select(ctr).selectAll('*').remove();
      var daily=r.daily||{};
      if(!ALL_DATES.some(function(d){return (daily[d]||0)>0;})){d3.select(ctr).append('p').style('font-size','10px').style('color','#888780').text('No temporal data.');return;}
      var maxV=1;ALL_DATES.forEach(function(d){if((daily[d]||0)>maxV)maxV=daily[d];});
      var col=r.color||'#888780',W=232,H=44,n=ALL_DATES.length,bw=Math.max(2,Math.floor((W-n)/n));
      var svg=d3.select(ctr).append('svg').attr('width',W).attr('height',H+16);
      svg.append('line').attr('x1',0).attr('y1',H-2).attr('x2',W).attr('y2',H-2).attr('stroke','#d3d1c7').attr('stroke-width',0.5);
      ALL_DATES.forEach(function(d,i){
    var v=daily[d]||0,bh=v>0?Math.max(3,Math.round(v/maxV*(H-8))):2;
    var bar=svg.append('rect').attr('x',i*(bw+1)).attr('y',H-bh-2).attr('width',bw).attr('height',bh).attr('fill',col).attr('opacity',v>0?0.85:0.1).attr('rx',1).style('cursor',v>0?'pointer':'default');
    if(v>0){bar.on('mouseenter',function(ev){d3.select(this).attr('opacity',1).attr('stroke','#333').attr('stroke-width',0.5);var t=document.getElementById('tip');if(t){t.innerHTML='<strong>'+d.slice(8)+'-'+d.slice(5,7)+'</strong><br>'+v+' comm'+(v!==1?'s':'');t.style.display='block';t.style.left=Math.min(ev.clientX+14,window.innerWidth-150)+'px';t.style.top=(ev.clientY-10)+'px';}}).on('mouseleave',function(){d3.select(this).attr('opacity',0.85).attr('stroke',null);var t=document.getElementById('tip');if(t)t.style.display='none';});
    if(bh>12)svg.append('text').attr('x',i*(bw+1)+bw/2).attr('y',H-bh/2-2).attr('text-anchor','middle').attr('dominant-baseline','central').attr('font-size','7').attr('fill','white').attr('pointer-events','none').attr('font-family','system-ui').text(v);}
      });
      svg.append('text').attr('x',0).attr('y',H+13).attr('font-size','7.5').attr('fill','#888780').attr('font-family','system-ui').text(ALL_DATES[0].slice(8)+'-'+ALL_DATES[0].slice(5,7));
      svg.append('text').attr('x',W).attr('y',H+13).attr('text-anchor','end').attr('font-size','7.5').attr('fill','#888780').attr('font-family','system-ui').text(ALL_DATES[ALL_DATES.length-1].slice(8)+'-'+ALL_DATES[ALL_DATES.length-1].slice(5,7));
    }

    // ── Layer 2: mini network (now receives typeName for back-nav) ────────────────
    function renderMiniNetwork(eid,typeName,typeRels,col){
      var ctr=document.getElementById('mini-net-ctr');if(!ctr)return;
      d3.select(ctr).selectAll('*').remove();
      var n=Math.min(typeRels.length,7);if(!n)return;
      var W=238,H=160,cx=W/2,cy=H/2,r=58;
      var svg=d3.select(ctr).append('svg').attr('width',W).attr('height',H);
      typeRels.slice(0,n).forEach(function(rel,i){
    var pid=rel.ents[0]===eid?rel.ents[1]:rel.ents[0];
    var a=(2*Math.PI*i/n)-Math.PI/2,px=cx+r*Math.cos(a),py=cy+r*Math.sin(a);
    var sw=Math.max(1.5,Math.min(5,rel.ev*0.5+1));
    svg.append('line').attr('x1',cx).attr('y1',cy).attr('x2',px).attr('y2',py).attr('stroke',col).attr('stroke-width',sw).attr('stroke-opacity',0.55);
    var g=svg.append('g').style('cursor','pointer')
      // Pass backFn so clicking a partner gives a back button to this reltype view
      .on('click',function(){showRel(rel,function(){showRelType(eid,typeName);});})
      .on('mouseenter',function(ev){d3.select(this).select('circle').attr('fill',col+'22');var t=document.getElementById('tip');if(t){t.innerHTML='<strong>'+pid+'</strong><br>'+rel.ev+' evidence<br><em>Click to see evidence chain</em>';t.style.display='block';t.style.left=Math.min(ev.clientX+14,window.innerWidth-160)+'px';t.style.top=(ev.clientY-10)+'px';}})
      .on('mouseleave',function(){d3.select(this).select('circle').attr('fill','#f8f7f4');var t=document.getElementById('tip');if(t)t.style.display='none';});
    g.append('circle').attr('cx',px).attr('cy',py).attr('r',9).attr('fill','#f8f7f4').attr('stroke',col).attr('stroke-width',1.5).attr('stroke-opacity',0.7);
    var lR=r+26,lx=cx+lR*Math.cos(a),ly=cy+lR*Math.sin(a);
    var pl=pid.length>11?pid.slice(0,10)+'\u2026':pid;
    svg.append('text').attr('x',lx).attr('y',ly).attr('text-anchor','middle').attr('dominant-baseline','central').attr('font-size','7').attr('fill','#3d3d3a').attr('font-family','system-ui').text(pl);
      });
      svg.append('circle').attr('cx',cx).attr('cy',cy).attr('r',20).attr('fill',col).attr('stroke','white').attr('stroke-width',2);
      var el=eid.length>10?eid.slice(0,9)+'\u2026':eid;
      svg.append('text').attr('x',cx).attr('y',cy).attr('text-anchor','middle').attr('dominant-baseline','central').attr('font-size','7.5').attr('font-weight','600').attr('fill','white').attr('font-family','system-ui').text(el);
      svg.append('text').attr('x',W/2).attr('y',H-2).attr('text-anchor','middle').attr('font-size','7.5').attr('fill','#888780').attr('font-family','system-ui').text('Click any partner to see evidence chain');
    }

    function showRelType(eid,typeName){
      var col=REL_COLORS[typeName]||'#888780';
      var typeRels=R.filter(function(r){return r.sub===typeName&&(r.ents[0]===eid||r.ents[1]===eid);});
      if(!typeRels.length)return;
      var h='<div style="display:flex;align-items:center;gap:7px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #f1efe8;">'
    +'<button onclick="showEnt(lastClickedEnt)" style="padding:3px 8px;border-radius:4px;border:1px solid #d3d1c7;background:#fff;font-size:10px;cursor:pointer;color:#73726c;">\u2190 Back</button>'
    +'<span style="font-size:11px;font-weight:600;color:'+col+';">'+typeName+' ('+typeRels.length+')</span></div>'
    +'<div style="font-size:10px;font-weight:600;color:#3d3d3a;margin-bottom:4px;">Connection network</div>'
    +'<div id="mini-net-ctr" style="margin-bottom:10px;"></div>'
    +'<div style="font-size:10px;font-weight:600;color:#3d3d3a;margin-bottom:6px;">Partners by evidence</div>'
    +'<div id="partner-list-ctr"></div>';
      document.getElementById('pb').innerHTML=h;
      renderMiniNetwork(eid,typeName,typeRels,col);
      var listCtr=document.getElementById('partner-list-ctr');
      if(listCtr){
    var sel=d3.select(listCtr).selectAll('.pl').data(typeRels.slice(0,6)).join('div').attr('class','pl')
      .style('background','#f8f7f4').style('border-radius','5px').style('padding','7px 9px')
      .style('margin-bottom','6px').style('cursor','pointer')
      .on('click',function(ev,r){
        // Pass backFn so the evidence chain has a back button to this view
        showRel(r,function(){showRelType(eid,typeName);});
      })
      .on('mouseenter',function(){d3.select(this).style('background','#ede9e0');})
      .on('mouseleave',function(){d3.select(this).style('background','#f8f7f4');});
    sel.each(function(r){
      var pid=r.ents[0]===eid?r.ents[1]:r.ents[0];var div=d3.select(this);
      div.append('div').style('display','flex').style('justify-content','space-between').style('margin-bottom','3px')
        .html('<span style="font-size:10px;font-weight:600;color:'+col+';">'+pid+'</span>'
          +'<span style="font-size:9px;color:#888780;">'+r.ev+' evidence</span>');
      if(r.comms&&r.comms.length){var c=r.comms[0];
        div.append('div').style('font-size','9px').style('color','#888780').style('margin-top','2px').text(c.ts+'  '+c.from+' to '+c.to);
        div.append('div').style('font-size','9.5px').style('color','#3d3d3a').style('line-height','1.5').style('margin-top','2px')
          .text('\u201c'+(c.text||'').slice(0,100)+((c.text&&c.text.length>100)?'\u2026':'')+'\u201d');
      }
    });
      }
      renderQueue();
    }

    // ── Investigation queue ────────────────────────────────────────────────────────
    var queue=[],currentRel=null;
    function escalate(){if(!currentRel)return;if(!queue.some(function(q){return q.id===currentRel.id;}))queue.push(currentRel);renderQueue();var b=document.getElementById('qbanner');if(b){b.style.display='block';b.textContent='Added to queue ('+queue.length+')';setTimeout(function(){b.style.display='none';},2000);}}
    function removeFromQueue(i){queue.splice(i,1);renderQueue();}
    function renderQueue(){var el=document.getElementById('qsec');if(!el||!queue.length){if(el)el.innerHTML='';return;}var h='<div style="border-top:1px solid #d3d1c7;margin-top:14px;padding-top:10px;"><div style="font-size:10px;font-weight:600;color:#3d3d3a;margin-bottom:6px;">Investigation queue ('+queue.length+')</div>';queue.forEach(function(r,i){var col=r.color||'#888780';h+='<div style="background:#f8f7f4;border-radius:5px;padding:6px 9px;margin-bottom:5px;display:flex;justify-content:space-between;align-items:flex-start;"><div><span style="font-size:9.5px;font-weight:600;color:'+col+';">'+r.sub+'</span><div style="font-size:9px;color:#73726c;margin-top:1px;">'+r.ents.join(' and ')+'</div><div style="font-size:8.5px;color:#888780;">Evidence: '+r.ev+'</div></div><button onclick="removeFromQueue('+i+')" style="font-size:13px;color:#888780;background:none;border:none;cursor:pointer;">&times;</button></div>';});el.innerHTML=h+'</div>';}

    function clearPanel(){currentRel=null;_backFn=null;generateInsightsPanel();var qs=document.getElementById('qsec');if(qs)renderQueue();}

    function showRel(r,optBackFn){
      currentRel=r;_backFn=optBackFn||null;
      var col=r.color||'#888780',pct=Math.round(r.ev/MEV*100),lbl=pct<30?'Low':pct<65?'Medium':'High';
      var backBtn=_backFn?'<button onclick="_navBack()" style="padding:3px 8px;border-radius:4px;border:1px solid #d3d1c7;background:#fff;font-size:10px;cursor:pointer;color:#73726c;margin-bottom:8px;">\u2190 Back</button><br>':'';
      var h=backBtn
    +'<div style="background:'+col+'18;border:1px solid '+col+'55;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    +'<div style="font-size:11px;font-weight:600;color:'+col+';">'+r.sub+' relationship</div>'
    +'<div style="font-size:10px;color:#73726c;margin-top:2px;">'+(r.ents||[]).join(' and ')+'</div></div>'
    +'<div style="font-size:10px;font-weight:600;margin:6px 0 3px;">Evidence confidence</div>'
    +'<div style="height:8px;background:#f1efe8;border-radius:4px;overflow:hidden;"><div style="height:100%;width:'+Math.min(100,pct)+'%;background:'+col+';opacity:.85;border-radius:4px;"></div></div>'
    +'<div style="display:flex;justify-content:space-between;font-size:9px;color:#888780;margin:2px 0 8px;"><span>'+lbl+' ('+pct+'%)</span><span>'+r.ev+' of '+MEV+' max</span></div>'
    +'<div style="font-size:10px;font-weight:600;color:#3d3d3a;margin-bottom:4px;">When these communications happened</div>'
    +'<div id="burst-ctr"></div>'
    +'<div style="font-size:10px;font-weight:600;margin:10px 0 6px;">Supporting communications ('+(r.comms||[]).length+')</div>';
      (r.comms||[]).forEach(function(c){h+='<div style="background:#f8f7f4;border-radius:5px;padding:7px 9px;margin-bottom:6px;"><div style="font-size:9px;font-weight:600;color:#534AB7;">'+c.ts+'  '+c.from+' to '+c.to+'</div><div style="font-size:10px;color:#3d3d3a;line-height:1.5;margin-top:3px;">\u201c'+trunc(c.text,180)+'\u201d</div><div style="font-size:8.5px;color:#888780;margin-top:2px;font-style:italic;">is_inferred: '+c.inf+'</div></div>';});
      h+='<div style="display:flex;gap:6px;margin-top:10px;"><button onclick="escalate()" style="flex:1;padding:7px;border-radius:5px;font-size:10px;font-weight:600;cursor:pointer;border:1px solid '+col+';background:'+col+'18;color:'+col+';">Add to queue</button><button onclick="clearPanel()" style="flex:1;padding:7px;border-radius:5px;font-size:10px;cursor:pointer;border:1px solid #d3d1c7;background:transparent;color:#888780;">Dismiss</button></div>'
    +'<div id="qbanner" style="display:none;margin-top:6px;padding:5px 8px;background:#E1F5EE;border-radius:4px;font-size:9.5px;color:#085041;"></div>'
    +'<div id="qsec"></div>';
      document.getElementById('pb').innerHTML=h;
      renderBurst(r);renderQueue();
    }

    function showEnt(e){
      lastClickedEnt=e;_backFn=null;
      var col=e.hcolor||'#888780';
      var deg=0;R.forEach(function(r){if(r.ents[0]===e.id||r.ents[1]===e.id)deg++;});
      var stats=ESTATS[e.id]||{sent:0,rcv:0,daily:{}};
      var peakD='',peakV=0;ALL_DATES.forEach(function(d){if((stats.daily[d]||0)>peakV){peakV=stats.daily[d]||0;peakD=d;}});
      var badge=e.conflict?'<div style="margin-top:6px;font-size:9.5px;background:#FCEBEB;border-radius:4px;padding:5px 8px;color:#791F1F;line-height:1.5;">\u26A0 Both Suspicious and Colleagues relationship found. Key investigative signal.</div>':'';
      var h='<div style="background:'+col+'18;border:1px solid '+col+'55;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    +'<div style="font-size:12px;font-weight:600;color:'+col+';">'+e.label+'</div>'
    +'<div style="font-size:10px;color:#73726c;margin-top:2px;">'+e.sub+'</div>'+badge+'</div>'
    +'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:10px;">'
    +'<div style="text-align:center;background:#f8f7f4;border-radius:5px;padding:6px 4px;"><div style="font-size:16px;font-weight:700;color:#3d3d3a;">'+deg+'</div><div style="font-size:8.5px;color:#888780;margin-top:1px;">connections</div></div>'
    +'<div style="text-align:center;background:#f8f7f4;border-radius:5px;padding:6px 4px;"><div style="font-size:16px;font-weight:700;color:#3d3d3a;">'+stats.sent+'</div><div style="font-size:8.5px;color:#888780;margin-top:1px;">msgs sent</div></div>'
    +'<div style="text-align:center;background:#f8f7f4;border-radius:5px;padding:6px 4px;"><div style="font-size:16px;font-weight:700;color:#3d3d3a;">'+stats.rcv+'</div><div style="font-size:8.5px;color:#888780;margin-top:1px;">msgs received</div></div></div>'
    +'<div style="font-size:10px;font-weight:600;color:#3d3d3a;margin-bottom:4px;">Daily activity</div>'
    +'<div id="spark-ctr"></div>'
    +(peakD?'<div style="font-size:9px;color:#888780;margin-top:4px;margin-bottom:10px;">Peak: '+peakD.slice(8)+'-'+peakD.slice(5,7)+' ('+peakV+' msgs)</div>':'<div style="margin-bottom:10px;"></div>')
    +'<div style="font-size:10px;font-weight:600;margin-bottom:6px;">Relationship types <span style="font-size:9px;font-weight:400;color:#888780;">(click to investigate)</span></div>';
      if(e.types&&e.types.length){e.types.forEach(function(t){var tc=REL_COLORS[t]||'#888780';h+='<span onclick="showRelType(\''+e.id+'\',\''+t+'\')" style="display:inline-block;margin:0 4px 4px 0;padding:3px 8px;border-radius:12px;font-size:9px;font-weight:600;background:'+tc+'20;color:'+tc+';border:1px solid '+tc+'55;cursor:pointer;" onmouseenter="this.style.background=\''+tc+'40\'" onmouseleave="this.style.background=\''+tc+'20\'">'+t+' \u2192</span>';});}
      h+='<div id="qsec"></div>';
      document.getElementById('pb').innerHTML=h;
      renderSparkline(e.id,col);renderQueue();
    }

    function showGhost(g){document.getElementById('pb').innerHTML='<div style="background:#8887801a;border:1px dashed #888780;border-radius:6px;padding:8px 10px;margin-bottom:10px;"><div style="font-size:11px;font-weight:600;color:#73726c;">Predicted missing relationship</div><div style="font-size:10px;color:#888780;margin-top:2px;">'+g.a+' and '+g.b+'</div></div><div style="font-size:11px;color:#3d3d3a;line-height:1.7;margin-bottom:8px;">These entities exchanged <strong>'+g.n+' communications</strong> but no relationship node exists. Predicted data gap.</div><div style="font-size:9.5px;color:#888780;background:#f8f7f4;padding:8px;border-radius:5px;line-height:1.6;">Dashed texture encodes epistemic uncertainty. MacEachren et al. (2012), doi:10.1145/2254556.2254592</div><div style="display:flex;gap:6px;margin-top:12px;"><button onclick="alert(\'Flagged\')" style="flex:1;padding:7px;border-radius:5px;font-size:10px;font-weight:600;cursor:pointer;border:1px solid #534AB7;background:#EEEDFE;color:#534AB7;">Review</button><button onclick="clearPanel()" style="flex:1;padding:7px;border-radius:5px;font-size:10px;cursor:pointer;border:1px solid #d3d1c7;background:transparent;color:#888780;">Dismiss</button></div>';}

    var tip=document.getElementById('tip');
    function showTip(html,x,y){tip.innerHTML=html;tip.style.display='block';tip.style.left=Math.min(x+14,window.innerWidth-tip.offsetWidth-10)+'px';tip.style.top=(y-10)+'px';}
    function hideTip(){tip.style.display='none';}

    var W=window.innerWidth-264,H=window.innerHeight-82;
    var svg=d3.select('#svg').attr('width',W).attr('height',H);
    var zoomG=svg.append('g');
    var zoomB=d3.zoom().scaleExtent([0.15,5]).on('zoom',function(ev){zoomG.attr('transform',ev.transform);});
    svg.call(zoomB);
    var ghostL=zoomG.append('g'),linkL=zoomG.append('g'),cardL=zoomG.append('g');
    var nodeById={};
    var simNodes=E.map(function(e){var n=Object.assign({},e,{x:W/2+(Math.random()-.5)*W*.5,y:H/2+(Math.random()-.5)*H*.5});nodeById[e.id]=n;return n;});
    var simLinks=R.map(function(r){return{data:r,source:r.ents[0],target:r.ents[1]};});
    var simGhosts=GH.map(function(g){return{data:g,source:g.a,target:g.b};});
    var sim=d3.forceSimulation(simNodes).force('link',d3.forceLink(simLinks).id(function(d){return d.id;}).distance(function(d){return 160+(1-d.data.ev/MEV)*100;}).strength(0.5)).force('charge',d3.forceManyBody().strength(-700).distanceMax(600)).force('center',d3.forceCenter(W/2,H/2)).force('collision',d3.forceCollide().radius(80).strength(0.9)).alphaDecay(0.025);
    var focusedId=null,focusedLink=null;
    function dimAll(){linkL.selectAll('.rl').attr('stroke-opacity',0.07);ghostL.selectAll('.gh').attr('stroke-opacity',0.05);cardL.selectAll('.ec').attr('opacity',0.1);}
    function resetFocus(){focusedId=null;focusedLink=null;linkL.selectAll('.rl').attr('stroke-opacity',function(d){return strokeO(d.data.ev);}).attr('stroke-width',function(d){return strokeW(d.data.ev);});ghostL.selectAll('.gh').attr('stroke-opacity',0.5).attr('stroke-width',2);cardL.selectAll('.ec').attr('opacity',1);}
    function focusEntity(eid){focusedId=eid;dimAll();linkL.selectAll('.rl').each(function(d){var src=typeof d.source==='object'?d.source.id:d.source,tgt=typeof d.target==='object'?d.target.id:d.target;if(src===eid||tgt===eid){d3.select(this).attr('stroke-opacity',strokeO(d.data.ev)).attr('stroke-width',strokeW(d.data.ev)+1);var nb=src===eid?tgt:src;cardL.selectAll('.ec').filter(function(n){return n.id===nb;}).attr('opacity',1);}});ghostL.selectAll('.gh').each(function(d){var sa=typeof d.source==='object'?(d.source.id||d.source):d.source,ta=typeof d.target==='object'?(d.target.id||d.target):d.target;if(sa===eid||ta===eid){d3.select(this).attr('stroke-opacity',0.8).attr('stroke-width',3);var nb=sa===eid?ta:sa;cardL.selectAll('.ec').filter(function(n){return n.id===nb;}).attr('opacity',1);}});cardL.selectAll('.ec').filter(function(d){return d.id===eid;}).attr('opacity',1);}
    function focusLink(r){focusedLink=r;dimAll();linkL.selectAll('.rl').filter(function(d){return d.data===r;}).attr('stroke-opacity',1).attr('stroke-width',strokeW(r.ev)+2);cardL.selectAll('.ec').filter(function(d){return d.id===r.ents[0]||d.id===r.ents[1];}).attr('opacity',1);}
    var ghostPaths=ghostL.selectAll('.gh').data(simGhosts).join('line').attr('class','gh').attr('stroke','#888780').attr('stroke-width',2).attr('stroke-dasharray','8,6').attr('stroke-opacity',0.5).style('cursor','pointer').on('mouseenter',function(ev,d){if(!focusedId&&!focusedLink)d3.select(this).attr('stroke-width',4).attr('stroke-opacity',.85);showTip('<strong>Predicted missing</strong><br>'+d.data.a+' and '+d.data.b+'<br>'+d.data.n+' comms',ev.clientX,ev.clientY);}).on('mousemove',function(ev){showTip(tip.innerHTML,ev.clientX,ev.clientY);}).on('mouseleave',function(ev,d){if(!focusedId&&!focusedLink)d3.select(this).attr('stroke-width',2).attr('stroke-opacity',.5);hideTip();}).on('click',function(ev,d){ev.stopPropagation();resetFocus();showGhost(d.data);});
    var relPaths=linkL.selectAll('.rl').data(simLinks).join('line').attr('class','rl').attr('stroke',function(d){return d.data.color;}).attr('stroke-width',function(d){return strokeW(d.data.ev);}).attr('stroke-opacity',function(d){return strokeO(d.data.ev);}).style('cursor','pointer').on('mouseenter',function(ev,d){if(!focusedId&&!focusedLink)d3.select(this).attr('stroke-width',strokeW(d.data.ev)+3).attr('stroke-opacity',1);showTip('<strong>'+d.data.sub+'</strong><br>'+d.data.ents.join(' and ')+'<br>Evidence: '+d.data.ev+' of '+MEV,ev.clientX,ev.clientY);}).on('mousemove',function(ev){showTip(tip.innerHTML,ev.clientX,ev.clientY);}).on('mouseleave',function(ev,d){if(!focusedId&&!focusedLink)d3.select(this).attr('stroke-width',strokeW(d.data.ev)).attr('stroke-opacity',strokeO(d.data.ev));hideTip();}).on('click',function(ev,d){ev.stopPropagation();focusLink(d.data);showRel(d.data);});
    var defs=svg.append('defs');var fl=defs.append('filter').attr('id','sh').attr('x','-20%').attr('y','-20%').attr('width','140%').attr('height','140%');fl.append('feDropShadow').attr('dx','0').attr('dy','1.5').attr('stdDeviation','2.5').attr('flood-color','#00000020');
    var cards=cardL.selectAll('.ec').data(simNodes).join('g').attr('class','ec').style('cursor','pointer').on('mouseenter',function(ev,d){d3.select(this).select('.cb').attr('stroke-width',d.conflict?3:1.5);showTip('<strong>'+d.label+'</strong><br>'+d.sub+(d.conflict?' <span style="color:#ffb3b0;">\u26A0</span>':''),ev.clientX,ev.clientY);}).on('mousemove',function(ev){showTip(tip.innerHTML,ev.clientX,ev.clientY);}).on('mouseleave',function(ev,d){d3.select(this).select('.cb').attr('stroke-width',d.conflict?2:.5);hideTip();}).on('click',function(ev,d){ev.stopPropagation();if(focusedId===d.id){resetFocus();clearPanel();}else{focusEntity(d.id);showEnt(d);}}).call(d3.drag().on('start',function(ev,d){if(!ev.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y;hideTip();}).on('drag',function(ev,d){d.fx=ev.x;d.fy=ev.y;}).on('end',function(ev,d){if(!ev.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}));
    cards.append('rect').attr('class','cb').attr('width',CW).attr('height',CH).attr('rx',8).attr('x',-CW/2).attr('y',-CH/2).attr('fill','#ffffff').attr('filter','url(#sh)').attr('stroke',function(d){return d.conflict?'#E24B4A':'#d3d1c7';}).attr('stroke-width',function(d){return d.conflict?2:.5;});
    cards.append('rect').attr('width',CW).attr('height',HH).attr('rx',8).attr('x',-CW/2).attr('y',-CH/2).attr('fill',function(d){return d.hcolor;});
    cards.append('rect').attr('width',CW).attr('height',HH/2).attr('x',-CW/2).attr('y',-CH/2+HH/2).attr('fill',function(d){return d.hcolor;});
    cards.append('text').attr('y',-CH/2+HH/2).attr('text-anchor','middle').attr('dominant-baseline','central').attr('font-size','10.5').attr('font-weight','600').attr('fill','white').attr('font-family','system-ui,sans-serif').text(function(d){return trunc(d.label,16);});
    cards.append('text').attr('y',-CH/2+HH+12).attr('text-anchor','middle').attr('dominant-baseline','central').attr('font-size','10').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text(function(d){return d.sub;});
    cards.append('text').attr('y',-CH/2+HH+27).attr('text-anchor','middle').attr('dominant-baseline','central').attr('font-size','9.5').attr('font-weight',function(d){return d.conflict?'600':'400';}).attr('fill',function(d){return d.conflict?'#E24B4A':'#888780';}).attr('font-family','system-ui,sans-serif').text(function(d){return d.conflict?'\u26A0 conflict':trunc(d.types.slice(0,2).join(', ')||'\u2014',22);});
    cards.filter(function(d){return d.conflict;}).append('circle').attr('cx',CW/2-8).attr('cy',-CH/2+8).attr('r',5).attr('fill','#E24B4A');
    d3.select('#bi').on('click',function(){svg.transition().duration(300).call(zoomB.scaleBy,1.4);});
    d3.select('#bo').on('click',function(){svg.transition().duration(300).call(zoomB.scaleBy,.7);});
    d3.select('#br').on('click',function(){svg.transition().duration(500).call(zoomB.transform,d3.zoomIdentity);});
    svg.on('click',function(){resetFocus();clearPanel();});
    sim.on('tick',function(){
      relPaths.attr('x1',function(d){return d.source.x;}).attr('y1',function(d){return d.source.y;}).attr('x2',function(d){return d.target.x;}).attr('y2',function(d){return d.target.y;});
      ghostPaths.attr('x1',function(d){var s=typeof d.source==='object'?d.source:nodeById[d.source];return s?s.x:0;}).attr('y1',function(d){var s=typeof d.source==='object'?d.source:nodeById[d.source];return s?s.y:0;}).attr('x2',function(d){var t=typeof d.target==='object'?d.target:nodeById[d.target];return t?t.x:0;}).attr('y2',function(d){var t=typeof d.target==='object'?d.target:nodeById[d.target];return t?t.y:0;});
      cards.attr('transform',function(d){return 'translate('+d.x+','+d.y+')';});
    });

    // ── Auto-surfaced key findings panel ──────────────────────────────────────
    // Fires on load: surfaces the highest-risk entity without requiring user interaction
    // This implements "overview first" (Shneiderman 1996) — the analyst sees the
    // most important finding immediately rather than having to discover it
    function generateInsightsPanel(){
      var pb=document.getElementById('pb');if(!pb)return;
      // Find highest-risk entity: most suspicious evidence
      var suspMap={};
      R.forEach(function(r){
        if(r.sub!=='Suspicious')return;
        r.ents.forEach(function(eid){
          if(!suspMap[eid])suspMap[eid]={ev:0,links:0,label:eid};
          suspMap[eid].ev+=r.ev;suspMap[eid].links++;
        });
      });
      var topEid=null,topEv=0;
      Object.keys(suspMap).forEach(function(eid){if(suspMap[eid].ev>topEv){topEv=suspMap[eid].ev;topEid=eid;}});
      var topEnt=E.find(function(e){return e.id===topEid;})||null;
      var conflictCount=E.filter(function(e){return e.conflict;}).length;
      var ghostCount=GH.length;
      var visCount=E.length;

      var h='<div style="margin-bottom:12px;">';
      // Top risk callout — red banner for the highest-risk entity
      if(topEnt){
        var col=topEnt.hcolor||'#888780';
        var sm=suspMap[topEid]||{ev:0,links:0};
        h+='<div style="background:#FCEBEB;border:1px solid #E24B4A55;border-radius:7px;padding:9px 11px;margin-bottom:10px;">'
          +'<div style="font-size:9.5px;font-weight:700;color:#E24B4A;letter-spacing:.4px;margin-bottom:3px;">HIGHEST RISK ENTITY</div>'
          +'<div style="font-size:12px;font-weight:700;color:#1a1a18;margin-bottom:2px;">'+topEnt.label+'</div>'
          +'<div style="font-size:10px;color:#73726c;margin-bottom:6px;">'+topEnt.sub+(topEnt.conflict?' · <span style="color:#E24B4A;font-weight:600;">conflict entity</span>':'')+'</div>'
          +'<div style="display:flex;gap:8px;">'
          +'<div style="text-align:center;background:white;border-radius:5px;padding:5px 8px;flex:1;"><div style="font-size:16px;font-weight:700;color:#E24B4A;">'+sm.ev+'</div><div style="font-size:8px;color:#888780;">evidence</div></div>'
          +'<div style="text-align:center;background:white;border-radius:5px;padding:5px 8px;flex:1;"><div style="font-size:16px;font-weight:700;color:#E24B4A;">'+sm.links+'</div><div style="font-size:8px;color:#888780;">susp. links</div></div>'
          +'<div style="text-align:center;background:white;border-radius:5px;padding:5px 8px;flex:1;"><div style="font-size:16px;font-weight:700;color:'+(topEnt.conflict?'#E24B4A':'#888780')+'">'+(topEnt.conflict?'Yes':'No')+'</div><div style="font-size:8px;color:#888780;">conflict</div></div>'
          +'</div>'
          +'<button onclick="var e=E.find(function(en){return en.id===\''+topEid+'\'});if(e){focusEntity(e.id);showEnt(e);}" '
          +'style="margin-top:8px;width:100%;padding:6px;border-radius:5px;font-size:10px;font-weight:600;cursor:pointer;border:1px solid #E24B4A;background:#E24B4A;color:white;">Investigate \u2192</button>'
          +'</div>';
      }
      // Three stat boxes
      h+='<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:10px;">'
        +'<div style="background:#FCEBEB;border-radius:6px;padding:8px 6px;text-align:center;">'
        +'<div style="font-size:18px;font-weight:700;color:#E24B4A;">'+conflictCount+'</div>'
        +'<div style="font-size:8px;color:#888780;margin-top:2px;">conflict entities</div></div>'
        +'<div style="background:#f0f3fa;border-radius:6px;padding:8px 6px;text-align:center;">'
        +'<div style="font-size:18px;font-weight:700;color:#534AB7;">'+ghostCount+'</div>'
        +'<div style="font-size:8px;color:#888780;margin-top:2px;">predicted missing</div></div>'
        +'<div style="background:#f8f7f4;border-radius:6px;padding:8px 6px;text-align:center;">'
        +'<div style="font-size:18px;font-weight:700;color:#3d3d3a;">'+visCount+'</div>'
        +'<div style="font-size:8px;color:#888780;margin-top:2px;">entities visible</div></div>'
        +'</div>';
      // Guidance
      h+='<div style="background:#f8f7f4;border-radius:6px;padding:9px 11px;font-size:9.5px;color:#73726c;line-height:1.65;">'
        +'<div style="font-weight:600;color:#3d3d3a;margin-bottom:4px;">How to investigate</div>'
        +'\u2192 Click any entity card to see its connections and activity<br>'
        +'\u2192 Click a relationship type pill to drill into specific partners<br>'
        +'\u2192 Click any string to read the evidence chain<br>'
        +'\u2192 Add findings to the investigation queue'
        +'</div>';
      h+='</div>';
      pb.innerHTML=h;
    }

    // Call after simulation has had time to initialise
    setTimeout(generateInsightsPanel, 800);

    """

    # PAGE 2: Communication Timeline — heatmap (entities x dates)
    # Colour: luminance encodes message count (Ware 2004, ordered data)
    # Cross-highlight on hover: row = green, column = blue (linked views)
    # Click a cell: all messages + hour-of-day activity histogram (D3)
    # Click a date header: day-level ranked summary (Shneiderman 1996 overview->detail)
    _p2_js = r"""

    var entities=HEAT.entities,dates=HEAT.dates,colors=HEAT.colors,conflicts=HEAT.conflicts,totals=HEAT.totals;
    var cellMap={};HEAT.cells.forEach(function(c){cellMap[c.entity+'|'+c.date]=c;});
    var maxCount=0;HEAT.cells.forEach(function(c){if(c.count>maxCount)maxCount=c.count;});
    var tip=document.getElementById('tip2');
    function showTip(html,x,y){tip.innerHTML=html;tip.style.display='block';tip.style.left=Math.min(x+14,window.innerWidth-tip.offsetWidth-10)+'px';tip.style.top=(y-10)+'px';}
    function hideTip(){tip.style.display='none';}

    // Format date as DD-MM (more natural reading order)
    function fmtDate(d){return d.slice(8)+'-'+d.slice(5,7);}

    function renderHourChart(msgs){
      var ctr=document.getElementById('hour-chart-ctr');if(!ctr)return;
      d3.select(ctr).selectAll('*').remove();
      var hours=new Array(24).fill(0);
      msgs.forEach(function(m){var h=parseInt((m.ts||'').slice(11,13),10);if(!isNaN(h)&&h>=0&&h<24)hours[h]++;});
      var maxH=Math.max(1,Math.max.apply(null,hours));
      var W=240,H=44,bw=Math.floor((W-2)/24)-1;
      var svg=d3.select(ctr).append('svg').attr('width',W).attr('height',H+24);
      svg.append('line').attr('x1',0).attr('y1',H-1).attr('x2',W).attr('y2',H-1).attr('stroke','#d3d1c7').attr('stroke-width',0.5);
      hours.forEach(function(v,i){
    var bh=v>0?Math.max(3,Math.round(v/maxH*(H-8))):1;
    var bar=svg.append('rect').attr('x',i*(bw+1)).attr('y',H-bh-1).attr('width',bw).attr('height',bh).attr('fill','#534AB7').attr('opacity',v>0?(0.35+v/maxH*0.6):0.08).attr('rx',1).style('cursor',v>0?'pointer':'default');
    if(v>0)bar.on('mouseenter',function(ev){d3.select(this).attr('opacity',1);var t=document.getElementById('tip2');if(t){t.innerHTML='<strong>'+String(i).padStart(2,'0')+':00</strong><br>'+v+' comm'+(v!==1?'s':'');t.style.display='block';t.style.left=Math.min(ev.clientX+14,window.innerWidth-140)+'px';t.style.top=(ev.clientY-10)+'px';}}).on('mouseleave',function(){d3.select(this).attr('opacity',0.35+v/maxH*0.6);var t=document.getElementById('tip2');if(t)t.style.display='none';});
      });
      [0,6,12,18].forEach(function(h){svg.append('text').attr('x',h*(bw+1)+bw/2).attr('y',H+14).attr('text-anchor','middle').attr('font-size','8').attr('fill','#888780').attr('font-family','system-ui').text(String(h).padStart(2,'0')+':00');});
      svg.append('text').attr('x',23*(bw+1)+bw/2).attr('y',H+14).attr('text-anchor','end').attr('font-size','8').attr('fill','#888780').attr('font-family','system-ui').text('23:00');
    }

    setTimeout(function(){
      var areaEl=document.getElementById('heatmap-area');
      var containerW=areaEl?areaEl.getBoundingClientRect().width-30:800;
      var ML=175,MT=55,MR=8,TOTALS_H=42,LEG_H=20;
      var availW=Math.max(300,containerW-ML-MR);
      var cellW=Math.max(20,Math.min(58,Math.floor(availW/dates.length)));
      // Measure actual available heatmap area height — avoids magic-number subtraction
      var _hmaH=areaEl?areaEl.clientHeight:600;
      var cellH=Math.max(18,Math.min(30,Math.floor((_hmaH-MT-TOTALS_H-LEG_H-20)/entities.length)));
      var svgW=ML+dates.length*cellW+MR,svgH=MT+entities.length*cellH+10+TOTALS_H+LEG_H+16;
      var svg=d3.select('#heatsvg').attr('width',svgW).attr('height',svgH);
      var colScale=d3.scaleSequential().domain([0,maxCount]).interpolator(d3.interpolate('#e8e6e0','#085041'));
      var maxDTotal=Math.max(1,Math.max.apply(null,dates.map(function(d){return DTOTALS[d]||0;})));

      // Date column headers — DD-MM format, clickable for day summary
      svg.selectAll('.dlbl').data(dates).join('text').attr('class','dlbl')
    .attr('x',function(d,i){return ML+i*cellW+cellW/2;}).attr('y',MT-10)
    .attr('text-anchor','middle').attr('font-size','9').attr('fill','#73726c').attr('font-family','system-ui,sans-serif')
    .style('cursor','pointer').attr('text-decoration','underline')
    .text(function(d){return fmtDate(d);})
    .on('mouseenter',function(){d3.select(this).attr('fill','#185FA5');})
    .on('mouseleave',function(){d3.select(this).attr('fill','#73726c');})
    .on('click',function(ev,d){
      var dayItems=entities.map(function(ent){var c=cellMap[ent+'|'+d];return c?{entity:ent,count:c.count}:null;})
        .filter(function(x){return x&&x.count>0;}).sort(function(a,b){return b.count-a.count;});
      var dtot=DTOTALS[d]||0;
      var h='<div style="font-size:11px;font-weight:600;color:#185FA5;margin-bottom:4px;">'+fmtDate(d)+'</div>'
        +'<div style="font-size:10px;color:#888780;margin-bottom:8px;">'+dtot+' total communications across '+dayItems.length+' entities</div>';
      var maxDayC=dayItems.length?dayItems[0].count:1;
      dayItems.forEach(function(item){
        var pct=Math.round(item.count/maxDayC*100);
        var col=colors[item.entity]||'#888780';
        h+='<div style="margin-bottom:5px;">'
          +'<div style="display:flex;justify-content:space-between;font-size:9.5px;margin-bottom:2px;">'
          +'<span style="color:'+col+';">'+(conflicts[item.entity]?'\u26A0 ':'')+item.entity+'</span>'
          +'<span style="color:#888780;">'+item.count+'</span></div>'
          +'<div style="height:6px;background:#f1efe8;border-radius:3px;overflow:hidden;">'
          +'<div style="height:100%;width:'+pct+'%;background:'+col+';opacity:0.75;border-radius:3px;"></div></div></div>';
      });
      document.getElementById('cpanel').innerHTML=h;
    });

      // Entity row labels
      var lg=svg.selectAll('.elbl').data(entities).join('g').attr('class','elbl')
    .attr('transform',function(d,i){return 'translate(0,'+(MT+i*cellH)+')';}).style('cursor','default')
    .on('mouseenter',function(ev,d){var i=entities.indexOf(d);svg.append('rect').attr('class','rhl').attr('x',ML).attr('y',MT+i*cellH).attr('width',dates.length*cellW).attr('height',cellH).attr('fill','#1D9E75').attr('opacity',0.09).attr('pointer-events','none');})
    .on('mouseleave',function(){svg.selectAll('.rhl').remove();});
      lg.filter(function(d){return conflicts[d];}).append('circle').attr('cx',8).attr('cy',cellH/2).attr('r',4).attr('fill','#E24B4A');
      lg.append('text').attr('x',18).attr('y',cellH/2).attr('dominant-baseline','central').attr('font-size','10').attr('font-family','system-ui,sans-serif').attr('font-weight',function(d){return conflicts[d]?'600':'400';}).attr('fill',function(d){return colors[d]||'#3d3d3a';}).text(function(d){return d.length>21?d.slice(0,20)+'\u2026':d;});
      lg.append('text').attr('x',ML-6).attr('y',cellH/2).attr('dominant-baseline','central').attr('text-anchor','end').attr('font-size','8.5').attr('fill','#aaa8a0').attr('font-family','system-ui,sans-serif').text(function(d){return totals[d]||0;});

      // Heatmap cells
      var cd=[];entities.forEach(function(ent,ei){dates.forEach(function(dt,di){cd.push({entity:ent,date:dt,ei:ei,di:di,key:ent+'|'+dt});});});
      svg.selectAll('.cell').data(cd).join('rect').attr('class','cell')
    .attr('x',function(d){return ML+d.di*cellW+1;}).attr('y',function(d){return MT+d.ei*cellH+1;})
    .attr('width',cellW-2).attr('height',cellH-2).attr('rx',2)
    .attr('fill',function(d){var c=cellMap[d.key];return c?colScale(c.count):'#f1efe8';})
    .style('cursor',function(d){return cellMap[d.key]?'pointer':'default';})
    .on('mouseenter',function(ev,d){
      var c=cellMap[d.key];if(!c)return;
      d3.select(this).attr('stroke','#085041').attr('stroke-width',1.5);
      svg.append('rect').attr('class','xhl').attr('x',ML).attr('y',MT+d.ei*cellH).attr('width',dates.length*cellW).attr('height',cellH).attr('fill','#1D9E75').attr('opacity',0.07).attr('pointer-events','none');
      svg.append('rect').attr('class','xhl').attr('x',ML+d.di*cellW).attr('y',MT).attr('width',cellW).attr('height',entities.length*cellH).attr('fill','#185FA5').attr('opacity',0.07).attr('pointer-events','none');
      var dtot=DTOTALS[d.date]||0;
      showTip('<strong>'+d.entity+'</strong><br>'+fmtDate(d.date)+'<br>'+c.count+' msg'+(c.count!==1?'s':'')+' sent<br><span style="color:#aaa">Day total: '+dtot+'</span>',ev.clientX,ev.clientY);
    })
    .on('mousemove',function(ev){showTip(tip.innerHTML,ev.clientX,ev.clientY);})
    .on('mouseleave',function(){hideTip();d3.select(this).attr('stroke',null);svg.selectAll('.xhl').remove();})
    .on('click',function(ev,d){
      var c=cellMap[d.key];if(!c)return;
      // Show all messages (no cap) with hour chart — full-height scrollable cpanel
      var h='<div style="font-size:11px;font-weight:600;color:#3d3d3a;margin-bottom:3px;">'+d.entity+' on '+fmtDate(d.date)+'</div>'
        +'<div style="font-size:10px;color:#888780;margin-bottom:6px;">'+c.count+' communication'+(c.count!==1?'s':'')+'</div>'
        +'<div style="font-size:10px;font-weight:600;color:#3d3d3a;margin-bottom:4px;">Hour of day activity</div>'
        +'<div id="hour-chart-ctr" style="margin-bottom:10px;"></div>'
        +'<div style="font-size:10px;font-weight:600;color:#3d3d3a;margin-bottom:6px;">All communications</div>';
      c.msgs.forEach(function(m){
        h+='<div style="background:#f8f7f4;border-radius:5px;padding:6px 8px;margin-bottom:5px;">'
          +'<div style="font-size:9px;font-weight:600;color:#534AB7;">'+m.ts+'  to '+m.to+'</div>'
          +'<div style="font-size:10px;color:#3d3d3a;line-height:1.5;margin-top:2px;">\u201c'
          +(m.content.length>220?m.content.slice(0,219)+'\u2026':m.content)+'\u201d</div></div>';
      });
      document.getElementById('cpanel').innerHTML=h;
      renderHourChart(c.msgs);
    });

      svg.selectAll('.clbl').data(cd.filter(function(d){var c=cellMap[d.key];return c&&c.count>=3&&cellH>=18;}))
    .join('text').attr('class','clbl').attr('x',function(d){return ML+d.di*cellW+cellW/2;}).attr('y',function(d){return MT+d.ei*cellH+cellH/2;}).attr('text-anchor','middle').attr('dominant-baseline','central').attr('font-size','7.5').attr('pointer-events','none').attr('font-family','system-ui').attr('fill',function(d){var c=cellMap[d.key];return c.count/maxCount>0.55?'rgba(255,255,255,0.85)':'#3d3d3a';}).text(function(d){var c=cellMap[d.key];return c.count;});

      entities.forEach(function(ent,i){if(!i)return;svg.append('line').attr('x1',ML).attr('x2',ML+dates.length*cellW).attr('y1',MT+i*cellH).attr('y2',MT+i*cellH).attr('stroke','#e8e6e0').attr('stroke-width',.5);});

      var dtY=MT+entities.length*cellH+14;
      svg.append('text').attr('x',ML-6).attr('y',dtY+TOTALS_H/2).attr('dominant-baseline','central').attr('text-anchor','end').attr('font-size','9').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text('Daily total');
      dates.forEach(function(d,i){var v=DTOTALS[d]||0;var bh=Math.max(v>0?2:0,Math.round(v/maxDTotal*(TOTALS_H-8)));svg.append('rect').attr('x',ML+i*cellW+2).attr('y',dtY+(TOTALS_H-bh-4)).attr('width',cellW-4).attr('height',bh).attr('rx',2).attr('fill','#185FA5').attr('opacity',0.6);if(v>0)svg.append('text').attr('x',ML+i*cellW+cellW/2).attr('y',dtY+TOTALS_H+2).attr('text-anchor','middle').attr('font-size','8').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text(v);});
      var legY=dtY+TOTALS_H+12,legW=Math.min(180,dates.length*cellW);
      var grad=svg.append('defs').append('linearGradient').attr('id','lg');grad.append('stop').attr('offset','0%').attr('stop-color','#e8e6e0');grad.append('stop').attr('offset','100%').attr('stop-color','#085041');
      svg.append('rect').attr('x',ML).attr('y',legY).attr('width',legW).attr('height',8).attr('rx',3).attr('fill','url(#lg)');
      svg.append('text').attr('x',ML).attr('y',legY-3).attr('font-size','8').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text('0');
      svg.append('text').attr('x',ML+legW).attr('y',legY-3).attr('text-anchor','end').attr('font-size','8').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text(maxCount+' comms');
    },60);

    """

    # PAGE 3: Suspicion Analysis — two linked views
    # Ranked list: entities sorted by suspicious evidence, with 14-day sparklines
    # Risk matrix: scatter (X=connections, Y=evidence) with beeswarm + zoom
    # Spoke network: D3 star layout with interactive hoverable partner labels
    # Entity type colour matches EvidenceBoard (Ware 2004 — consistent encoding)
    _p3_js = r"""

    var tip3=document.getElementById('tip3');
    function showTip3(h,x,y){tip3.innerHTML=h;tip3.style.display='block';tip3.style.left=Math.min(x+14,window.innerWidth-tip3.offsetWidth-10)+'px';tip3.style.top=(y-10)+'px';}
    function hideTip3(){tip3.style.display='none';}

    function renderSpoke(d){
      var ctr=document.getElementById('spoke-ctr');if(!ctr)return;
      d3.select(ctr).selectAll('*').remove();
      var rels=d.rels||[],n=Math.min(rels.length,8);
      if(!n){d3.select(ctr).append('p').style('font-size','10px').style('color','#888780').text('No suspicious connections.');return;}
      var W=280,H=240,cx=W/2,cy=H/2-10,r=70;
      var svg=d3.select(ctr).append('svg').attr('width',W).attr('height',H);
      rels.slice(0,n).forEach(function(rel,i){var a=(2*Math.PI*i/n)-Math.PI/2,px=cx+r*Math.cos(a),py=cy+r*Math.sin(a);svg.append('line').attr('x1',cx).attr('y1',cy).attr('x2',px).attr('y2',py).attr('stroke','#E24B4A').attr('stroke-width',Math.max(1.5,Math.min(7,rel.ev*0.5+1))).attr('stroke-opacity',0.55);});
      rels.slice(0,n).forEach(function(rel,i){
    var a=(2*Math.PI*i/n)-Math.PI/2,px=cx+r*Math.cos(a),py=cy+r*Math.sin(a);
    var g=svg.append('g').style('cursor','pointer');
    g.append('circle').attr('cx',px).attr('cy',py).attr('r',10).attr('fill','#fff8f8').attr('stroke','#E24B4A').attr('stroke-width',1.5);
    g.append('text').attr('x',px).attr('y',py).attr('text-anchor','middle').attr('dominant-baseline','central').attr('font-size','7').attr('font-weight','600').attr('fill','#E24B4A').attr('font-family','system-ui').text(rel.ev);
    var lR=r+32,lx=cx+lR*Math.cos(a),ly=cy+lR*Math.sin(a),pl=rel.partner.length>14?rel.partner.slice(0,13)+'\u2026':rel.partner,tw=pl.length*5.5+8;
    g.append('rect').attr('x',lx-tw/2).attr('y',ly-7).attr('width',tw).attr('height',14).attr('rx',3).attr('fill','white').attr('stroke','#E24B4A').attr('stroke-opacity',0.4).attr('stroke-width',1);
    g.append('text').attr('x',lx).attr('y',ly).attr('text-anchor','middle').attr('dominant-baseline','central').attr('font-size','8.5').attr('fill','#3d3d3a').attr('font-family','system-ui').text(pl);
    g.on('mouseenter',function(ev){d3.select(this).select('circle').attr('fill','#FCEBEB');d3.select(this).select('rect').attr('stroke-opacity',0.9);var ct='<strong>'+rel.partner+'</strong><br>Evidence: '+rel.ev;if(rel.comms&&rel.comms.length){var cm=rel.comms[0];ct+='<br><span style="color:#aaa;font-size:10px;">'+cm.ts+'  '+cm.from+' to '+cm.to+'</span><br>'+(cm.text||'').slice(0,220)+(cm.text&&cm.text.length>220?'\u2026':'');}showTip3(ct,ev.clientX,ev.clientY);}).on('mouseleave',function(){d3.select(this).select('circle').attr('fill','#fff8f8');d3.select(this).select('rect').attr('stroke-opacity',0.4);hideTip3();});
      });
      svg.append('circle').attr('cx',cx).attr('cy',cy).attr('r',32).attr('fill',d.color).attr('stroke','white').attr('stroke-width',2);
      if(d.conflict)svg.append('circle').attr('cx',cx+25).attr('cy',cy-25).attr('r',7).attr('fill','#E24B4A').attr('stroke','white').attr('stroke-width',1.5);
      var cl=d.label.length>13?d.label.slice(0,12)+'\u2026':d.label;
      svg.append('text').attr('x',cx).attr('y',cy-6).attr('text-anchor','middle').attr('font-size','9').attr('font-weight','600').attr('font-family','system-ui').attr('fill','white').text(cl);
      svg.append('text').attr('x',cx).attr('y',cy+7).attr('text-anchor','middle').attr('font-size','8').attr('font-family','system-ui').attr('fill','rgba(255,255,255,0.85)').text(d.sub);
      svg.append('text').attr('x',W/2).attr('y',H-4).attr('text-anchor','middle').attr('font-size','7.5').attr('fill','#888780').attr('font-family','system-ui').text('Spoke width = evidence \u00B7 Hover labels for details');
    }

    var selectedEntityId=null,_barG=null,barSel=null,scatterSel=null,scatterLblSel=null;
    function updateSelection(id){
      selectedEntityId=id;
      if(barSel)barSel.select('.bar').attr('stroke',function(d){return d.id===id?'#1a1a18':null;}).attr('stroke-width',function(d){return d.id===id?2:null;});
      if(scatterSel)scatterSel.attr('r',function(d){return d.id===id?14:9;}).attr('stroke',function(d){return d.id===id?'#1a1a18':(d.conflict?'#E24B4A':'white');}).attr('stroke-width',function(d){return d.id===id?2.5:(d.conflict?2.5:1.5);});
    }

    function showSuspDetail(d){
      updateSelection(d.id);
      var col=d.color||'#888780';
      var h='<div style="background:'+col+'18;border:1px solid '+col+'55;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    +'<div style="font-size:12px;font-weight:600;color:'+col+';">'+d.label+'</div>'
    +'<div style="font-size:10px;color:#73726c;margin-top:2px;">'+d.sub+(d.conflict?' <span style="color:#E24B4A;font-weight:600;">\u26A0 conflict entity</span>':'')+'</div></div>'
    +'<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px;">'
    +'<div style="text-align:center;background:#f8f7f4;border-radius:5px;padding:6px;"><div style="font-size:18px;font-weight:700;color:#E24B4A;">'+d.ev+'</div><div style="font-size:8.5px;color:#888780;">total evidence</div></div>'
    +'<div style="text-align:center;background:#f8f7f4;border-radius:5px;padding:6px;"><div style="font-size:18px;font-weight:700;color:#E24B4A;">'+d.count+'</div><div style="font-size:8.5px;color:#888780;">suspicious links</div></div></div>'
    +'<div style="font-size:10px;font-weight:600;color:#3d3d3a;margin-bottom:6px;">Suspicious connection network</div>'
    +'<div id="spoke-ctr"></div>'
    +'<div style="font-size:10px;font-weight:600;margin:10px 0 6px;">Relationship details</div>';
      d.rels.forEach(function(r){
    h+='<div style="background:#f8f7f4;border-radius:5px;padding:7px 9px;margin-bottom:8px;">'
      +'<div style="display:flex;justify-content:space-between;margin-bottom:5px;"><span style="font-size:10px;font-weight:600;color:#E24B4A;">with '+r.partner+'</span><span style="font-size:9px;color:#888780;">'+r.ev+' evidence</span></div>';
    (r.comms||[]).forEach(function(c){h+='<div style="border-left:2px solid #E24B4A33;padding-left:7px;margin-bottom:5px;"><div style="font-size:9px;font-weight:600;color:#534AB7;margin-bottom:2px;">'+c.ts+'  '+c.from+' to '+c.to+'</div><div style="font-size:9.5px;color:#3d3d3a;line-height:1.6;">'+(c.text||'').slice(0,300)+(c.text&&c.text.length>300?'\u2026':'')+'</div></div>';});
    h+='</div>';
      });
      document.getElementById('sp').innerHTML=h;
      renderSpoke(d);
    }

    // Daily suspicious activity for sparkline
    function getSuspDaily(d){
      var dates=typeof ALL_DATES3!=='undefined'?ALL_DATES3:[];
      var daily={};dates.forEach(function(dt){daily[dt]=0;});
      d.rels.forEach(function(r){(r.comms||[]).forEach(function(c){var dt=(c.ts||'').slice(0,10);if(daily.hasOwnProperty(dt))daily[dt]++;});});
      return dates.map(function(dt){return daily[dt];});
    }

    // Use requestAnimationFrame to ensure DOM is fully laid out before measuring
    requestAnimationFrame(function(){setTimeout(function(){
      var top=SUSP.slice(0,18);
      if(!top.length)return;

      var maxEv=Math.max.apply(null,top.map(function(d){return d.ev;}));
      var maxCnt=Math.max.apply(null,top.map(function(d){return d.count;}));

      // Width: measure the actual SVG parent element — most reliable approach
      var ssvgEl=document.getElementById('ssvg');
      var parentEl=ssvgEl?ssvgEl.parentElement:null;
      var measuredW=parentEl?parentEl.getBoundingClientRect().width:0;
      var cW=measuredW>200?Math.floor(measuredW)-4:(window.innerWidth>400?window.innerWidth-290:800);

      var ML=188,LABEL_GAP=58,SP_GAP=10,SP_W=62,MR=16;
      var BAR_W=cW-ML-LABEL_GAP-SP_GAP-SP_W-MR;
      if(BAR_W<180)BAR_W=180;
      var svgW=ML+BAR_W+LABEL_GAP+SP_GAP+SP_W+MR;
      var MT=16,BAR_H=30,GAP=7;
      var scX=d3.scaleLinear().domain([0,maxEv]).range([0,BAR_W]);
      var barSvgH=MT+top.length*(BAR_H+GAP)+55;
      var svg3=d3.select('#ssvg').attr('width',svgW).attr('height',barSvgH);
      var sl=document.getElementById('ev-filter');if(sl)sl.max=maxEv;

      _barG=svg3.append('g').attr('id','bar-g');

      // Sparkline column header
      var spX0=ML+BAR_W+LABEL_GAP+SP_GAP;
      var dates3=typeof ALL_DATES3!=='undefined'?ALL_DATES3:[];
      _barG.append('text').attr('x',spX0+SP_W/2).attr('y',MT-4).attr('text-anchor','middle').attr('font-size','7.5').attr('fill','#888780').attr('font-family','system-ui').text('Susp. by day');

      barSel=_barG.selectAll('.bg').data(top).join('g').attr('class','bg')
    .attr('transform',function(d,i){return 'translate(0,'+(MT+i*(BAR_H+GAP))+')';})
    .style('cursor','pointer')
    .on('mouseenter',function(ev,d){d3.select(this).select('.bar').attr('opacity',.8);showTip3('<strong>'+d.label+'</strong><br>Evidence: '+d.ev+'<br>Connections: '+d.count,ev.clientX,ev.clientY);})
    .on('mousemove',function(ev){showTip3(tip3.innerHTML,ev.clientX,ev.clientY);})
    .on('mouseleave',function(){d3.select(this).select('.bar').attr('opacity',1);hideTip3();})
    .on('click',function(ev,d){showSuspDetail(d);});

      barSel.append('text').attr('x',ML-8).attr('y',BAR_H/2).attr('text-anchor','end').attr('dominant-baseline','central').attr('font-size','10.5').attr('font-family','system-ui,sans-serif').attr('font-weight',function(d){return d.conflict?'600':'400';}).attr('fill',function(d){return d.color||'#3d3d3a';}).text(function(d){return d.label.length>24?d.label.slice(0,23)+'\u2026':d.label;});
      barSel.append('text').attr('x',ML-8).attr('y',BAR_H/2+12).attr('text-anchor','end').attr('dominant-baseline','central').attr('font-size','8.5').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text(function(d){return d.sub+(d.conflict?' \u26A0':'');});
      barSel.append('rect').attr('class','bar').attr('x',ML).attr('y',4).attr('height',BAR_H-8).attr('rx',4).attr('width',function(d){return Math.max(4,scX(d.ev));}).attr('fill',function(d){return d.conflict?'#E24B4A':'#F5A0A0';});
      barSel.append('text').attr('x',function(d){return Math.min(ML+scX(d.ev)+6,ML+BAR_W+LABEL_GAP-4);}).attr('y',BAR_H/2).attr('dominant-baseline','central').attr('font-size','9').attr('fill','#73726c').attr('font-family','system-ui,sans-serif').text(function(d){return d.ev+'ev, '+d.count+'x';});

      // Suspicious activity sparkline
      var spN=dates3.length,spBw=spN>0?Math.max(1,Math.floor(SP_W/spN)-1):3,spBarMax=BAR_H-10;
      barSel.each(function(d){
    var counts=getSuspDaily(d),maxC=Math.max(1,Math.max.apply(null,counts.concat([1])));
    var g=d3.select(this);
    counts.forEach(function(v,i){g.append('rect').attr('x',spX0+i*(spBw+1)).attr('y',4+spBarMax-(v>0?Math.max(2,Math.round(v/maxC*spBarMax)):1)).attr('width',spBw).attr('height',v>0?Math.max(2,Math.round(v/maxC*spBarMax)):1).attr('fill',v>0?'#E24B4A':'#f1efe8').attr('opacity',v>0?(0.30+v/maxC*0.65):1).attr('rx',0.5);});
    var peakIdx=counts.indexOf(Math.max.apply(null,counts)),peakDate=dates3[peakIdx]||'';
    g.append('rect').attr('x',spX0).attr('y',3).attr('width',SP_W).attr('height',spBarMax+2).attr('fill','transparent').style('cursor','pointer')
      .on('mouseenter',function(ev){showTip3('<strong>'+d.label+'</strong><br>Peak suspicious activity:<br>'+(peakDate?peakDate.slice(8)+'-'+peakDate.slice(5,7):'—'),ev.clientX,ev.clientY);}).on('mouseleave',hideTip3);
      });

      var axY=MT+top.length*(BAR_H+GAP)+8;
      _barG.append('line').attr('x1',ML).attr('x2',ML+BAR_W).attr('y1',axY).attr('y2',axY).attr('stroke','#d3d1c7').attr('stroke-width',.5);
      _barG.append('text').attr('x',ML).attr('y',axY+12).attr('font-size','9').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text('0');
      _barG.append('text').attr('x',ML+BAR_W).attr('y',axY+12).attr('text-anchor','end').attr('font-size','9').attr('fill','#888780').attr('font-family','system-ui,sans-serif').text('Total suspicious evidence');
      var lY=axY+26;
      _barG.append('rect').attr('x',ML).attr('y',lY).attr('width',14).attr('height',10).attr('rx',2).attr('fill','#E24B4A');
      _barG.append('text').attr('x',ML+18).attr('y',lY+5).attr('dominant-baseline','central').attr('font-size','9').attr('fill','#73726c').attr('font-family','system-ui,sans-serif').text('Conflict entity (Suspicious AND Colleagues)');
      _barG.append('rect').attr('x',ML+240).attr('y',lY).attr('width',14).attr('height',10).attr('rx',2).attr('fill','#F5A0A0');
      _barG.append('text').attr('x',ML+258).attr('y',lY+5).attr('dominant-baseline','central').attr('font-size','9').attr('fill','#73726c').attr('font-family','system-ui,sans-serif').text('Suspicious only');
      _barG.append('rect').attr('x',spX0).attr('y',lY).attr('width',10).attr('height',10).attr('rx',1).attr('fill','#E24B4A').attr('opacity',0.6);
      _barG.append('text').attr('x',spX0+14).attr('y',lY+5).attr('dominant-baseline','central').attr('font-size','9').attr('fill','#73726c').attr('font-family','system-ui,sans-serif').text('Daily suspicious evidence');

      // ── Risk matrix scatter ──────────────────────────────────────────────────────
      var SM={l:58,r:20,t:30,b:55};
      // Fill the actual available chart height rather than a fixed fraction of viewport
      var _ctrlH=document.getElementById('ctrl-bar')?document.getElementById('ctrl-bar').offsetHeight:44;
      var _areaH=document.getElementById('chart-area')?document.getElementById('chart-area').clientHeight:500;
      var SH=Math.max(220,_areaH-_ctrlH-SM.t-SM.b-65);
      var SW=svgW-SM.l-SM.r;
      var scatterSvgH=SM.t+SH+SM.b+65;
      var scatterG=svg3.append('g').attr('id','scatter-g').style('display','none');
      var scX2=d3.scaleLinear().domain([0,maxCnt+0.8]).range([SM.l,SM.l+SW]);
      var scY2=d3.scaleLinear().domain([0,maxEv+0.8]).range([SM.t+SH,SM.t]);

      var cGroups={};top.forEach(function(d){if(!cGroups[d.count])cGroups[d.count]=[];cGroups[d.count].push(d);});
      var maxGN=Math.max.apply(null,Object.keys(cGroups).map(function(k){return cGroups[k].length;}));
      var JX=Math.min(14,Math.abs(scX2(1)-scX2(0))*0.36/Math.max(1,(maxGN-1)/2));
      var cvG={};top.forEach(function(d){var k=d.count+'|'+d.ev;if(!cvG[k])cvG[k]=[];cvG[k].push(d);});
      top.forEach(function(d){var cg=cGroups[d.count],ci=cg.indexOf(d),cn=cg.length;d._jx=(ci-(cn-1)/2)*JX;var cvg=cvG[d.count+'|'+d.ev],cvi=cvg.indexOf(d),cvn=cvg.length;d._jy=(cvi-(cvn-1)/2)*11;});

      var LH=12,LW=90;
      var lpos=top.map(function(d){return{id:d.id,px:scX2(d.count)+d._jx,py:scY2(d.ev)+d._jy,ly:scY2(d.ev)+d._jy,txt:d.label.length>15?d.label.slice(0,14)+'\u2026':d.label};});
      lpos.sort(function(a,b){return a.py-b.py;});
      for(var li=1;li<lpos.length;li++)for(var lj=0;lj<li;lj++)if(Math.abs(lpos[li].px-lpos[lj].px)<LW&&Math.abs(lpos[li].ly-lpos[lj].ly)<LH)lpos[li].ly=lpos[lj].ly+LH+1;
      var lById={};lpos.forEach(function(l){lById[l.id]=l;});

      var clipId='scp'+Date.now();
      var defs=svg3.append('defs').append('clipPath').attr('id',clipId);
      defs.append('rect').attr('x',SM.l).attr('y',SM.t).attr('width',SW).attr('height',SH);
      var axG=scatterG.append('g').attr('id','sc-ax');
      var dataG=scatterG.append('g').attr('id','sc-data').attr('clip-path','url(#'+clipId+')');

      var xAxisFn=d3.axisBottom(scX2).ticks(Math.min(maxCnt+1,9)).tickFormat(d3.format('d'));
      var yAxisFn=d3.axisLeft(scY2).ticks(6);
      var xAxisG=axG.append('g').attr('transform','translate(0,'+(SM.t+SH)+')').call(xAxisFn);
      var yAxisG=axG.append('g').attr('transform','translate('+SM.l+',0)').call(yAxisFn);
      function styleAxes(){[xAxisG,yAxisG].forEach(function(g){g.selectAll('.tick text').attr('font-size','8').attr('fill','#888780').attr('font-family','system-ui');g.selectAll('.tick line').attr('stroke','#e8e6e0');g.select('.domain').attr('stroke','#d3d1c7');});}
      styleAxes();

      scatterG.append('text').attr('x',SM.l+SW/2).attr('y',SM.t+SH+44).attr('text-anchor','middle').attr('font-size','10').attr('fill','#73726c').attr('font-family','system-ui').text('Number of suspicious connections');
      scatterG.append('text').attr('transform','rotate(-90)').attr('x',-(SM.t+SH/2)).attr('y',SM.l-46).attr('text-anchor','middle').attr('font-size','10').attr('fill','#73726c').attr('font-family','system-ui').text('Total evidence');

      var qMX0=scX2((maxCnt+0.8)/2),qMY0=scY2((maxEv+0.8)/2);
      var qLV=axG.append('line').attr('x1',qMX0).attr('y1',SM.t).attr('x2',qMX0).attr('y2',SM.t+SH).attr('stroke','#c8c6be').attr('stroke-width',1).attr('stroke-dasharray','5,4');
      var qLH=axG.append('line').attr('x1',SM.l).attr('y1',qMY0).attr('x2',SM.l+SW).attr('y2',qMY0).attr('stroke','#c8c6be').attr('stroke-width',1).attr('stroke-dasharray','5,4');
      [{x:SM.l+5,y:SM.t+14,t:'High evidence',a:'start',col:'#888780',w:400},{x:SM.l+SW-4,y:SM.t+14,t:'HIGHEST PRIORITY',a:'end',col:'#E24B4A',w:600},{x:SM.l+5,y:SM.t+SH-6,t:'Low risk',a:'start',col:'#888780',w:400},{x:SM.l+SW-4,y:SM.t+SH-6,t:'Many connections',a:'end',col:'#888780',w:400}].forEach(function(q){scatterG.append('text').attr('x',q.x).attr('y',q.y).attr('text-anchor',q.a).attr('font-size','8.5').attr('fill',q.col).attr('opacity',q.w===600?0.65:0.45).attr('font-family','system-ui').attr('font-weight',q.w===600?'600':'400').text(q.t);});
      var qBg=dataG.append('rect').attr('x',qMX0).attr('y',SM.t).attr('width',SM.l+SW-qMX0).attr('height',qMY0-SM.t).attr('fill','#E24B4A').attr('opacity',0.04).attr('pointer-events','none');

      scatterLblSel=dataG.selectAll('.ptl').data(top).join('text').attr('class','ptl').attr('x',function(d){return(lById[d.id]?lById[d.id].px:scX2(d.count)+d._jx)+14;}).attr('y',function(d){return lById[d.id]?lById[d.id].ly:scY2(d.ev)+d._jy;}).attr('font-size','8.5').attr('fill','#3d3d3a').attr('font-family','system-ui').attr('pointer-events','none').text(function(d){return lById[d.id]?lById[d.id].txt:(d.label.length>15?d.label.slice(0,14)+'\u2026':d.label);});

      var EC={Person:'#1D9E75',Organization:'#534AB7',Vessel:'#185FA5',Group:'#BA7517',Location:'#888780'};
      scatterSel=dataG.selectAll('.pt').data(top).join('circle').attr('class','pt').attr('cx',function(d){return scX2(d.count)+d._jx;}).attr('cy',function(d){return scY2(d.ev)+d._jy;}).attr('r',9).attr('fill',function(d){return EC[d.sub]||'#888780';}).attr('stroke',function(d){return d.conflict?'#E24B4A':'white';}).attr('stroke-width',function(d){return d.conflict?2.5:1.5;}).attr('opacity',0.88).style('cursor','pointer')
    .on('mouseenter',function(ev,d){d3.select(this).attr('r',13).attr('opacity',1);showTip3('<strong>'+d.label+'</strong><br>'+d.sub+'<br>Ev: '+d.ev+' Conn: '+d.count+(d.conflict?' \u26A0':''),ev.clientX,ev.clientY);}).on('mousemove',function(ev){showTip3(tip3.innerHTML,ev.clientX,ev.clientY);}).on('mouseleave',function(ev,d){d3.select(this).attr('r',selectedEntityId===d.id?14:9).attr('opacity',0.88);hideTip3();}).on('click',function(ev,d){showSuspDetail(d);});

      var legTypes=Object.keys(EC),legX=SM.l,legY=SM.t+SH+57;
      legTypes.forEach(function(t,i){scatterG.append('circle').attr('cx',legX+i*90+5).attr('cy',legY).attr('r',5).attr('fill',EC[t]);scatterG.append('text').attr('x',legX+i*90+14).attr('y',legY).attr('dominant-baseline','central').attr('font-size','8.5').attr('fill','#73726c').attr('font-family','system-ui').text(t);});
      scatterG.append('text').attr('x',SM.l+SW).attr('y',legY).attr('text-anchor','end').attr('font-size','8').attr('fill','#888780').attr('font-family','system-ui').text('Red ring = conflict \u00B7 Scroll to zoom \u00B7 Drag to pan');

      var currentView='bar';
      var scatterZoom=d3.zoom().scaleExtent([0.3,10]).filter(function(ev){return currentView==='scatter';})
    .on('zoom',function(ev){
      var t=ev.transform,newX=t.rescaleX(scX2),newY=t.rescaleY(scY2);
      xAxisG.call(xAxisFn.scale(newX));yAxisG.call(yAxisFn.scale(newY));styleAxes();
      var qmx=newX((maxCnt+0.8)/2),qmy=newY((maxEv+0.8)/2);
      qLV.attr('x1',qmx).attr('x2',qmx);qLH.attr('y1',qmy).attr('y2',qmy);
      qBg.attr('x',qmx).attr('y',Math.max(SM.t,qmy)).attr('width',Math.max(0,SM.l+SW-qmx)).attr('height',Math.max(0,qmy-SM.t));
      scatterSel.attr('cx',function(d){return newX(d.count)+d._jx*t.k;}).attr('cy',function(d){return newY(d.ev)+d._jy*t.k;});
      scatterLblSel.attr('x',function(d){return newX(d.count)+d._jx*t.k+14;}).attr('y',function(d){var by=newY(d.ev)+d._jy*t.k;return lById[d.id]?by+(lById[d.id].ly-lById[d.id].py):by;});
    });
      svg3.call(scatterZoom);

      function setView(v){
    currentView=v;var isBar=v==='bar';
    _barG.style('display',isBar?null:'none');scatterG.style('display',isBar?'none':null);
    svg3.attr('height',isBar?barSvgH:scatterSvgH);
    if(!isBar)svg3.call(scatterZoom.transform,d3.zoomIdentity);
    var bl=document.getElementById('btn-list'),br=document.getElementById('btn-risk');
    if(bl){bl.style.background=isBar?'#534AB7':'#fff';bl.style.color=isBar?'white':'#3d3d3a';bl.style.border=isBar?'1px solid #534AB7':'1px solid #d3d1c7';}
    if(br){br.style.background=isBar?'#fff':'#534AB7';br.style.color=isBar?'#3d3d3a':'white';br.style.border=isBar?'1px solid #d3d1c7':'1px solid #534AB7';}
    var rz=document.getElementById('btn-reset-zoom');if(rz)rz.style.display=isBar?'none':'inline-block';
      }
      var bl=document.getElementById('btn-list'),br=document.getElementById('btn-risk');
      if(bl)bl.addEventListener('click',function(){setView('bar');});
      if(br)br.addEventListener('click',function(){setView('scatter');});
      var rz=document.getElementById('btn-reset-zoom');if(rz)rz.addEventListener('click',function(){svg3.transition().duration(400).call(scatterZoom.transform,d3.zoomIdentity);});

      var evSl=document.getElementById('ev-filter');
      if(evSl){evSl.max=maxEv;evSl.addEventListener('input',function(){var m=parseInt(this.value,10);document.getElementById('ev-val').textContent=m;_barG.selectAll('.bg').each(function(d){var v=d.ev>=m;d3.select(this).style('opacity',v?1:0.1).style('pointer-events',v?'all':'none');});if(scatterSel)scatterSel.style('opacity',function(d){return d.ev>=m?0.88:0.08;});if(scatterLblSel)scatterLblSel.style('opacity',function(d){return d.ev>=m?1:0.08;});});}
      var srch=document.getElementById('entity-search');
      if(srch){srch.addEventListener('input',function(){var q=this.value.toLowerCase().trim();_barG.selectAll('.bg').each(function(d){var v=!q||d.label.toLowerCase().indexOf(q)!==-1;d3.select(this).style('opacity',v?1:0.1).style('pointer-events',v?'all':'none');});if(scatterSel)scatterSel.style('opacity',function(d){return(!q||d.label.toLowerCase().indexOf(q)!==-1)?0.88:0.08;});if(scatterLblSel)scatterLblSel.style('opacity',function(d){return(!q||d.label.toLowerCase().indexOf(q)!==-1)?1:0.08;});});}

      setView('bar');
    },60);});

    """









    # ── HTML templates ────────────────────────────────────────────────────────
    # Each page is a self-contained HTML document rendered inside a Marimo iframe
    # D3 v7 loads from CDN in <head>; data is injected via placeholder replacement
    _p1_html = """<!DOCTYPE html>
    <html><head><meta charset="utf-8">
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
    html,body{margin:0;padding:0;overflow:hidden;width:100%;height:100%;
      font-family:system-ui,-apple-system,sans-serif;background:#f1efe8;}
    #wrap{display:flex;flex-direction:column;height:100%;}
    #hdr{display:flex;align-items:center;justify-content:space-between;padding:7px 16px;
      background:#f8f7f4;border-bottom:1px solid #d3d1c7;flex-shrink:0;flex-wrap:wrap;gap:6px;}
    #hdr-t{font-size:13px;font-weight:600;color:#1a1a18;}
    #hdr-s{font-size:10px;color:#73726c;display:flex;gap:14px;flex-wrap:wrap;}
    #hdr-b{display:flex;gap:4px;}
    .zb{padding:3px 10px;border-radius:4px;border:1px solid #d3d1c7;background:#fff;
      font-size:11px;cursor:pointer;color:#3d3d3a;}.zb:hover{background:#f1efe8;}
    #main{display:flex;flex:1;min-height:0;}
    #canvas{flex:1;min-width:0;overflow:hidden;}
    #svg{display:block;cursor:grab;width:100%;height:100%;}#svg:active{cursor:grabbing;}
    #tip{position:fixed;display:none;background:rgba(26,26,24,.88);color:#fff;
      padding:6px 10px;border-radius:6px;font-size:11px;pointer-events:none;max-width:240px;line-height:1.5;z-index:999;}
    #panel{width:264px;min-width:264px;border-left:1px solid #d3d1c7;background:#fff;
      display:flex;flex-direction:column;overflow:hidden;}
    #ph{padding:9px 13px;font-size:11px;font-weight:600;color:#534AB7;background:#EEEDFE;
      border-bottom:1px solid #AFA9EC;flex-shrink:0;}
    #pb{padding:11px 13px;flex:1;overflow-y:auto;}
    .pp{font-size:11px;color:#888780;line-height:1.7;padding:16px 0;text-align:center;}
    #leg{display:flex;gap:10px;padding:6px 16px;background:#f8f7f4;border-top:1px solid #d3d1c7;
      flex-wrap:wrap;align-items:center;flex-shrink:0;}
    .li{display:flex;align-items:center;gap:4px;font-size:9px;color:#73726c;}
    .ll{display:inline-block;width:20px;height:3px;border-radius:2px;}
    .ln{font-size:9px;color:#b4b2a9;margin-left:auto;}
    </style></head><body>
    <div id="wrap">
      <div id="hdr">
    <span id="hdr-t">EvidenceBoard  Oceanus Investigation, Oct 2040</span>
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
        <p class="pp">Click any string to see evidence chain and temporal burst.<br>
        Click any entity card to see connections, activity sparkline, and comm stats.<br>
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
    <span class="ln">Drag cards &middot; Scroll to zoom &middot; Click to focus &middot; Click again to reset</span>
      </div>
    </div>
    <script>P1_DATA P1_JS</script></body></html>"""

    _p2_html = """<!DOCTYPE html>
    <html><head><meta charset="utf-8">
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
    html,body{margin:0;padding:0;overflow:auto;width:100%;height:100%;
      font-family:system-ui,-apple-system,sans-serif;background:#f1efe8;}
    #wrap{display:flex;flex-direction:column;height:100%;}
    #hdr2{padding:10px 16px;background:#f8f7f4;border-bottom:1px solid #d3d1c7;flex-shrink:0;}
    #hdr2 h2{margin:0;font-size:13px;font-weight:600;color:#1a1a18;}
    #hdr2 p{margin:4px 0 0;font-size:10px;color:#73726c;}
    #body2{display:flex;flex:1;min-height:0;}
    #heatmap-area{flex:1;overflow:auto;padding:12px 16px 12px 12px;}
    #cpanel{width:264px;min-width:264px;padding:12px 14px;border-left:1px solid #d3d1c7;
      background:#fff;overflow-y:auto;font-size:11px;color:#888780;line-height:1.6;}
    #tip2{position:fixed;display:none;background:rgba(26,26,24,.88);color:#fff;
      padding:6px 10px;border-radius:6px;font-size:11px;pointer-events:none;max-width:200px;line-height:1.5;z-index:999;}
    </style></head><body>
    <div id="wrap">
      <div id="hdr2">
    <h2>Communication timeline  Oct 1 to 14, 2040</h2>
    <p>Top 25 entities by total message volume. Cell colour intensity encodes daily communication count (darker = more).
    Bottom bars show total daily volume across all entities. Conflict entities marked with red dot. Click any cell to read messages. Hover entity name to highlight row.</p>
      </div>
      <div id="body2">
    <div id="heatmap-area"><svg id="heatsvg"></svg></div>
    <div id="cpanel">Click any coloured cell to read the communications for that entity on that day.</div>
      </div>
    </div>
    <div id="tip2"></div>
    <script>P2_DATA P2_JS</script></body></html>"""

    _p3_html = """<!DOCTYPE html>
    <html><head><meta charset="utf-8">
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
    html,body{margin:0;padding:0;overflow:hidden;width:100%;height:100%;
      font-family:system-ui,-apple-system,sans-serif;background:#f1efe8;}
    #wrap3{display:flex;flex-direction:column;height:100%;}
    #hdr3{padding:10px 16px;background:#f8f7f4;border-bottom:1px solid #d3d1c7;flex-shrink:0;}
    #hdr3 h2{margin:0;font-size:13px;font-weight:600;color:#1a1a18;}
    #hdr3 p{margin:4px 0 0;font-size:10px;color:#73726c;}
    #body3{display:flex;flex:1;min-height:0;}
    #chart-area{flex:1;overflow:hidden;display:flex;flex-direction:column;padding:0;}
    #sp{width:280px;min-width:280px;padding:12px 14px;border-left:1px solid #d3d1c7;
      background:#fff;overflow-y:auto;font-size:11px;color:#888780;line-height:1.6;}
    #tip3{position:fixed;display:none;background:rgba(26,26,24,.88);color:#fff;
      padding:6px 10px;border-radius:6px;font-size:11px;pointer-events:none;max-width:200px;line-height:1.5;z-index:999;}
    </style></head><body>
    <div id="wrap3">
      <div id="hdr3">
    <h2>Suspicion network analysis  Oceanus Investigation, Oct 2040</h2>
    <p>Entities ranked by total suspicious relationship evidence. Red bars are conflict entities
    (simultaneously Suspicious AND Colleagues). Click any bar to see the entity's spoke network and key communications.</p>
      </div>
      <div id="body3">
    <div id="chart-area">
    <div id="ctrl-bar" style="padding:7px 14px;background:#f8f7f4;border-bottom:1px solid #eee;display:flex;align-items:center;gap:14px;flex-wrap:wrap;flex-shrink:0;">
      <div style="display:flex;gap:4px;">
        <button id="btn-list" style="padding:3px 10px;border-radius:4px;border:1px solid #534AB7;background:#534AB7;color:white;font-size:10px;cursor:pointer;font-weight:600;">Ranked list</button>
        <button id="btn-risk" style="padding:3px 10px;border-radius:4px;border:1px solid #d3d1c7;background:#fff;color:#3d3d3a;font-size:10px;cursor:pointer;">Risk matrix</button>
      </div>
      <div style="display:flex;align-items:center;gap:6px;font-size:11px;color:#73726c;">
        <span>Min. evidence:</span>
        <span id="ev-val" style="font-weight:600;color:#3d3d3a;min-width:14px;">1</span>
        <input type="range" id="ev-filter" min="1" max="30" value="1" style="width:90px;accent-color:#534AB7;"><button id="btn-reset-zoom" style="display:none;padding:3px 9px;border-radius:4px;border:1px solid #185FA5;background:#fff;color:#185FA5;font-size:9.5px;cursor:pointer;">Reset zoom</button><input id="entity-search" type="text" placeholder="Search…" style="margin-left:8px;width:120px;padding:3px 7px;border:1px solid #d3d1c7;border-radius:4px;font-size:10px;outline:none;">
      </div>
    </div>
    <div style="flex:1;overflow-y:auto;overflow-x:hidden;"><svg id="ssvg"></svg></div>
      </div>
    <div id="sp">Click any bar to see this entity's suspicious connections and a network diagram of its relationships.</div>
      </div>
    </div>
    <div id="tip3"></div>
    <script>P3_DATA P3_JS</script></body></html>"""

    # ── Inject data and code into templates ───────────────────────────────────
    _p1_html = (_p1_html
        .replace("EC", str(len(_ve)))
        .replace("RC", str(len(_vr)))
        .replace("CC", str(_nc))
        .replace("GC", str(len(_vg)))
        .replace("P1_DATA", _p1_data)
        .replace("P1_JS",   _p1_js))
    _p2_html = _p2_html.replace("P2_DATA", _p2_data).replace("P2_JS", _p2_js)
    _p3_html = _p3_html.replace("P3_DATA", _p3_data).replace("P3_JS", _p3_js)

    # Tooltip info icons for Ghost links and Conflicts only toggles
    # Defined here in Cell 4 (not Cell 3) to avoid Marimo underscore scoping rules
    # Styled info badges with custom floating tooltip (JS-powered, not browser title)
    # Ghost = purple badge (matches EvidenceBoard panel), Conflict = red badge
    _ghost_html = (
        '<span '
        'style="display:inline-flex;align-items:center;justify-content:center;'
        'width:16px;height:16px;border-radius:50%;background:#534AB7;color:white;'
        'font-size:9px;font-weight:700;font-family:system-ui;'
        'margin-left:4px;cursor:help;vertical-align:middle;flex-shrink:0;"'
        ' title="Ghost links: shows entity pairs with 5+ communications but no '
        'relationship node in the MC3 graph (predicted data gaps). '
        'Rendered as dashed strings MacEachren et al. 2012 epistemic uncertainty encoding."'
        '>i</span>'
    )
    _ghost_tip = mo.Html(_ghost_html)

    _conflict_html = (
        '<span '
        'style="display:inline-flex;align-items:center;justify-content:center;'
        'width:16px;height:16px;border-radius:50%;background:#E24B4A;color:white;'
        'font-size:9px;font-weight:700;font-family:system-ui;'
        'margin-left:4px;cursor:help;vertical-align:middle;flex-shrink:0;"'
        ' title="Conflicts only: shows entities with BOTH Suspicious AND Colleagues/Friends '
        'relationships simultaneously. This contradiction is a key investigative signal '
        'for VAST Task 2 suggests coordinated cover behaviour."'
        '>i</span>'
    )
    _conflict_tip = mo.Html(_conflict_html)

    # ── Assemble into tabs and return ─────────────────────────────────────────
    # Tab 1: EvidenceBoard with filter controls above the iframe
    # Tab 2: Communication Timeline (standalone, no Marimo controls)
    # Tab 3: Suspicion Analysis (standalone, controls embedded in iframe HTML)
    # ── Controls and tab assembly ─────────────────────────────────────────────
    _controls = mo.hstack(
        [threshold, etype_filter, rtype_filter,
         mo.hstack([ghost_toggle, _ghost_tip], gap=0),
         mo.hstack([conflict_only, _conflict_tip], gap=0)],
        gap=2, wrap=True,
    )
    _tab1 = mo.vstack([_controls, mo.iframe(_p1_html, height="720px")])
    _tab2 = mo.iframe(_p2_html, height="720px")
    _tab3 = mo.iframe(_p3_html, height="720px")

    mo.ui.tabs({
        "EvidenceBoard":          _tab1,
        "Communication timeline": _tab2,
        "Suspicion analysis":     _tab3,
    })
    return


if __name__ == "__main__":
    app.run()
