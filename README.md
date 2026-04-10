# EvidenceBoard
### A Detective's Interface for Knowledge Graph Visual Analytics

**AmanDeep Singh · Utrecht University · Design Challenge · April 2026**

---

## Overview

EvidenceBoard is a fully functional visual analytics system built on the metaphor of the detective's evidence board. It enables a domain-expert analyst with no graph theory background to investigate a knowledge graph by discovering relationships, detecting anomalies, and inferring missing connections all within a single coherent workflow.

The system is implemented as a Marimo reactive Python application rendering three coordinated D3.js v7 views inside HTML iframes. It was designed and built as the individual submission for the VAST 2025 Design Challenge at Utrecht University.

---

## Key Features

**Ghost link detection.** Entity pairs with five or more direct communications but no corresponding Relationship node are identified computationally and rendered as dashed grey strokes. This treats edge absence as a first-class visual signal rather than ignoring it.

**Conflict entity detection.** Entities simultaneously holding Suspicious and Colleagues or Friends relationships are identified via set intersection and marked with a red border and dot badge across all three views.

**Auto-surfaced entry point.** On first load, the highest-risk entity is surfaced automatically in the evidence panel, responding directly to Li et al. (2024) who found that practitioners prefer seeded entry points over blank graph overviews.

**Three coordinated views.**
- Tab 1: Force-directed entity-relationship graph with focus mode, progressive disclosure, evidence chain panel, and investigation queue.
- Tab 2: Communication timeline heatmap with two-colour cross-highlight and hour-of-day histogram.
- Tab 3: Suspicion analysis with ranked bar chart, 14-day sparklines, and risk matrix scatter plot.

**Investigation queue.** Analysts flag relationships for follow-up. Flagged items persist across all filter and navigation changes.

---

## Repository Structure

```
EvidenceBoard/
│
├── app_final.py              # Main Marimo application (submit this file)
│
├── data/
│   ├── MC3_graph.json              # MC3 knowledge graph (1,159 nodes, 3,226 edges)
│   ├── MC3_schema.json             # Graph schema definition
│   └── MC3_data_description.pdf    # Official dataset documentation
│
├── mock_up_design/
│   ├── V0_Adjacency_Matrix.png             # Rejected design candidate
│   ├── V1_Hierarchical_Edge_Bundling.png   # Rejected design candidate
│   ├── V2_Bare_Force_Graph.png             # Rejected design candidate
│   └── V3_EvidenceBoard.png                # Selected final design wireframe
│
├── app_old_version/          # Full iterative development history (app_0 through app17_final)
│
├── Report.pdf                # Final Medium-style blog report
└── README.md
```

---

## Getting Started

### Requirements

- Python 3
- Marimo v0.22.4
- No additional Python packages required beyond Marimo

### Installation

```bash
pip install marimo==0.22.4
```

### Running the Application

```bash
marimo run app_final.py
```

The interface will open in your browser. **Allow 30 to 60 seconds on first load.** This is expected behaviour: Marimo executes the full data processing pipeline on startup, traversing all 3,226 edges and computing conflict entities, ghost links, and sparkline statistics before the interface renders. D3.js v7 additionally loads from the public CDN on first render of each tab. Subsequent interactions are immediate.

### File Structure Requirement

The `data/` folder must be in the same directory as `app_final.py`. The application loads `data/MC3_graph.json` on startup.

---

## Implementation Details

The application is structured in four reactive Marimo cells.

**Cell 1** imports Marimo.

**Cell 2** performs all data loading and Python computation: MC3 graph JSON traversal, entity and relationship extraction via type filtering, conflict entity detection via set intersection across relationship subtype sets per entity, ghost link identification by communication frequency thresholding at five communications per entity pair, sparkline statistics, and sender and receiver lookups for all 3,226 edges.

**Cell 3** creates the Marimo UI controls: minimum evidence slider, entity type dropdown, relationship type dropdown, ghost links toggle, and conflicts-only toggle.

