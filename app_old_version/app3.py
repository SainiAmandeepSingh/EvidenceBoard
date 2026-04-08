import marimo

__generated_with = "0.21.1"
app = marimo.App(width="full")


# ── Cell 1: Marimo import ────────────────────────────────────────────────────
@app.cell
def _():
    import marimo as mo
    return (mo,)


# ── Cell 2: Data loading and computation ─────────────────────────────────────
# This cell runs once at startup. It loads MC3_graph.json and computes:
#   - Entity records with subtype colours and conflict flags
#   - Relationship objects with full evidence chains (up to 8 supporting comms)
#   - Ghost links: entity pairs with >= 5 communications but no relationship node
#   - Conflict entities: those with both Suspicious AND Colleagues/Friends
# No NetworkX layout here — D3 force simulation handles positioning live in browser.
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

    # Build entity <-> relationship membership from graph edges
    _r2e = _dd(list)
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _s.get("type") == "Entity" and _t.get("type") == "Relationship":
            _r2e[_e["target"]].append(_e["source"])
        if _s.get("type") == "Relationship" and _t.get("type") == "Entity":
            _r2e[_e["source"]].append(_e["target"])

    # Build evidence chains: which Communications support each Relationship
    _r2c = _dd(list)
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _s.get("sub_type") == "Communication" and _t.get("type") == "Relationship":
            _r2c[_e["target"]].append(_e["source"])

    # Build sender and receiver lookups for each Communication node
    _csnd, _crcv = {}, {}
    for _e in _edges:
        _s = _nmap.get(_e["source"], {})
        _t = _nmap.get(_e["target"], {})
        if _e.get("type") == "sent" and _s.get("type") == "Entity" and _t.get("sub_type") == "Communication":
            _csnd[_e["target"]] = _e["source"]
        if _e.get("type") == "received" and _s.get("sub_type") == "Communication" and _t.get("type") == "Entity":
            _crcv[_e["source"]] = _e["target"]

    # Count communications per entity pair (used for ghost link detection)
    _pair = _dd(list)
    for _cid, _snd in _csnd.items():
        _rcv = _crcv.get(_cid)
        if _rcv and _snd != _rcv:
            _pair[tuple(sorted([_snd, _rcv]))].append(_cid)

    # Build relationship objects with evidence metadata
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
        # Store up to 8 supporting communications with full content
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

    # Identify conflict entities: have BOTH Suspicious AND Colleagues/Friends
    # These are the most analytically significant nodes (Task 2: find anomalies)
    _ert = _dd(set)
    for _r in all_rels:
        for _eid in _r["ents"]:
            _ert[_eid].add(_r["sub"])
    _conflicts = frozenset(
        _eid for _eid, _st in _ert.items()
        if "Suspicious" in _st and ("Colleagues" in _st or "Friends" in _st)
    )

    # Ghost links: entity pairs with 5+ shared communications but NO relationship node
    # These are predicted missing relationships (Task 3: infer missing data)
    _existing = {tuple(sorted(_r["ents"][:2])) for _r in all_rels}
    all_ghosts = [
        {"a": _p[0], "b": _p[1], "n": len(_c)}
        for _p, _c in _pair.items()
        if len(_c) >= 5 and _p not in _existing
    ]

    # Colour maps for entity subtypes and relationship types
    _EC = {
        "Person":       "#1D9E75",
        "Organization": "#534AB7",
        "Vessel":       "#185FA5",
        "Group":        "#BA7517",
        "Location":     "#888780",
    }
    _RC = {
        "Suspicious":       "#E24B4A",
        "Colleagues":       "#1D9E75",
        "Friends":          "#1D9E75",
        "Operates":         "#534AB7",
        "AccessPermission": "#BA7517",
        "Coordinates":      "#185FA5",
        "Jurisdiction":     "#185FA5",
        "Reports":          "#3B8BD4",
        "Unfriendly":       "#D85A30",
    }

    # Build entity records (positions assigned by D3 force simulation at runtime)
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

    # Add colour to each relationship for rendering
    for _r in all_rels:
        _r["color"] = _RC.get(_r["sub"], "#888780")

    all_subtypes = sorted(set(_r["sub"] for _r in all_rels))

    return all_ents, all_ghosts, all_rels, all_subtypes, MAX_EV


