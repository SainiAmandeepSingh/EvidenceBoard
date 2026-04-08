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
    import networkx as _nx
    from collections import defaultdict as _dd

    with open("data/MC3_graph.json") as _f:
        _raw = _json.load(_f)

    _nodes = _raw["nodes"]
    _edges = _raw["edges"]
    _nmap  = {n["id"]: n for n in _nodes}
    _ent_nodes = [n for n in _nodes if n["type"] == "Entity"]
    _rel_nodes = [n for n in _nodes if n["type"] == "Relationship"]

    _r2e = _dd(list)
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _s.get("type") == "Entity" and _t.get("type") == "Relationship":
            _r2e[_e["target"]].append(_e["source"])
        if _s.get("type") == "Relationship" and _t.get("type") == "Entity":
            _r2e[_e["source"]].append(_e["target"])

    _r2c = _dd(list)
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _s.get("sub_type") == "Communication" and _t.get("type") == "Relationship":
            _r2c[_e["target"]].append(_e["source"])

    _csnd, _crcv = {}, {}
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _e.get("type") == "sent" and _s.get("type") == "Entity" and _t.get("sub_type") == "Communication":
            _csnd[_e["target"]] = _e["source"]
        if _e.get("type") == "received" and _s.get("sub_type") == "Communication" and _t.get("type") == "Entity":
            _crcv[_e["source"]] = _e["target"]

    _pair = _dd(list)
    for _cid, _snd in _csnd.items():
        _rcv = _crcv.get(_cid)
        if _rcv and _snd != _rcv:
            _pair[tuple(sorted([_snd, _rcv]))].append(_cid)

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

    _ert = _dd(set)
    for _r in all_rels:
        for _eid in _r["ents"]:
            _ert[_eid].add(_r["sub"])
    _conflicts = frozenset(
        _eid for _eid, _st in _ert.items()
        if "Suspicious" in _st and ("Colleagues" in _st or "Friends" in _st)
    )

    _existing = {tuple(sorted(_r["ents"][:2])) for _r in all_rels}
    all_ghosts = [
        {"a": _p[0], "b": _p[1], "n": len(_c)}
        for _p, _c in _pair.items()
        if len(_c) >= 5 and _p not in _existing
    ]

    _G = _nx.Graph()
    for _en in _ent_nodes:
        _G.add_node(_en["id"])
    for _r in all_rels:
        _G.add_edge(_r["ents"][0], _r["ents"][1], weight=_r["ev"])
    _pos = _nx.spring_layout(_G, k=4.0, iterations=200, seed=42, weight="weight")

    _EC = {"Person":"#1D9E75","Organization":"#534AB7","Vessel":"#185FA5","Group":"#BA7517","Location":"#888780"}
    all_ents = []
    for _en in _ent_nodes:
        _eid = _en["id"]
        _x, _y = _pos.get(_eid, (0.0, 0.0))
        all_ents.append({
            "id":       _eid,
            "label":    _en.get("label", _eid),
            "sub":      _en.get("sub_type", "Unknown"),
            "hcolor":   _EC.get(_en.get("sub_type", ""), "#888780"),
            "conflict": _eid in _conflicts,
            "types":    sorted(_ert.get(_eid, set())),
            "x":        round(float(_x), 4),
            "y":        round(float(_y), 4),
        })

    _RC = {"Suspicious":"#E24B4A","Colleagues":"#1D9E75","Friends":"#1D9E75","Operates":"#534AB7",
           "AccessPermission":"#BA7517","Coordinates":"#185FA5","Jurisdiction":"#185FA5",
           "Reports":"#3B8BD4","Unfriendly":"#D85A30"}
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
        ["All"] + all_subtypes, value="All", label="Relationship type",  # Change to Suspicious, Coordinates etc to filter
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

    # ── Build JavaScript as a plain string (no f-string) to avoid all escaping issues ──
    # Data is injected via simple string concatenation
    _js_data = (
        "var E=" + _ej + ";\n"
        "var R=" + _rj + ";\n"
        "var GH=" + _gj + ";\n"
        "var MEV=" + str(MAX_EV) + ";\n"
    )

    _js_code = r"""
var CW=130, CH=58, HH=18;

function sw(ev){ return Math.max(1.5, Math.min(8, ev*0.55+1.2)); }
function so(ev){ return Math.max(0.3, Math.min(0.9, ev/MEV*2.4+0.3)); }
function tr(s,n){ return s && s.length>n ? s.slice(0,n-1)+'\u2026' : (s||''); }

function qp(a,b,ep,k){
  var pa=ep[a], pb=ep[b];
  if(!pa||!pb) return '';
  var f=k||0.18;
  return 'M'+pa.cx+','+pa.cy+' Q'+
    ((pa.cx+pb.cx)/2+(pb.cy-pa.cy)*f)+','+
    ((pa.cy+pb.cy)/2-(pb.cx-pa.cx)*f)+' '+pb.cx+','+pb.cy;
}

function rst(){
  d3.selectAll('.rs').each(function(d){
    if(d3.select(this).attr('s')==='1')
      d3.select(this).attr('s','0').attr('stroke-width',sw(d.ev)).attr('stroke-opacity',so(d.ev));
  });
  d3.selectAll('.gs').each(function(){
    if(d3.select(this).attr('s')==='1')
      d3.select(this).attr('s','0').attr('stroke-opacity',0.45).attr('stroke-width',2);
  });
}

function clr(){
  document.getElementById('pb').innerHTML='<p class="pp">Click any string to inspect its evidence chain.</p>';
}

function showR(r){
  var col=r.color||'#888780';
  var pct=Math.round(r.ev/MEV*100);
  var lbl=pct<30?'Low':pct<65?'Medium':'High';
  var h='<div style="background:'+col+'18;border:1px solid '+col+'55;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    +'<div style="font-size:11px;font-weight:600;color:'+col+';">'+r.sub+' relationship</div>'
    +'<div style="font-size:10px;color:#73726c;margin-top:2px;">'+(r.ents||[]).join(' &amp; ')+'</div></div>'
    +'<div style="font-size:10px;font-weight:600;margin:6px 0 3px;">Confidence</div>'
    +'<div style="height:7px;background:#f1efe8;border-radius:4px;overflow:hidden;">'
    +'<div style="height:100%;width:'+Math.min(100,pct)+'%;background:'+col+';opacity:.85;"></div></div>'
    +'<div style="display:flex;justify-content:space-between;font-size:9px;color:#888780;margin:2px 0 8px;">'
    +'<span>'+lbl+' ('+pct+'%)</span><span>'+r.ev+'/'+MEV+'</span></div>'
    +'<div style="font-size:10px;font-weight:600;margin-bottom:5px;">Communications ('+(r.comms||[]).length+')</div>';
  (r.comms||[]).forEach(function(c){
    h+='<div style="background:#f8f7f4;border-radius:5px;padding:6px 8px;margin-bottom:6px;">'
      +'<div style="font-size:9px;font-weight:600;color:#534AB7;">'+c.ts+' \u2014 '+c.from+' \u2192 '+c.to+'</div>'
      +'<div style="font-size:10px;color:#3d3d3a;line-height:1.5;margin-top:2px;">\u201c'+tr(c.text,180)+'\u201d</div>'
      +'<div style="font-size:8.5px;color:#888780;margin-top:2px;font-style:italic;">is_inferred: '+c.inf+'</div></div>';
  });
  h+='<div style="display:flex;gap:6px;margin-top:8px;">'
    +'<button onclick="alert(\'Escalated\')" style="flex:1;padding:6px;border-radius:5px;font-size:10px;font-weight:600;cursor:pointer;border:1px solid '+col+';background:'+col+'18;color:'+col+';">Escalate</button>'
    +'<button onclick="clr()" style="flex:1;padding:6px;border-radius:5px;font-size:10px;cursor:pointer;border:1px solid #d3d1c7;background:transparent;color:#888780;">Dismiss</button></div>';
  document.getElementById('pb').innerHTML=h;
}

function showGH(g){
  document.getElementById('pb').innerHTML=
    '<div style="background:#8887801a;border:1px dashed #888780;border-radius:6px;padding:8px 10px;margin-bottom:10px;">'
    +'<div style="font-size:11px;font-weight:600;color:#73726c;">Predicted missing relationship</div>'
    +'<div style="font-size:10px;color:#888780;margin-top:2px;">'+g.a+' &amp; '+g.b+'</div></div>'
    +'<div style="font-size:11px;color:#3d3d3a;line-height:1.7;margin-bottom:6px;">'
    +'These entities exchanged <strong>'+g.n+' communications</strong> but no relationship node exists. Predicted data gap.</div>'
    +'<div style="font-size:9px;color:#888780;">Dashed texture encodes epistemic uncertainty (MacEachren et al. 2012).</div>'
    +'<div style="display:flex;gap:6px;margin-top:10px;">'
    +'<button onclick="alert(\'Flagged\')" style="flex:1;padding:6px;border-radius:5px;font-size:10px;font-weight:600;cursor:pointer;border:1px solid #534AB7;background:#EEEDFE;color:#534AB7;">Review</button>'
    +'<button onclick="clr()" style="flex:1;padding:6px;border-radius:5px;font-size:10px;cursor:pointer;border:1px solid #d3d1c7;background:transparent;color:#888780;">Dismiss</button></div>';
}

// KEY FIX: give SVG explicit pixel dimensions matching the canvas area
var W = window.innerWidth - 260;
var H = window.innerHeight - 80;
if(W < 100) W = 700;
if(H < 100) H = 560;

var svg = d3.select('#svg')
  .attr('width', W)
  .attr('height', H)
  .attr('viewBox', '0 0 '+W+' '+H);

var scX = d3.scaleLinear().domain([-1.0,1.0]).range([22+CW/2, W-22-CW/2]);
var scY = d3.scaleLinear().domain([-1.0,1.0]).range([36+CH/2, H-14-CH/2]);

var ep = {};
E.forEach(function(e){
  var cx=scX(e.x), cy=scY(e.y);
  ep[e.id]={cx:cx, cy:cy, lx:cx-CW/2, ly:cy-CH/2};
});

var defs = svg.append('defs');
var fl = defs.append('filter').attr('id','sh')
  .attr('x','-20%').attr('y','-20%').attr('width','140%').attr('height','140%');
fl.append('feDropShadow').attr('dx','0').attr('dy','1')
  .attr('stdDeviation','2').attr('flood-color','#00000018');

var sl = svg.append('g');

sl.selectAll('.gs').data(GH).join('path').attr('class','gs').attr('s','0')
  .attr('d', function(d,i){ return qp(d.a,d.b,ep,0.22+i*0.08); })
  .attr('fill','none').attr('stroke','#888780')
  .attr('stroke-width',2).attr('stroke-dasharray','8,6')
  .attr('stroke-opacity',0.45).style('cursor','pointer')
  .on('mouseenter', function(){ if(d3.select(this).attr('s')!=='1') d3.select(this).attr('stroke-opacity',0.8).attr('stroke-width',3.5); })
  .on('mouseleave', function(){ if(d3.select(this).attr('s')!=='1') d3.select(this).attr('stroke-opacity',0.45).attr('stroke-width',2); })
  .on('click', function(ev,d){ rst(); d3.select(this).attr('s','1').attr('stroke-opacity',0.9).attr('stroke-width',4); showGH(d); });

sl.selectAll('.rs').data(R).join('path').attr('class','rs').attr('s','0')
  .attr('d', function(d,i){ return qp(d.ents[0],d.ents[1],ep,0.12+(i%5)*0.04); })
  .attr('fill','none')
  .attr('stroke', function(d){ return d.color; })
  .attr('stroke-width', function(d){ return sw(d.ev); })
  .attr('stroke-opacity', function(d){ return so(d.ev); })
  .style('cursor','pointer')
  .on('mouseenter', function(ev,d){ if(d3.select(this).attr('s')!=='1') d3.select(this).attr('stroke-width',sw(d.ev)+2.5).attr('stroke-opacity',1); })
  .on('mouseleave', function(ev,d){ if(d3.select(this).attr('s')!=='1') d3.select(this).attr('stroke-width',sw(d.ev)).attr('stroke-opacity',so(d.ev)); })
  .on('click', function(ev,d){ rst(); d3.select(this).attr('s','1').attr('stroke-width',9).attr('stroke-opacity',1); showR(d); });

var cl = svg.append('g');
var cards = cl.selectAll('.ec').data(E).join('g').attr('class','ec')
  .attr('transform', function(d){ var p=ep[d.id]; return p?'translate('+p.lx+','+p.ly+')':'translate(0,0)'; });

cards.append('rect').attr('width',CW).attr('height',CH).attr('rx',7)
  .attr('fill','#ffffff').attr('filter','url(#sh)')
  .attr('stroke', function(d){ return d.conflict?'#E24B4A':'#d3d1c7'; })
  .attr('stroke-width', function(d){ return d.conflict?2:0.5; });

cards.append('rect').attr('width',CW).attr('height',HH).attr('rx',7)
  .attr('fill', function(d){ return d.hcolor; });
cards.append('rect').attr('y',HH/2).attr('width',CW).attr('height',HH/2)
  .attr('fill', function(d){ return d.hcolor; });

cards.append('text').attr('x',CW/2).attr('y',HH/2)
  .attr('text-anchor','middle').attr('dominant-baseline','central')
  .attr('font-size','10.5').attr('font-weight','600').attr('fill','white')
  .attr('font-family','system-ui,sans-serif')
  .text(function(d){ return tr(d.label,17); });

cards.append('text').attr('x',CW/2).attr('y',HH+13)
  .attr('text-anchor','middle').attr('dominant-baseline','central')
  .attr('font-size','10').attr('fill','#73726c')
  .attr('font-family','system-ui,sans-serif')
  .text(function(d){ return d.sub; });

cards.append('text').attr('x',CW/2).attr('y',HH+28)
  .attr('text-anchor','middle').attr('dominant-baseline','central')
  .attr('font-size','9.5')
  .attr('font-weight', function(d){ return d.conflict?'600':'400'; })
  .attr('fill', function(d){ return d.conflict?'#E24B4A':'#888780'; })
  .attr('font-family','system-ui,sans-serif')
  .text(function(d){
    return d.conflict ? '\u26A0 conflict' : tr(d.types.slice(0,2).join(', ')||'\u2014',22);
  });

cards.filter(function(d){ return d.conflict; })
  .append('circle').attr('cx',CW-8).attr('cy',8).attr('r',5).attr('fill','#E24B4A');

svg.append('text').attr('x',12).attr('y',22)
  .attr('font-size','9.5').attr('fill','#b4b2a9')
  .attr('font-family','system-ui,sans-serif')
  .text('Click any string \u00B7 Width = evidence \u00B7 Opacity = confidence');
"""

    # HTML for the iframe — JS code is a raw string so no escaping issues at all
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
  padding:8px 16px;background:#f8f7f4;border-bottom:1px solid #d3d1c7;
  flex-shrink:0;flex-wrap:wrap;gap:6px;}
