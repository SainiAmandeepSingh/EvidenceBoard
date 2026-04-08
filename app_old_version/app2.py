import marimo

__generated_with = "0.21.1"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _():
    import json as _json
    from collections import defaultdict as _dd

    with open("data/MC3_graph.json") as _f:
        _raw = _json.load(_f)

    _nodes = _raw["nodes"]
    _edges = _raw["edges"]
    _nmap  = {n["id"]: n for n in _nodes}

    _ent_nodes = [n for n in _nodes if n["type"] == "Entity"]
    _rel_nodes = [n for n in _nodes if n["type"] == "Relationship"]

    # entity <-> relationship membership
    _r2e = _dd(list)
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _s.get("type") == "Entity" and _t.get("type") == "Relationship":
            _r2e[_e["target"]].append(_e["source"])
        if _s.get("type") == "Relationship" and _t.get("type") == "Entity":
            _r2e[_e["source"]].append(_e["target"])

    # communication evidence chains
    _r2c = _dd(list)
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _s.get("sub_type") == "Communication" and _t.get("type") == "Relationship":
            _r2c[_e["target"]].append(_e["source"])

    # sender / receiver
    _csnd, _crcv = {}, {}
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _e.get("type") == "sent" and _s.get("type") == "Entity" and _t.get("sub_type") == "Communication":
            _csnd[_e["target"]] = _e["source"]
        if _e.get("type") == "received" and _s.get("sub_type") == "Communication" and _t.get("type") == "Entity":
            _crcv[_e["source"]] = _e["target"]

    # entity-pair comms for ghost links
    _pair = _dd(list)
    for _cid, _snd in _csnd.items():
        _rcv = _crcv.get(_cid)
        if _rcv and _snd != _rcv:
            _pair[tuple(sorted([_snd, _rcv]))].append(_cid)

    # build relationship objects
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
                "from": _csnd.get(_cid, "?"),
                "to":   _crcv.get(_cid, "?"),
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

    # conflict entities
    _ert = _dd(set)
    for _r in all_rels:
        for _eid in _r["ents"]:
            _ert[_eid].add(_r["sub"])
    _conflicts = frozenset(
        _eid for _eid, _st in _ert.items()
        if "Suspicious" in _st and ("Colleagues" in _st or "Friends" in _st)
    )

    # ghost links
    _existing = {tuple(sorted(_r["ents"][:2])) for _r in all_rels}
    all_ghosts = [
        {"a": _p[0], "b": _p[1], "n": len(_c)}
        for _p, _c in _pair.items()
        if len(_c) >= 5 and _p not in _existing
    ]

    # entity records — no pre-computed layout, D3 force does it live
    _EC = {"Person":"#1D9E75","Organization":"#534AB7","Vessel":"#185FA5","Group":"#BA7517","Location":"#888780"}
    _RC = {"Suspicious":"#E24B4A","Colleagues":"#1D9E75","Friends":"#1D9E75","Operates":"#534AB7",
           "AccessPermission":"#BA7517","Coordinates":"#185FA5","Jurisdiction":"#185FA5",
           "Reports":"#3B8BD4","Unfriendly":"#D85A30"}

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

    return all_ents, all_ghosts, all_rels, all_subtypes, MAX_EV


@app.cell
def _(mo, all_subtypes, MAX_EV):
    threshold    = mo.ui.slider(1, MAX_EV, value=1, label="Min. evidence", show_value=True)
    etype_filter = mo.ui.dropdown(
        ["All","Person","Organization","Vessel","Group","Location"],
        value="All", label="Entity type",
    )
    rtype_filter = mo.ui.dropdown(
        ["All"] + all_subtypes, value="All", label="Relationship type",
    )
    ghost_toggle = mo.ui.switch(value=True, label="Ghost links")
    return etype_filter, ghost_toggle, rtype_filter, threshold