# ── Cell 3: UI controls ───────────────────────────────────────────────────────
# Controls are created here. Values are READ in Cell 4, not here.
# Marimo rule: cannot read .value in the same cell that creates the element.
@app.cell
def _(mo, all_subtypes, MAX_EV):
    threshold      = mo.ui.slider(1, MAX_EV, value=1, label="Min. evidence", show_value=True)
    etype_filter   = mo.ui.dropdown(
        ["All", "Person", "Organization", "Vessel", "Group", "Location"],
        value="All", label="Entity type",
    )
    rtype_filter   = mo.ui.dropdown(
        ["All"] + all_subtypes, value="All", label="Relationship type",
    )
    ghost_toggle   = mo.ui.switch(value=True, label="Ghost links")
    conflict_only  = mo.ui.switch(value=False, label="Conflicts only")
    return conflict_only, etype_filter, ghost_toggle, rtype_filter, threshold


# ── Cell 4: Filter data and render the EvidenceBoard ─────────────────────────
# This cell re-runs every time a control changes.
# It filters the data, serialises it to JSON, and builds the complete iframe HTML.
@app.cell
def _(mo, all_ents, all_rels, all_ghosts, MAX_EV,
      threshold, etype_filter, rtype_filter, ghost_toggle, conflict_only):
    import json as _js

    # Read current control values
    _ef = etype_filter.value
    _rf = rtype_filter.value
    _sg = ghost_toggle.value
    _mn = threshold.value
    _co = conflict_only.value

    # Apply filters to entities
    _ve = [
        e for e in all_ents
        if (_ef == "All" or e["sub"] == _ef)
        and (not _co or e["conflict"])
    ]
    _vi = {e["id"] for e in _ve}

    # Apply filters to relationships (both endpoints must be in visible entity set)
    _vr = [
        r for r in all_rels
        if r["ev"] >= _mn
        and (_rf == "All" or r["sub"] == _rf)
        and r["ents"][0] in _vi
        and r["ents"][1] in _vi
    ]

    # Find which entities actually have at least one visible relationship
    _connected = set()
    for _r in _vr:
        _connected.add(_r["ents"][0])
        _connected.add(_r["ents"][1])

    # Only show ghost links when ghost toggle is on
    _vg = [g for g in all_ghosts if _sg and g["a"] in _vi and g["b"] in _vi]
    for _g in _vg:
        _connected.add(_g["a"])
        _connected.add(_g["b"])

    # Remove isolated entities (no visible relationships) to reduce clutter
    _ve = [e for e in _ve if e["id"] in _connected]
    _vi = {e["id"] for e in _ve}

    _nc = sum(1 for e in _ve if e["conflict"])

    # Serialise filtered data to JSON for injection into JavaScript
    _ej = _js.dumps(_ve, ensure_ascii=False)
    _rj = _js.dumps(_vr, ensure_ascii=False)
    _gj = _js.dumps(_vg, ensure_ascii=False)

    _js_data = (
        "var E="   + _ej + ";\n"
        "var R="   + _rj + ";\n"
        "var GH="  + _gj + ";\n"
        "var MEV=" + str(MAX_EV) + ";\n"
    )

    # ── JavaScript: D3 force simulation with zoom, pan, drag, focus mode ─────
    # Written as a raw string (r"""...""") so { } need no escaping.
    _js_code = r"""

// ── Colour maps (must match Python side) ─────────────────────────────────────
var REL_COLORS = {
  Suspicious: '#E24B4A', Colleagues: '#1D9E75', Friends: '#1D9E75',
  Operates: '#534AB7', AccessPermission: '#BA7517',
  Coordinates: '#185FA5', Jurisdiction: '#185FA5',
  Reports: '#3B8BD4', Unfriendly: '#D85A30'
};

// ── Card dimensions ───────────────────────────────────────────────────────────
var CW = 124, CH = 54, HH = 17;

// ── Stroke helpers (evidence -> visual weight) ────────────────────────────────
// Width encodes evidence count: more comms = thicker string (Ware 2004)
function strokeW(ev) { return Math.max(2, Math.min(10, ev * 0.6 + 1.5)); }
// Opacity encodes inference confidence: more comms = more opaque (MacEachren 2012)
function strokeO(ev) { return Math.max(0.35, Math.min(0.95, ev / MEV * 2 + 0.35)); }
// Truncate long strings for card labels
function trunc(s, n) { return s && s.length > n ? s.slice(0, n - 1) + '\u2026' : (s || ''); }

// ── Evidence detail panel helpers ────────────────────────────────────────────
function clearPanel() {
  document.getElementById('pb').innerHTML =
    '<p class="pp">Click any string or entity card to inspect details.</p>';
}

// Show relationship details when a string is clicked
function showRel(r) {
  var col = r.color || '#888780';
  var pct = Math.round(r.ev / MEV * 100);
  var lbl = pct < 30 ? 'Low' : pct < 65 ? 'Medium' : 'High';
  var h =
    '<div style="background:' + col + '18;border:1px solid ' + col + '55;' +
    'border-radius:6px;padding:8px 10px;margin-bottom:10px;">' +
    '<div style="font-size:11px;font-weight:600;color:' + col + ';">' + r.sub + ' relationship</div>' +
    '<div style="font-size:10px;color:#73726c;margin-top:2px;">' + (r.ents || []).join(' and ') + '</div></div>' +
    '<div style="font-size:10px;font-weight:600;margin:6px 0 3px;">Evidence confidence</div>' +
    '<div style="height:8px;background:#f1efe8;border-radius:4px;overflow:hidden;">' +
    '<div style="height:100%;width:' + Math.min(100, pct) + '%;background:' + col + ';opacity:.85;border-radius:4px;"></div></div>' +
    '<div style="display:flex;justify-content:space-between;font-size:9px;color:#888780;margin:2px 0 10px;">' +
    '<span>' + lbl + ' (' + pct + '%)</span><span>' + r.ev + ' of ' + MEV + ' max</span></div>' +
    '<div style="font-size:10px;font-weight:600;margin-bottom:6px;">Supporting communications (' + (r.comms || []).length + ')</div>';
  (r.comms || []).forEach(function(c) {
    h += '<div style="background:#f8f7f4;border-radius:5px;padding:7px 9px;margin-bottom:6px;">' +
      '<div style="font-size:9px;font-weight:600;color:#534AB7;">' + c.ts + '  ' + c.from + ' to ' + c.to + '</div>' +
      '<div style="font-size:10px;color:#3d3d3a;line-height:1.5;margin-top:3px;">\u201c' + trunc(c.text, 180) + '\u201d</div>' +
      '<div style="font-size:8.5px;color:#888780;margin-top:2px;font-style:italic;">is_inferred: ' + c.inf + '</div></div>';
  });
  h += '<div style="display:flex;gap:6px;margin-top:10px;">' +
    '<button onclick="alert(\'Escalated to investigation queue\')" ' +
    'style="flex:1;padding:7px;border-radius:5px;font-size:10px;font-weight:600;cursor:pointer;' +
    'border:1px solid ' + col + ';background:' + col + '18;color:' + col + ';">Escalate</button>' +
    '<button onclick="clearPanel()" ' +
    'style="flex:1;padding:7px;border-radius:5px;font-size:10px;cursor:pointer;' +
    'border:1px solid #d3d1c7;background:transparent;color:#888780;">Dismiss</button></div>';
  document.getElementById('pb').innerHTML = h;
}

// Show entity details when a card is clicked
function showEnt(e) {
  var col = e.hcolor || '#888780';
  var conflictBadge = e.conflict
    ? '<span style="color:#E24B4A;font-weight:600;"> \u26A0 Conflict entity</span>' +
      '<div style="font-size:9.5px;color:#888780;margin-top:4px;line-height:1.5;">' +
      'This entity has both a Suspicious relationship and a Colleagues or Friends relationship.' +
      ' This contradiction is a key investigative signal.</div>'
    : '';
  var h =
    '<div style="background:' + col + '18;border:1px solid ' + col + '55;' +
    'border-radius:6px;padding:8px 10px;margin-bottom:10px;">' +
    '<div style="font-size:12px;font-weight:600;color:' + col + ';">' + e.label + '</div>' +
    '<div style="font-size:10px;color:#73726c;margin-top:2px;">' + e.sub + conflictBadge + '</div></div>' +
    '<div style="font-size:10px;font-weight:600;margin-bottom:6px;">Relationship types</div>';
  if (e.types && e.types.length) {
    e.types.forEach(function(t) {
      var tc = REL_COLORS[t] || '#888780';
      h += '<span style="display:inline-block;margin:0 4px 4px 0;padding:3px 8px;border-radius:12px;' +
        'font-size:9px;font-weight:600;background:' + tc + '20;color:' + tc + ';border:1px solid ' + tc + '55;">' + t + '</span>';
    });
  } else {
    h += '<p style="font-size:10px;color:#888780;">No relationships in current filter</p>';
  }
  document.getElementById('pb').innerHTML = h;
}

// Show ghost link details when a predicted missing string is clicked
function showGhost(g) {
  document.getElementById('pb').innerHTML =
    '<div style="background:#8887801a;border:1px dashed #888780;border-radius:6px;padding:8px 10px;margin-bottom:10px;">' +
    '<div style="font-size:11px;font-weight:600;color:#73726c;">Predicted missing relationship</div>' +
    '<div style="font-size:10px;color:#888780;margin-top:2px;">' + g.a + ' and ' + g.b + '</div></div>' +
    '<div style="font-size:11px;color:#3d3d3a;line-height:1.7;margin-bottom:8px;">' +
    'These entities exchanged <strong>' + g.n + ' communications</strong> but no relationship node was inferred ' +
    'in the knowledge graph. This is a predicted data gap: a relationship that likely exists in reality ' +
    'but was not captured during knowledge graph construction.</div>' +
    '<div style="font-size:9.5px;color:#888780;background:#f8f7f4;padding:8px;border-radius:5px;line-height:1.6;">' +
    'The dashed visual texture encodes epistemic uncertainty about this inferred relationship. ' +
    'Uncertainty visualisation principle from MacEachren et al. (2012), doi:10.1145/2254556.2254592</div>' +
    '<div style="display:flex;gap:6px;margin-top:12px;">' +
    '<button onclick="alert(\'Flagged for manual review\')" ' +
    'style="flex:1;padding:7px;border-radius:5px;font-size:10px;font-weight:600;cursor:pointer;' +
    'border:1px solid #534AB7;background:#EEEDFE;color:#534AB7;">Review</button>' +
    '<button onclick="clearPanel()" ' +
    'style="flex:1;padding:7px;border-radius:5px;font-size:10px;cursor:pointer;' +
    'border:1px solid #d3d1c7;background:transparent;color:#888780;">Dismiss</button></div>';
}

// ── Tooltip (floating dark label on hover) ────────────────────────────────────
var tip = document.getElementById('tip');
function showTip(html, x, y) {
  tip.innerHTML = html;
  tip.style.display = 'block';
  var tx = Math.min(x + 14, window.innerWidth - tip.offsetWidth - 10);
  tip.style.left = tx + 'px';
  tip.style.top = (y - 10) + 'px';
}
function hideTip() { tip.style.display = 'none'; }

// ── Canvas sizing ─────────────────────────────────────────────────────────────
// Use full window width minus the 264px evidence panel
var W = window.innerWidth - 264;
var H = window.innerHeight - 80;

// ── SVG setup with zoom container ─────────────────────────────────────────────
var svg  = d3.select('#svg').attr('width', W).attr('height', H);
var zoomG = svg.append('g'); // All drawable content lives in this group

// ── Zoom and pan behaviour ────────────────────────────────────────────────────
// d3.zoom handles mouse wheel (scale), click-drag (translate), and touch
var zoomBehaviour = d3.zoom()
  .scaleExtent([0.15, 5])
  .on('zoom', function(event) {
    zoomG.attr('transform', event.transform);
  });
svg.call(zoomBehaviour);

// ── Layer order: ghost strings, relationship strings, cards on top ────────────
var ghostLayer = zoomG.append('g').attr('id', 'ghost-layer');
var linkLayer  = zoomG.append('g').attr('id', 'link-layer');
var cardLayer  = zoomG.append('g').attr('id', 'card-layer');

// ── Build node map for ghost link position lookups ────────────────────────────
var nodeById = {};

// ── Prepare D3 simulation nodes with random starting positions ────────────────
var simNodes = E.map(function(e) {
  var n = Object.assign({}, e, {
    x: W / 2 + (Math.random() - 0.5) * W * 0.5,
    y: H / 2 + (Math.random() - 0.5) * H * 0.5,
  });
  nodeById[e.id] = n;
  return n;
});

// Relationship strings: each link references source/target by entity id
var simLinks = R.map(function(r) {
  return { data: r, source: r.ents[0], target: r.ents[1] };
});

// Ghost links reference entities by id in nodeById
var simGhosts = GH.map(function(g) {
  return { data: g, source: g.a, target: g.b };
});

// ── D3 force simulation ────────────────────────────────────────────────────────
// Forces: repulsion between all nodes, attraction along links, center gravity, collision
var sim = d3.forceSimulation(simNodes)
  .force('link', d3.forceLink(simLinks)
    .id(function(d) { return d.id; })
    // Longer distance for weak-evidence links (more uncertainty = more space)
    .distance(function(d) { return 160 + (1 - d.data.ev / MEV) * 100; })
    .strength(0.5))
  .force('charge', d3.forceManyBody().strength(-700).distanceMax(600))
  .force('center', d3.forceCenter(W / 2, H / 2))
  // Collision radius prevents cards from overlapping
  .force('collision', d3.forceCollide().radius(80).strength(0.9))
  .alphaDecay(0.025);

// ── Focus mode state ──────────────────────────────────────────────────────────
// When an entity or string is selected, connected elements highlight, rest dim
var focusedId   = null; // entity id or null
var focusedLink = null; // link data or null

function dimAll() {
  // Dim all strings and cards to background
  linkLayer.selectAll('.rl').attr('stroke-opacity', 0.08);
  ghostLayer.selectAll('.gh').attr('stroke-opacity', 0.06);
  cardLayer.selectAll('.ec').attr('opacity', 0.12);
}

function resetFocus() {
  // Restore all elements to their normal opacity
  focusedId   = null;
  focusedLink = null;
  linkLayer.selectAll('.rl')
    .attr('stroke-opacity', function(d) { return strokeO(d.data.ev); })
    .attr('stroke-width',   function(d) { return strokeW(d.data.ev); });
  ghostLayer.selectAll('.gh').attr('stroke-opacity', 0.5).attr('stroke-width', 2);
  cardLayer.selectAll('.ec').attr('opacity', 1);
}

function focusOnEntity(eid) {
  // Highlight the selected entity and all its direct neighbours and connecting strings
  focusedId = eid;
  dimAll();
  // Find all links connected to this entity
  linkLayer.selectAll('.rl').each(function(d) {
    var src = typeof d.source === 'object' ? d.source.id : d.source;
    var tgt = typeof d.target === 'object' ? d.target.id : d.target;
    if (src === eid || tgt === eid) {
      d3.select(this)
        .attr('stroke-opacity', strokeO(d.data.ev))
        .attr('stroke-width', strokeW(d.data.ev) + 1);
      // Also highlight the neighbour card
      var neighbourId = src === eid ? tgt : src;
      cardLayer.selectAll('.ec').filter(function(n) { return n.id === neighbourId; })
        .attr('opacity', 1);
    }
  });
  // Highlight ghost links connected to this entity
  ghostLayer.selectAll('.gh').each(function(d) {
    var src = typeof d.source === 'object' ? d.source.id || d.source : d.source;
    var tgt = typeof d.target === 'object' ? d.target.id || d.target : d.target;
    if (src === eid || tgt === eid) {
      d3.select(this).attr('stroke-opacity', 0.8).attr('stroke-width', 3);
      var nid = src === eid ? tgt : src;
      cardLayer.selectAll('.ec').filter(function(n) { return n.id === nid; }).attr('opacity', 1);
    }
  });
  // Always fully highlight the clicked entity itself
  cardLayer.selectAll('.ec').filter(function(d) { return d.id === eid; }).attr('opacity', 1);
}

function focusOnLink(linkDatum) {
  // Highlight the selected string and its two endpoint cards
  focusedLink = linkDatum;
  dimAll();
  var eid0 = linkDatum.ents[0];
  var eid1 = linkDatum.ents[1];
  linkLayer.selectAll('.rl').filter(function(d) { return d.data === linkDatum; })
    .attr('stroke-opacity', 1)
    .attr('stroke-width', strokeW(linkDatum.ev) + 2);
  cardLayer.selectAll('.ec').filter(function(d) { return d.id === eid0 || d.id === eid1; })
    .attr('opacity', 1);
}

// ── Draw ghost strings (predicted missing relationships) ──────────────────────
var ghostPaths = ghostLayer.selectAll('.gh')
  .data(simGhosts).join('line').attr('class', 'gh')
  .attr('stroke', '#888780')
  .attr('stroke-width', 2)
  .attr('stroke-dasharray', '8,6')
  .attr('stroke-opacity', 0.5)
  .style('cursor', 'pointer')
  .on('mouseenter', function(event, d) {
    if (focusedId === null && focusedLink === null)
      d3.select(this).attr('stroke-width', 4).attr('stroke-opacity', 0.85);
    showTip(
      '<strong>Predicted missing</strong><br>' + d.data.a + ' and ' + d.data.b + '<br>' + d.data.n + ' comms, no relationship node',
      event.clientX, event.clientY
    );
  })
  .on('mousemove', function(event) { showTip(tip.innerHTML, event.clientX, event.clientY); })
  .on('mouseleave', function(event, d) {
    if (focusedId === null && focusedLink === null)
      d3.select(this).attr('stroke-width', 2).attr('stroke-opacity', 0.5);
    hideTip();
  })
  .on('click', function(event, d) {
    event.stopPropagation();
    resetFocus();
    showGhost(d.data);
  });

// ── Draw relationship strings ─────────────────────────────────────────────────
var relPaths = linkLayer.selectAll('.rl')
  .data(simLinks).join('line').attr('class', 'rl')
  .attr('stroke',         function(d) { return d.data.color; })
  .attr('stroke-width',   function(d) { return strokeW(d.data.ev); })
  .attr('stroke-opacity', function(d) { return strokeO(d.data.ev); })
  .style('cursor', 'pointer')
  .on('mouseenter', function(event, d) {
    if (focusedId === null && focusedLink === null)
      d3.select(this).attr('stroke-width', strokeW(d.data.ev) + 3).attr('stroke-opacity', 1);
    showTip(
      '<strong>' + d.data.sub + '</strong><br>' +
      d.data.ents.join(' and ') + '<br>Evidence: ' + d.data.ev + ' of ' + MEV,
      event.clientX, event.clientY
    );
  })
  .on('mousemove', function(event) { showTip(tip.innerHTML, event.clientX, event.clientY); })
  .on('mouseleave', function(event, d) {
    if (focusedId === null && focusedLink === null)
      d3.select(this).attr('stroke-width', strokeW(d.data.ev)).attr('stroke-opacity', strokeO(d.data.ev));
    hideTip();
  })
  .on('click', function(event, d) {
    event.stopPropagation();
    focusOnLink(d.data);
    showRel(d.data);
  });

// ── Drop shadow filter for cards ──────────────────────────────────────────────
var defs = svg.append('defs');
var flt  = defs.append('filter').attr('id', 'sh')
  .attr('x', '-20%').attr('y', '-20%').attr('width', '140%').attr('height', '140%');
flt.append('feDropShadow')
  .attr('dx', '0').attr('dy', '1.5').attr('stdDeviation', '2.5')
  .attr('flood-color', '#00000020');

// ── Draw entity cards ─────────────────────────────────────────────────────────
var cards = cardLayer.selectAll('.ec')
  .data(simNodes).join('g').attr('class', 'ec')
  .style('cursor', 'pointer')
  .on('mouseenter', function(event, d) {
    d3.select(this).select('.card-body')
      .attr('stroke-width', d.conflict ? 3 : 1.5);
    showTip(
      '<strong>' + d.label + '</strong><br>' + d.sub +
      (d.conflict ? ' <span style="color:#ffb3b0;">\u26A0 conflict entity</span>' : ''),
      event.clientX, event.clientY
    );
  })
  .on('mousemove', function(event) { showTip(tip.innerHTML, event.clientX, event.clientY); })
  .on('mouseleave', function(event, d) {
    d3.select(this).select('.card-body').attr('stroke-width', d.conflict ? 2 : 0.5);
    hideTip();
  })
  .on('click', function(event, d) {
    event.stopPropagation();
    // Toggle focus: click same card again to reset
    if (focusedId === d.id) {
      resetFocus();
      clearPanel();
    } else {
      focusOnEntity(d.id);
      showEnt(d);
    }
  })
  // Drag: reheat simulation while dragging, freeze position on drag end
  .call(d3.drag()
    .on('start', function(event, d) {
      if (!event.active) sim.alphaTarget(0.3).restart();
      d.fx = d.x; d.fy = d.y;
      hideTip();
    })
    .on('drag', function(event, d) {
      d.fx = event.x; d.fy = event.y;
    })
    .on('end', function(event, d) {
      if (!event.active) sim.alphaTarget(0);
      d.fx = null; d.fy = null;
    })
  );

// Card white background rectangle
cards.append('rect').attr('class', 'card-body')
  .attr('width', CW).attr('height', CH).attr('rx', 8)
  .attr('x', -CW / 2).attr('y', -CH / 2)
  .attr('fill', '#ffffff')
  .attr('filter', 'url(#sh)')
  .attr('stroke',       function(d) { return d.conflict ? '#E24B4A' : '#d3d1c7'; })
  .attr('stroke-width', function(d) { return d.conflict ? 2 : 0.5; });

// Coloured header band (top strip showing entity subtype colour)
cards.append('rect')
  .attr('width', CW).attr('height', HH).attr('rx', 8)
  .attr('x', -CW / 2).attr('y', -CH / 2)
  .attr('fill', function(d) { return d.hcolor; });
// Fill bottom half of header (removes rounded bottom corners from top rect)
cards.append('rect')
  .attr('width', CW).attr('height', HH / 2)
  .attr('x', -CW / 2).attr('y', -CH / 2 + HH / 2)
  .attr('fill', function(d) { return d.hcolor; });

// Entity name in white text on coloured header
cards.append('text')
  .attr('y', -CH / 2 + HH / 2)
  .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
  .attr('font-size', '10.5').attr('font-weight', '600').attr('fill', 'white')
  .attr('font-family', 'system-ui, sans-serif')
  .text(function(d) { return trunc(d.label, 16); });

// Subtype label below header
cards.append('text')
  .attr('y', -CH / 2 + HH + 12)
  .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
  .attr('font-size', '10').attr('fill', '#888780')
  .attr('font-family', 'system-ui, sans-serif')
  .text(function(d) { return d.sub; });

// Relationship types or conflict warning in bottom row
cards.append('text')
  .attr('y', -CH / 2 + HH + 27)
  .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
  .attr('font-size', '9.5')
  .attr('font-weight', function(d) { return d.conflict ? '600' : '400'; })
  .attr('fill',        function(d) { return d.conflict ? '#E24B4A' : '#888780'; })
  .attr('font-family', 'system-ui, sans-serif')
  .text(function(d) {
    return d.conflict
      ? '\u26A0 conflict'
      : trunc(d.types.slice(0, 2).join(', ') || '\u2014', 22);
  });

// Red circle badge in top-right corner for conflict entities
cards.filter(function(d) { return d.conflict; })
  .append('circle')
  .attr('cx', CW / 2 - 8).attr('cy', -CH / 2 + 8).attr('r', 5)
  .attr('fill', '#E24B4A');

// ── Zoom control buttons ──────────────────────────────────────────────────────
d3.select('#btn-in').on('click',
  function() { svg.transition().duration(300).call(zoomBehaviour.scaleBy, 1.4); });
d3.select('#btn-out').on('click',
  function() { svg.transition().duration(300).call(zoomBehaviour.scaleBy, 0.7); });
d3.select('#btn-fit').on('click',
  function() { svg.transition().duration(500).call(zoomBehaviour.transform, d3.zoomIdentity); });

// ── Click on blank board area resets focus ────────────────────────────────────
svg.on('click', function() {
  resetFocus();
  clearPanel();
});

// ── Simulation tick: update positions on every physics step ──────────────────
sim.on('tick', function() {
  // Update relationship string endpoints
  relPaths
    .attr('x1', function(d) { return d.source.x; })
    .attr('y1', function(d) { return d.source.y; })
    .attr('x2', function(d) { return d.target.x; })
    .attr('y2', function(d) { return d.target.y; });

  // Update ghost string endpoints (looked up from nodeById map)
  ghostPaths
    .attr('x1', function(d) {
      var s = typeof d.source === 'object' ? d.source : nodeById[d.source];
      return s ? s.x : 0;
    })
    .attr('y1', function(d) {
      var s = typeof d.source === 'object' ? d.source : nodeById[d.source];
      return s ? s.y : 0;
    })
    .attr('x2', function(d) {
      var t = typeof d.target === 'object' ? d.target : nodeById[d.target];
      return t ? t.x : 0;
    })
    .attr('y2', function(d) {
      var t = typeof d.target === 'object' ? d.target : nodeById[d.target];
      return t ? t.y : 0;
    });

  // Translate each entity card to its simulated position
  cards.attr('transform', function(d) {
    return 'translate(' + d.x + ',' + d.y + ')';
  });
});
"""

    # ── HTML document ─────────────────────────────────────────────────────────
    # Written as a plain string with PLACEHOLDER tokens replaced after.
    # This avoids all Python f-string escaping issues with CSS and JS braces.
    _html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