**Cell 4** is the main reactive cell. It receives all controls and computed data, filters entities and relationships, serialises filtered data to JavaScript variables, and assembles three complete HTML iframe documents injected with D3.js v7 dynamically loaded from the public CDN.

### D3.js Rendering

- **Tab 1** uses forceSimulation with forceLink (link distance inversely scaled by evidence count), forceManyBody (charge repulsion at minus 300), forceCenter, and forceCollide (collision radius matching card dimensions), plus d3.zoom and d3.drag.
- **Tab 2** uses scaleSequential with a custom luminance interpolator from off-white to dark teal.
- **Tab 3** uses scaleLinear for the ranked bar chart and scatter plot, with zoom transform rescaling both axes on each zoom event.

### Key Technical Notes for Developers

- `mo.Html()` does **not** execute JavaScript. All D3 rendering uses `mo.iframe()` with complete `<!DOCTYPE html>` documents.
- D3 must be loaded as a **blocking script in `<head>`**, not dynamically, to prevent render race conditions.
- `mo.iframe()` requires height as a **string** (e.g., `"720px"`), not an integer.
- Marimo prohibits accessing `.value` of a UI element in the same cell that created it.
- All local variables inside cells must be prefixed with `_` to avoid cross-cell name conflicts.
- JavaScript inside Python f-strings requires `{{ }}` for literal braces.

---

## Design Process

Four design candidates were evaluated. Three were rejected on principled grounds before arriving at the final design.

| Version | Design | Rejection Reason |
|---|---|---|
| V0 | Adjacency Matrix | Munzner (2009) Level 2 task misalignment. Supports Lookup and Compare only. No evidence chain access. |
| V1 | Hierarchical Edge Bundling | Destroys per-edge uncertainty encoding required by MacEachren et al. (2012). Imposes artificial hierarchy. |
| V2 | Bare Force Graph | Sedlmair et al. (2012) pitfall PF-32: premature end. Displays data but does not support investigation as a workflow. |
| V3 | EvidenceBoard | **Selected.** Addresses every specific failure of V0 through V2. |

Mockup images for all four candidates are in the `mock_up_design/` folder.

---

## Dataset

The MC3 knowledge graph describes a fictional coastal investigation set in Oceanus, October 2040.

| Property | Value |
|---|---|
| Total nodes | 1,159 |
| Total edges | 3,226 |
| Entity nodes (filtered) | 44 |
| Relationship subtypes | 8 |
| Communication nodes | 584 |
| Investigation window | October 1 to 14, 2040 |
| Conflict entities detected | 18 |
| Ghost links detected | 3 |

---

## Limitations

- The D3 force simulation degrades above approximately 150 entities. A production deployment would require server-side layout computation.
- Ghost link detection uses a heuristic threshold of five communications. A production system would use probabilistic link prediction.
- The interface requires a pointer device and a minimum screen width of approximately 1,280 pixels. It is not optimised for mobile or touch environments.
- The investigation queue is local to a single browser session. Multi-analyst collaboration would require a shared backend.

---

## References

Bludau et al. (2023). https://doi.org/10.1111/cgf.14831

Brehmer and Munzner (2013). https://doi.org/10.1109/TVCG.2013.124

Li et al. (2024). https://doi.org/10.1109/TVCG.2023.3326904

MacEachren et al. (2012). https://doi.org/10.1109/TVCG.2012.252

Munzner (2009). https://doi.org/10.1109/TVCG.2009.111

Sedlmair, Meyer, and Munzner (2012). https://doi.org/10.1109/TVCG.2012.213

Shneiderman (1996). https://doi.org/10.1109/VL.1996.545307

Stasko, Görg, and Liu (2007). https://doi.org/10.1109/VAST.2007.4389006

Ware (2004). https://www.sciencedirect.com/book/9781558608191/information-visualization

---

*EvidenceBoard was built with Marimo v0.22.4, D3.js v7.8.5, and Python 3.*