@app.cell
def _(mo, all_ents, all_rels, all_ghosts, MAX_EV,
      threshold, etype_filter, rtype_filter, ghost_toggle):
    import json as _js

    _ef = etype_filter.value
    _rf = rtype_filter.value
    _sg = ghost_toggle.value
    _mn = threshold.value

    _ve = [e for e in all_ents  if _ef == "All" or e["sub"] == _ef]
    _vi = {e["id"] for e in _ve}
    _vr = [r for r in all_rels
           if r["ev"] >= _mn and (_rf == "All" or r["sub"] == _rf)
           and r["ents"][0] in _vi and r["ents"][1] in _vi]
    _vg = [g for g in all_ghosts if _sg and g["a"] in _vi and g["b"] in _vi]
    _nc = sum(1 for e in _ve if e["conflict"])

    _ej = _js.dumps(_ve, ensure_ascii=False)
    _rj = _js.dumps(_vr, ensure_ascii=False)
    _gj = _js.dumps(_vg, ensure_ascii=False)

    _js_data = (
        "var E="   + _ej + ";\n"
        "var R="   + _rj + ";\n"
        "var GH="  + _gj + ";\n"
        "var MEV=" + str(MAX_EV) + ";\n"
    )

    # ── Full D3 force simulation with zoom, pan, drag, hover, click ───────────
    _js_code = r"""
var CW=124, CH=54, HH=17;
var COLORS={Suspicious:'#E24B4A',Colleagues:'#1D9E75',Friends:'#1D9E75',
  Operates:'#534AB7',AccessPermission:'#BA7517',Coordinates:'#185FA5',
  Jurisdiction:'#185FA5',Reports:'#3B8BD4',Unfriendly:'#D85A30'};

function sw(ev){ return Math.max(2, Math.min(10, ev*0.6+1.5)); }
function so(ev){ return Math.max(0.35, Math.min(0.95, ev/MEV*2+0.35)); }
function tr(s,n){ return s&&s.length>n?s.slice(0,n-1)+'\u2026':(s||''); }

// ── Panel helpers ─────────────────────────────────────────────────────────────
function clr(){
  document.getElementById('pb').innerHTML=
    '<p class="pp">Click any string or card to inspect details.</p>';
}

function showRel(r){
  var col=r.color||'#888780';
  var pct=Math.round(r.ev/MEV*100);
  var lbl=pct<30?'Low':pct<65?'Medium':'High';
  var h='<div style="background:'+col+'18;border:1px solid '+col+'55;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    +'<div style="font-size:11px;font-weight:600;color:'+col+';">'+r.sub+' relationship</div>'
    +'<div style="font-size:10px;color:#73726c;margin-top:2px;">'+(r.ents||[]).join(' &amp; ')+'</div></div>'
    +'<div style="font-size:10px;font-weight:600;margin:6px 0 3px;">Evidence confidence</div>'
    +'<div style="height:8px;background:#f1efe8;border-radius:4px;overflow:hidden;">'
    +'<div style="height:100%;width:'+Math.min(100,pct)+'%;background:'+col+';opacity:.85;border-radius:4px;"></div></div>'
    +'<div style="display:flex;justify-content:space-between;font-size:9px;color:#888780;margin:2px 0 10px;">'
    +'<span>'+lbl+' ('+pct+'%)</span><span>'+r.ev+' of '+MEV+' max</span></div>'
    +'<div style="font-size:10px;font-weight:600;margin-bottom:6px;">Supporting communications ('+(r.comms||[]).length+')</div>';
  (r.comms||[]).forEach(function(c){
    h+='<div style="background:#f8f7f4;border-radius:5px;padding:7px 9px;margin-bottom:6px;">'
      +'<div style="font-size:9px;font-weight:600;color:#534AB7;">'+c.ts+' \u2014 '+c.from+' \u2192 '+c.to+'</div>'
      +'<div style="font-size:10px;color:#3d3d3a;line-height:1.5;margin-top:3px;">\u201c'+tr(c.text,180)+'\u201d</div>'
      +'<div style="font-size:8.5px;color:#888780;margin-top:2px;font-style:italic;">is_inferred: '+c.inf+'</div></div>';
  });
  h+='<div style="display:flex;gap:6px;margin-top:10px;">'
    +'<button onclick="alert(\'Escalated to investigation queue\')" style="flex:1;padding:7px;border-radius:5px;font-size:10px;font-weight:600;cursor:pointer;border:1px solid '+col+';background:'+col+'18;color:'+col+';">Escalate</button>'
    +'<button onclick="clr()" style="flex:1;padding:7px;border-radius:5px;font-size:10px;cursor:pointer;border:1px solid #d3d1c7;background:transparent;color:#888780;">Dismiss</button></div>';
  document.getElementById('pb').innerHTML=h;
}

function showEnt(e){
  var col=e.hcolor||'#888780';
  var h='<div style="background:'+col+'18;border:1px solid '+col+'55;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    +'<div style="font-size:12px;font-weight:600;color:'+col+';">'+e.label+'</div>'
    +'<div style="font-size:10px;color:#73726c;margin-top:2px;">'+e.sub+(e.conflict?' \u2014 <span style=\"color:#E24B4A;font-weight:600;\">\u26A0 conflict detected</span>':'')+'</div></div>'
    +'<div style="font-size:10px;font-weight:600;margin-bottom:5px;">Relationship types</div>';
  if(e.types&&e.types.length){
    e.types.forEach(function(t){
      var tc=COLORS[t]||'#888780';
      h+='<div style="display:inline-block;margin:0 4px 4px 0;padding:3px 8px;border-radius:12px;font-size:9px;font-weight:600;background:'+tc+'20;color:'+tc+';border:1px solid '+tc+'55;">'+t+'</div>';
    });
  }else{
    h+='<p style="font-size:10px;color:#888780;">No relationships found</p>';
  }
  document.getElementById('pb').innerHTML=h;
}

function showGhost(g){
  document.getElementById('pb').innerHTML=
    '<div style="background:#8887801a;border:1px dashed #888780;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    +'<div style="font-size:11px;font-weight:600;color:#73726c;">Predicted missing relationship</div>'
    +'<div style="font-size:10px;color:#888780;margin-top:2px;">'+g.a+' &amp; '+g.b+'</div></div>'
    +'<div style="font-size:11px;color:#3d3d3a;line-height:1.7;margin-bottom:8px;">'
    +'These entities exchanged <strong>'+g.n+' communications</strong> but no relationship node was inferred in the knowledge graph.'
    +' This is a predicted data gap \u2014 a relationship that may exist in reality but was not captured during KG construction.</div>'
    +'<div style="font-size:9.5px;color:#888780;background:#f8f7f4;padding:8px;border-radius:5px;line-height:1.6;">'
    +'Dashed texture encodes epistemic uncertainty about this inferred relationship.'
    +' <em>MacEachren et al. (2012), doi:10.1145/2254556.2254592</em></div>'
    +'<div style="display:flex;gap:6px;margin-top:12px;">'
    +'<button onclick="alert(\'Flagged for manual review\')" style="flex:1;padding:7px;border-radius:5px;font-size:10px;font-weight:600;cursor:pointer;border:1px solid #534AB7;background:#EEEDFE;color:#534AB7;">Review</button>'
    +'<button onclick="clr()" style="flex:1;padding:7px;border-radius:5px;font-size:10px;cursor:pointer;border:1px solid #d3d1c7;background:transparent;color:#888780;">Dismiss</button></div>';
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
var tip = document.getElementById('tip');
function showTip(html, x, y){
  tip.innerHTML=html;
  tip.style.display='block';
  var tx = Math.min(x+14, window.innerWidth-tip.offsetWidth-10);
  tip.style.left=tx+'px';
  tip.style.top=(y-10)+'px';
}
function hideTip(){ tip.style.display='none'; }

// ── Main ──────────────────────────────────────────────────────────────────────
var W = window.innerWidth - 264;
var H = window.innerHeight - 80;

var svg = d3.select('#svg').attr('width',W).attr('height',H);
var zoomG = svg.append('g');  // all content lives here, zoom transforms this

// ── Zoom + pan ────────────────────────────────────────────────────────────────
var zoom = d3.zoom()
  .scaleExtent([0.2, 4])
  .on('zoom', function(event){ zoomG.attr('transform', event.transform); });
svg.call(zoom);

// ── Tooltip for strings ───────────────────────────────────────────────────────
// Separate layers: links behind, cards in front
var linkG  = zoomG.append('g').attr('id','link-layer');
var ghostG = zoomG.append('g').attr('id','ghost-layer');
var cardG  = zoomG.append('g').attr('id','card-layer');

// ── Build D3 node and link arrays ─────────────────────────────────────────────
// Nodes start at random positions within canvas
var nodeById = {};
var simNodes = E.map(function(e,i){
  var n = Object.assign({}, e, {
    x: W/2 + (Math.random()-0.5)*W*0.6,
    y: H/2 + (Math.random()-0.5)*H*0.6
  });
  nodeById[e.id] = n;
  return n;
});

var simLinks = R.map(function(r){
  return {data:r, source:r.ents[0], target:r.ents[1]};
});
var simGhosts = GH.map(function(g){
  return {data:g, source:g.a, target:g.b};
});

// ── Force simulation ──────────────────────────────────────────────────────────
var sim = d3.forceSimulation(simNodes)
  .force('link', d3.forceLink(simLinks)
    .id(function(d){ return d.id; })
    .distance(function(d){ return 180 + (1 - d.data.ev/MEV)*80; })
    .strength(0.4))
  .force('charge', d3.forceManyBody().strength(-600).distanceMax(500))
  .force('center', d3.forceCenter(W/2, H/2))
  .force('collision', d3.forceCollide().radius(90))
  .alphaDecay(0.03);

// ── Draw ghost strings ────────────────────────────────────────────────────────
var ghostPaths = ghostG.selectAll('.gh')
  .data(simGhosts).join('line').attr('class','gh')
  .attr('stroke','#888780').attr('stroke-width',2)
  .attr('stroke-dasharray','8,6').attr('stroke-opacity',0.5)
  .style('cursor','pointer')
  .on('mouseenter', function(event,d){
    d3.select(this).attr('stroke-width',4).attr('stroke-opacity',0.85);
    showTip('<strong>Predicted missing</strong><br>'+d.data.a+' &amp; '+d.data.b+'<br>'+d.data.n+' comms, no relationship node', event.clientX, event.clientY);
  })
  .on('mousemove', function(event){ showTip(tip.innerHTML, event.clientX, event.clientY); })
  .on('mouseleave', function(){
    d3.select(this).attr('stroke-width',2).attr('stroke-opacity',0.5);
    hideTip();
  })
  .on('click', function(event,d){ event.stopPropagation(); showGhost(d.data); });

// ── Draw relationship strings ─────────────────────────────────────────────────
var relPaths = linkG.selectAll('.rl')
  .data(simLinks).join('line').attr('class','rl')
  .attr('stroke', function(d){ return d.data.color; })
  .attr('stroke-width', function(d){ return sw(d.data.ev); })
  .attr('stroke-opacity', function(d){ return so(d.data.ev); })
  .style('cursor','pointer')
  .on('mouseenter', function(event,d){
    d3.select(this).attr('stroke-width', sw(d.data.ev)+3).attr('stroke-opacity',1);
    showTip('<strong>'+d.data.sub+'</strong><br>'+d.data.ents.join(' &amp; ')+'<br>Evidence: '+d.data.ev+'/'+MEV, event.clientX, event.clientY);
  })
  .on('mousemove', function(event){ showTip(tip.innerHTML, event.clientX, event.clientY); })
  .on('mouseleave', function(event,d){
    d3.select(this).attr('stroke-width', sw(d.data.ev)).attr('stroke-opacity', so(d.data.ev));
    hideTip();
  })
  .on('click', function(event,d){ event.stopPropagation(); showRel(d.data); });

// ── Draw entity cards ─────────────────────────────────────────────────────────
var cards = cardG.selectAll('.ec')
  .data(simNodes).join('g').attr('class','ec')
  .style('cursor','pointer')
  .on('mouseenter', function(event,d){
    d3.select(this).select('.card-body')
      .attr('stroke-width', d.conflict?2.5:1.5);
    showTip('<strong>'+d.label+'</strong><br>'+d.sub+(d.conflict?' \u26A0 conflict':''), event.clientX, event.clientY);
  })
  .on('mousemove', function(event){ showTip(tip.innerHTML, event.clientX, event.clientY); })
  .on('mouseleave', function(event,d){
    d3.select(this).select('.card-body')
      .attr('stroke-width', d.conflict?2:0.5);
    hideTip();
  })
  .on('click', function(event,d){ event.stopPropagation(); showEnt(d); })
  .call(d3.drag()
    .on('start', function(event,d){
      if(!event.active) sim.alphaTarget(0.3).restart();
      d.fx=d.x; d.fy=d.y;
      hideTip();
    })
    .on('drag', function(event,d){
      d.fx=event.x; d.fy=event.y;
    })
    .on('end', function(event,d){
      if(!event.active) sim.alphaTarget(0);
      d.fx=null; d.fy=null;
    })
  );

// Drop shadow
var defs = svg.append('defs');
var flt = defs.append('filter').attr('id','sh')
  .attr('x','-20%').attr('y','-20%').attr('width','140%').attr('height','140%');
flt.append('feDropShadow').attr('dx','0').attr('dy','1.5')
  .attr('stdDeviation','2.5').attr('flood-color','#00000020');

// Card body (white rect with border)
cards.append('rect').attr('class','card-body')
  .attr('width',CW).attr('height',CH).attr('rx',8)
  .attr('x',-CW/2).attr('y',-CH/2)
  .attr('fill','#ffffff').attr('filter','url(#sh)')
  .attr('stroke', function(d){ return d.conflict?'#E24B4A':'#d3d1c7'; })
  .attr('stroke-width', function(d){ return d.conflict?2:0.5; });

// Coloured header band
cards.append('rect')
  .attr('width',CW).attr('height',HH).attr('rx',8)
  .attr('x',-CW/2).attr('y',-CH/2)
  .attr('fill', function(d){ return d.hcolor; });
// Square off bottom of header (top rounded, bottom flat)
cards.append('rect')
  .attr('width',CW).attr('height',HH/2)
  .attr('x',-CW/2).attr('y',-CH/2+HH/2)
  .attr('fill', function(d){ return d.hcolor; });

// Entity label in header
cards.append('text')
  .attr('y', -CH/2+HH/2)
  .attr('text-anchor','middle').attr('dominant-baseline','central')
  .attr('font-size','10.5').attr('font-weight','600').attr('fill','white')
  .attr('font-family','system-ui,sans-serif')
  .text(function(d){ return tr(d.label,16); });

// Subtype row
cards.append('text')
  .attr('y', -CH/2+HH+12)
  .attr('text-anchor','middle').attr('dominant-baseline','central')
  .attr('font-size','10').attr('fill','#888780')
  .attr('font-family','system-ui,sans-serif')
  .text(function(d){ return d.sub; });

// Relationship types or conflict warning
cards.append('text')
  .attr('y', -CH/2+HH+27)
  .attr('text-anchor','middle').attr('dominant-baseline','central')
  .attr('font-size','9.5')
  .attr('font-weight', function(d){ return d.conflict?'600':'400'; })
  .attr('fill', function(d){ return d.conflict?'#E24B4A':'#888780'; })
  .attr('font-family','system-ui,sans-serif')
  .text(function(d){
    return d.conflict?'\u26A0 conflict detected':tr(d.types.slice(0,2).join(', ')||'\u2014',22);
  });

// Conflict dot
cards.filter(function(d){ return d.conflict; })
  .append('circle')
  .attr('cx', CW/2-8).attr('cy', -CH/2+8).attr('r',5)
  .attr('fill','#E24B4A');

// ── Zoom controls ─────────────────────────────────────────────────────────────
d3.select('#btn-in').on('click',  function(){ svg.transition().duration(300).call(zoom.scaleBy, 1.4); });
d3.select('#btn-out').on('click', function(){ svg.transition().duration(300).call(zoom.scaleBy, 0.7); });
d3.select('#btn-fit').on('click', function(){ svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity); });

// Click blank area to clear panel
svg.on('click', function(){ clr(); });

// ── Simulation tick ───────────────────────────────────────────────────────────
sim.on('tick', function(){
  relPaths
    .attr('x1', function(d){ return d.source.x; })
    .attr('y1', function(d){ return d.source.y; })
    .attr('x2', function(d){ return d.target.x; })
    .attr('y2', function(d){ return d.target.y; });

  ghostPaths
    .filter(function(d){ return nodeById[d.source]&&nodeById[d.target]; })
    .attr('x1', function(d){ return nodeById[d.source]?nodeById[d.source].x:0; })
    .attr('y1', function(d){ return nodeById[d.source]?nodeById[d.source].y:0; })
    .attr('x2', function(d){ return nodeById[d.target]?nodeById[d.target].x:0; })
    .attr('y2', function(d){ return nodeById[d.target]?nodeById[d.target].y:0; });

  cards.attr('transform', function(d){ return 'translate('+d.x+','+d.y+')'; });
});
"""

    _html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