/* Base reset and full-height layout */
html, body {
  margin: 0; padding: 0; overflow: hidden;
  width: 100%; height: 100%;
  font-family: system-ui, -apple-system, sans-serif;
  background: #f1efe8;
}
/* Outer wrapper fills viewport height */
#wrap { display: flex; flex-direction: column; height: 100vh; }

/* Top header bar */
#hdr {
  display: flex; align-items: center; justify-content: space-between;
  padding: 7px 16px; background: #f8f7f4;
  border-bottom: 1px solid #d3d1c7;
  flex-shrink: 0; flex-wrap: wrap; gap: 6px; z-index: 10;
}
#hdr-t { font-size: 13px; font-weight: 600; color: #1a1a18; }
#hdr-s { font-size: 10px; color: #73726c; display: flex; gap: 14px; flex-wrap: wrap; }
#hdr-btns { display: flex; gap: 4px; }
.zb {
  padding: 3px 10px; border-radius: 4px;
  border: 1px solid #d3d1c7; background: #fff;
  font-size: 11px; cursor: pointer; color: #3d3d3a;
}
.zb:hover { background: #f1efe8; }

/* Main content area: board + side panel */
#main { display: flex; flex: 1; min-height: 0; }

/* SVG canvas fills remaining width */
#canvas { flex: 1; min-width: 0; overflow: hidden; }
#svg { display: block; cursor: grab; width: 100%; height: 100%; }
#svg:active { cursor: grabbing; }

/* Floating tooltip */
#tip {
  position: fixed; display: none;
  background: rgba(26, 26, 24, 0.88); color: #fff;
  padding: 6px 10px; border-radius: 6px;
  font-size: 11px; pointer-events: none;
  max-width: 240px; line-height: 1.5; z-index: 999;
}