#hdr-t{font-size:13px;font-weight:600;color:#1a1a18;}
#hdr-s{font-size:10px;color:#73726c;display:flex;gap:12px;}
#main{display:flex;flex:1;min-height:0;}
#canvas{flex:1;min-width:0;overflow:hidden;}
#svg{display:block;}
#panel{width:260px;min-width:260px;border-left:1px solid #d3d1c7;
  background:#fff;display:flex;flex-direction:column;overflow:hidden;}
#ph{padding:9px 12px;font-size:11px;font-weight:600;color:#534AB7;
  background:#EEEDFE;border-bottom:1px solid #AFA9EC;flex-shrink:0;}
#pb{padding:10px 12px;flex:1;overflow-y:auto;}
.pp{font-size:11px;color:#888780;line-height:1.7;padding:14px 0;text-align:center;}
#leg{display:flex;gap:10px;padding:6px 16px;background:#f8f7f4;
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
  </div>
  <div id="main">
    <div id="canvas"><svg id="svg"></svg></div>
    <div id="panel">
      <div id="ph">Evidence detail</div>
      <div id="pb"><p class="pp">Click any string to inspect its evidence chain.</p></div>
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
    <span class="ln">Width = evidence &middot; Opacity = confidence &middot; Red border = conflict</span>
  </div>
</div>
<script>
JS_DATA_PLACEHOLDER
JS_CODE_PLACEHOLDER
</script>
</body>
</html>"""

    # Replace placeholders — completely avoids f-string escaping issues
    _html = _html.replace("ENTITY_COUNT",   str(len(_ve)))
    _html = _html.replace("REL_COUNT",      str(len(_vr)))
    _html = _html.replace("CONFLICT_COUNT", str(_nc))
    _html = _html.replace("GHOST_COUNT",    str(len(_vg)))
    _html = _html.replace("JS_DATA_PLACEHOLDER", _js_data)
    _html = _html.replace("JS_CODE_PLACEHOLDER",  _js_code)

    _board    = mo.iframe(_html, height="720px")
    _controls = mo.hstack([threshold, etype_filter, rtype_filter, ghost_toggle], gap=2, wrap=True)
    mo.vstack([_controls, _board])