html,body{margin:0;padding:0;overflow:hidden;width:100%;height:100%;
  font-family:system-ui,-apple-system,sans-serif;background:#f1efe8;}
#wrap{display:flex;flex-direction:column;height:100vh;}
#hdr{display:flex;align-items:center;justify-content:space-between;
  padding:7px 14px;background:#f8f7f4;border-bottom:1px solid #d3d1c7;
  flex-shrink:0;flex-wrap:wrap;gap:6px;z-index:10;}
#hdr-t{font-size:13px;font-weight:600;color:#1a1a18;}
#hdr-s{font-size:10px;color:#73726c;display:flex;gap:14px;flex-wrap:wrap;}
#hdr-btns{display:flex;gap:4px;}
.zb{padding:3px 9px;border-radius:4px;border:1px solid #d3d1c7;background:#fff;
  font-size:11px;cursor:pointer;color:#3d3d3a;}
.zb:hover{background:#f1efe8;}
#main{display:flex;flex:1;min-height:0;}
#canvas{flex:1;min-width:0;overflow:hidden;position:relative;}
#svg{display:block;cursor:grab;}
#svg:active{cursor:grabbing;}
#tip{position:fixed;display:none;background:rgba(26,26,24,0.88);color:#fff;
  padding:6px 10px;border-radius:6px;font-size:11px;pointer-events:none;
  max-width:240px;line-height:1.5;z-index:999;}
#panel{width:264px;min-width:264px;border-left:1px solid #d3d1c7;
  background:#fff;display:flex;flex-direction:column;overflow:hidden;}
#ph{padding:9px 13px;font-size:11px;font-weight:600;color:#534AB7;
  background:#EEEDFE;border-bottom:1px solid #AFA9EC;flex-shrink:0;}
#pb{padding:11px 13px;flex:1;overflow-y:auto;}
.pp{font-size:11px;color:#888780;line-height:1.7;padding:16px 0;text-align:center;}
#leg{display:flex;gap:10px;padding:6px 14px;background:#f8f7f4;
  border-top:1px solid #d3d1c7;flex-wrap:wrap;align-items:center;flex-shrink:0;}
.li{display:flex;align-items:center;gap:4px;font-size:9px;color:#73726c;}
.ll{display:inline-block;width:20px;height:3px;border-radius:2px;}
.ln{font-size:9px;color:#b4b2a9;margin-left:auto;}
</style>
</head>
<body>
<div id="wrap">
  <div id="hdr">
    <span id="hdr-t">EvidenceBoard &mdash; Oceanus Investigation, Oct 2040</span>
    <div id="hdr-s">
      <span>ENTITY_COUNT entities</span>
      <span>REL_COUNT relationships</span>
      <span>CONFLICT_COUNT conflicts</span>
      <span>GHOST_COUNT predicted missing</span>
    </div>
    <div id="hdr-btns">
      <button class="zb" id="btn-in">+ Zoom</button>
      <button class="zb" id="btn-out">&minus; Zoom</button>
      <button class="zb" id="btn-fit">Reset</button>
    </div>
  </div>
  <div id="main">
    <div id="canvas">
      <svg id="svg"></svg>
      <div id="tip"></div>
    </div>
    <div id="panel">
      <div id="ph">Evidence detail</div>
      <div id="pb"><p class="pp">Click any string or entity card to inspect details.</p></div>
    </div>
  </div>
  <div id="leg">
    <div class="li"><span class="ll" style="background:#E24B4A;height:4px"></span>Suspicious</div>
    <div class="li"><span class="ll" style="background:#1D9E75"></span>Colleagues/Friends</div>
    <div class="li"><span class="ll" style="background:#534AB7;height:2.5px"></span>Operates</div>
    <div class="li"><span class="ll" style="background:#BA7517;height:2px"></span>AccessPermission</div>
    <div class="li"><span class="ll" style="background:#185FA5;height:2px"></span>Coordinates</div>
    <div class="li">
      <svg width="22" height="5"><line x1="0" y1="2.5" x2="22" y2="2.5" stroke="#888780" stroke-width="2" stroke-dasharray="5,4"/></svg>
      Predicted missing
    </div>
    <span class="ln">Drag cards &middot; Scroll to zoom &middot; Click strings for evidence &middot; Red border = conflict</span>
  </div>
</div>
<script>
JS_DATA
JS_CODE
</script>
</body>
</html>"""

    _html = _html.replace("ENTITY_COUNT",   str(len(_ve)))
    _html = _html.replace("REL_COUNT",      str(len(_vr)))
    _html = _html.replace("CONFLICT_COUNT", str(_nc))
    _html = _html.replace("GHOST_COUNT",    str(len(_vg)))
    _html = _html.replace("JS_DATA",        _js_data)
    _html = _html.replace("JS_CODE",        _js_code)

    _board    = mo.iframe(_html, height="720px")
    _controls = mo.hstack([threshold, etype_filter, rtype_filter, ghost_toggle], gap=2, wrap=True)
    mo.vstack([_controls, _board])