/* Evidence detail panel */
#panel {
  width: 264px; min-width: 264px;
  border-left: 1px solid #d3d1c7;
  background: #fff; display: flex;
  flex-direction: column; overflow: hidden;
}
#ph {
  padding: 9px 13px; font-size: 11px; font-weight: 600; color: #534AB7;
  background: #EEEDFE; border-bottom: 1px solid #AFA9EC; flex-shrink: 0;
}
#pb { padding: 11px 13px; flex: 1; overflow-y: auto; }
.pp { font-size: 11px; color: #888780; line-height: 1.7; padding: 16px 0; text-align: center; }

/* Legend bar at bottom */
#leg {
  display: flex; gap: 10px; padding: 6px 16px;
  background: #f8f7f4; border-top: 1px solid #d3d1c7;
  flex-wrap: wrap; align-items: center; flex-shrink: 0;
}
.li { display: flex; align-items: center; gap: 4px; font-size: 9px; color: #73726c; }
.ll { display: inline-block; width: 20px; height: 3px; border-radius: 2px; }
.ln { font-size: 9px; color: #b4b2a9; margin-left: auto; }
</style>
</head>
<body>
<div id="wrap">

  <!-- Header: title, stats, zoom controls -->
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
      <button class="zb" id="btn-fit">Reset view</button>
    </div>
  </div>

  <!-- Board and evidence panel side by side -->
  <div id="main">
    <div id="canvas">
      <svg id="svg"></svg>
      <div id="tip"></div>
    </div>
    <div id="panel">
      <div id="ph">Evidence detail</div>
      <div id="pb">
        <p class="pp">Click any string to see its evidence chain.<br>Click any entity card to see its connections.<br>Click background to reset.</p>
      </div>
    </div>
  </div>

  <!-- Legend -->
  <div id="leg">
    <div class="li"><span class="ll" style="background:#E24B4A;height:4px"></span>Suspicious</div>
    <div class="li"><span class="ll" style="background:#1D9E75"></span>Colleagues / Friends</div>
    <div class="li"><span class="ll" style="background:#534AB7;height:2.5px"></span>Operates</div>
    <div class="li"><span class="ll" style="background:#BA7517;height:2px"></span>AccessPermission</div>
    <div class="li"><span class="ll" style="background:#185FA5;height:2px"></span>Coordinates</div>
    <div class="li">
      <svg width="22" height="5">
        <line x1="0" y1="2.5" x2="22" y2="2.5" stroke="#888780" stroke-width="2" stroke-dasharray="5,4"/>
      </svg>
      Predicted missing
    </div>
    <span class="ln">Drag cards &middot; Scroll to zoom &middot; Click card or string to focus &middot; Click again to reset</span>
  </div>

</div>

<script>
JS_DATA
JS_CODE
</script>
</body>
</html>"""

    # Replace placeholder tokens with actual data and code
    _html = _html.replace("ENTITY_COUNT",   str(len(_ve)))
    _html = _html.replace("REL_COUNT",      str(len(_vr)))
    _html = _html.replace("CONFLICT_COUNT", str(_nc))
    _html = _html.replace("GHOST_COUNT",    str(len(_vg)))
    _html = _html.replace("JS_DATA",        _js_data)
    _html = _html.replace("JS_CODE",        _js_code)

    _board    = mo.iframe(_html, height="720px")
    _controls = mo.hstack(
        [threshold, etype_filter, rtype_filter, ghost_toggle, conflict_only],
        gap=2, wrap=True,
    )
    mo.vstack([_controls, _board])
