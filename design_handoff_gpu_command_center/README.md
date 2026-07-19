# Handoff: Dual-GPU llama.cpp Command Center V 1.0

## Overview
A single-page web control center for running llama.cpp (`llama-server`) on two AMD GPUs in one Linux machine ("Orion", Ubuntu 24.04, ROCm, host IP `192.168.1.5`):

- **RX 7900 XT** — GPU 0, port **8081**, 20 GB VRAM
- **RX 6600** — GPU 1, port **8082**, 8 GB VRAM

The UI replaces two separate terminal TUI launchers (`~/Desktop/ROCm-TUI/run-rocm-tui.sh` and `~/Desktop/ROCm-TUI-RX6600/run-rx6600-tui.sh`, both driving `rocm_tui.py` in a shared `.venv`). One browser page manages both cards: browse a GGUF model library, assign a model to either card, check VRAM fit, set launch parameters, launch/stop each server, and watch live telemetry and logs.

## About the Design Files
The file in this bundle (`GPU Command Center.dc.html`) is a **design reference created in HTML** — an interactive prototype showing intended look and behavior with **simulated** data. It is not production code to copy directly. The task is to **recreate this design as a real application**: a small Python backend (FastAPI/Flask recommended — the machine already runs Python + a venv) serving this exact frontend, with real process management, filesystem scanning, and `amd-smi` telemetry. No auth is required (trusted LAN). Dark theme only.

## Fidelity
**High-fidelity.** Recreate the UI pixel-perfectly: colors, typography, spacing, and interactions below are final. The design intentionally uses **zero border-radius, zero shadows** — structure comes from 1px hairlines and flat fills.

## Layout

Full-viewport column: header (64px) → optional settings drawer → main 3-column grid → footer.

Main grid: `grid-template-columns: <libWidth>px 1fr 1fr` where `libWidth` is **user-resizable by dragging the library's right edge** (min 240px, max 640px, default 340px; persist it, e.g. localStorage). All three columns scroll independently (`min-width:0; min-height:0; overflow-y:auto` on the scrolling regions).

### Header (nav)
- 64px tall, `padding: 0 32px`, 1px bottom rule `#2a2d32`, not fixed.
- Left: wordmark `SPARK.Ai` (Inter Tight 600, 20px; the period is amber `#E39A2B`) + mono label `LLAMA.CPP COMMAND CENTER V 1.0 — ORION` (JetBrains Mono 13px, uppercase, letter-spacing 0.08em, `#c7cad0`).
- Right: mono label `ROCM 6.4 · 192.168.1.5` + **Model Database** button (outlined amber rectangle: 1px `#E39A2B` border, amber text, mono 13px uppercase, padding 10px 16px, small 15px stroke "sliders" icon before label; hover inverts to solid amber bg with `#0E0F11` text).

### Settings drawer (Model Database)
Toggled by the header button. A row under the header, bg `#17191C`, 1px bottom rule, `padding: 22px 32px`, flex with 24px gaps:
- Text input for **model database location** (default `/media/mikem/WorkDrive_A/Models`), mono 15px, dark input (`#0E0F11` bg, `#2a2d32` border).
- Live counts: `N GGUF FOUND` / `N GB ON DISK` (mono 13px uppercase).
- **Rescan** button (amber outline; label becomes "Scanning…" while a scan runs) and **Close** button (gray outline).

Backend: rescanning runs `MODEL_DIR.rglob("*.gguf")`, reading file size and (ideally) GGUF metadata for quant + param count.

### Column 1 — Model Library (left rail)
- Header block: amber mono section label `§ 01 — MODEL LIBRARY` + filter input (substring match, mono 14px).
- Scrollable list of model rows. Each row (`padding: 14px 22px`, bottom rule `#ffffff14`, pointer cursor, hover bg `#17191C`):
  - Top line: two-digit index `01` (mono 13px `#c7cad0`) left; right side has file size `42.5 GB` (mono 13px, weight 600 — **amber `#E39A2B` when > 20 GB**, else `#c7cad0`) and a **red trash icon** (16px stroke trash-can SVG, stroke 1.6, color `#e05252`, hover `#ff6b6b`).
  - Model filename, e.g. `Llama-3.3-70B-Instruct.Q4_K_M.gguf` (Inter 15.5px, weight 600, line-height 1.4, word-break).
  - Meta line: `Q4_K_M · 70B` (mono 12.5px uppercase `#c7cad0`); when the model is running on a card, append amber `● RX 7900 XT`.
  - **Selected state**: bg `#17191C` + `inset 3px 0 0 #E39A2B` left bar. Click toggles selection.
  - **Trash flow**: clicking the trash icon shows an inline confirm strip inside the row (1px `#e05252` border, "Move to trash?" 14px + solid-red **Trash** button + outlined **Keep** button). Confirming moves the file to the OS trash (`gio trash` on Ubuntu — never `rm`), removes the row, and clears it from any *stopped* card's slot.
- Footer strip: current model dir path, mono 12.5px uppercase, top rule.
- **Resize handle**: invisible 10px-wide strip on the rail's right edge, `cursor: col-resize`, hover tint `#e39a2b33`; drag adjusts library width 240–640px.

### Columns 2 & 3 — GPU panels (identical structure)
Panel 2 = RX 7900 XT (`§ 02 — PRIMARY`, 1px right rule); Panel 3 = RX 6600 (`§ 03 — SECONDARY`).

**Panel header** (`padding: 20px 26px 16px`, bottom rule):
- Row 1: amber mono section label; right: status `● RUNNING` (amber, 10px square dot with 2s blink animation) or `● STOPPED` (gray `#c7cad0`, dot `#2a2d32`). Squares, not circles.
- Row 2: H2 `RX 7900 XT.` (Inter Tight 30px, weight 500, letter-spacing -0.02em, **trailing amber period**); right: mono `GPU 0 · :8081 · 20 GB`.

**Panel body** (`padding: 22px 26px`, vertical stack, 20px gaps, scrolls):

1. **Assigned-model slot** — card `#17191C`, 1px border (solid `#2a2d32` when filled; **dashed**, turning amber, when empty and a library model is selected — clicking assigns).
   - Empty state: centered "NO MODEL ASSIGNED" (mono 13px uppercase `#F2EFE6`) + 16px `#c7cad0` instruction line.
   - Filled: "ASSIGNED MODEL" mono label, filename (17px, 600), meta `Q4_K_M · 70B · 42.5 GB on disk` (mono 13px), and an outlined gray **Clear** button.
   - **VRAM fit estimate**: label row (`VRAM FIT ESTIMATE` + verdict `FITS` green `#7da77f` / `TIGHT FIT` amber / `WILL NOT FIT` red `#e05252`, mono 12.5px bold); 12px-tall bar (dark track, 1px border, flat colored fill = est/total %); detail line `44.4 GB est. (42.5 weights + 1.9 KV @ 8192 ctx)` vs total. Estimate = file size + KV cache scaled by context (prototype: `kv ≈ max(0.5, gb × 0.045) × ctx/8192`; production should compute from GGUF metadata).
   - Warning box (1px amber border, 18px warning-triangle stroke icon) when over budget ("Model + KV cache exceeds N GB VRAM. Reduce context, choose a smaller quant, or lower GPU layers to split with CPU.") or when < 15% headroom.
2. **Assign button** — full-width amber outline `ASSIGN SELECTED → RX 7900 XT`, shown only when a library model is selected, the card isn't running, and it isn't already assigned.
3. **Launch parameters card** — `#17191C`, mono label + **Profile** select (`Balanced` ctx 8192/threads 8/ngl 999/batch 512 · `Max Speed` 4096/12/999/1024 · `Long Context` 32768/8/999/256 · `Custom` auto-selected on any manual edit). 2×2 grid of labeled inputs: `CONTEXT (-C)`, `THREADS (-T)`, `GPU LAYERS (-NGL)`, `BATCH (-B)` (mono 15px values). Profiles should persist per card.
4. **Launch / Stop row** — main button: solid amber `▶ LAUNCH ON GPU 0 · :8081` when launchable (hover inverts to outline); disabled gray outline when no model or won't fit; outlined `■ STOP SERVER` while running (hover turns red `#e05252`). While running, a companion outlined link `:8081 ↗` opens `http://192.168.1.5:8081`.
5. **Telemetry card** — 1px border, label `TELEMETRY — AMD-SMI` + 10px status square. 4-column grid of stats: **Edge temp °C · VRAM used GB · Power W · Gen speed tok/s** (Inter Tight 27px values, mono 11.5px uppercase captions; gen speed value amber; temp turns amber > 75°C; em-dash values when stopped). Below, a GPU-load sparkline (amber 1.5px polyline over 1px top rule, last ~40 samples, 1s poll).
6. **Log panel** — bg `#0B0C0E`, 1px border, mono 13.5px, line-height 1.7, min-height 110px, last ~8 lines. Line colors: default `#c7cad0`, command/stop lines `#F2EFE6`, success lines amber. Prototype sequence to mirror: `[launch] llama-server --port 8081 -ngl 999 -c 8192` → `[env] ROCR_VISIBLE_DEVICES=0 HIP_VISIBLE_DEVICES=0` → `[load] <file>` → `[rocm] offloading layers to RX 7900 XT (gfx1100)` → `[ok] model loaded — listening on http://192.168.1.5:8081` → `[health] /health → 200 OK`. Production: stream real stdout/stderr.

### Footer
Single row, `padding: 14px 32px`, top rule, mono 12.5px uppercase `#c7cad0`:
left `ORION · UBUNTU 24.04 · ROCM 6.4 · LLAMA.CPP B4970`, right `MIKE MILLER · MIKE@SPARKAI805.COM · SPARKAI805.COM`.

## Interactions & Behavior
- Select model (library) → both GPU panels show an Assign button; assign via button or by clicking the dashed slot.
- Clear slot: stops nothing (button only shown; assignment locked while running — inputs/assign disabled when `running`).
- Launch: disabled unless a model is assigned **and** the fit estimate is within VRAM. On launch set `ROCR_VISIBLE_DEVICES` / `HIP_VISIBLE_DEVICES` to the card's index and start `llama-server` on the card's port. Stop sends SIGTERM.
- Telemetry polls every 1s (`amd-smi` / sysfs) only for running cards.
- Transitions: minimal, ~150ms ease color changes only. The single blink animation is the running status dot (2s opacity pulse). No bounces, no parallax.
- Hover convention: outlined amber buttons invert to solid amber; gray outlines brighten to bone.
- Responsive: desktop/laptop only. Panels must tolerate ~300px widths (all grids need `min-width:0`); no mobile layout required.

## State Management
Per app: `modelDir`, `models[]` (id, filename, quant, params, sizeGb), `filter`, `selectedModelId`, `libWidth`, `trashed[]`, `confirmTrashId`, `settingsOpen`.
Per GPU (×2): `model`, `running`, `profile`, `params {ctx, threads, layers, batch}`, `log[]`, `loadHistory[]`, telemetry snapshot.
Suggested API: `GET /api/models`, `POST /api/rescan`, `POST /api/models/trash`, `POST /api/gpu/{i}/launch`, `POST /api/gpu/{i}/stop`, `GET /api/gpu/{i}/telemetry`, WebSocket or SSE for logs.

## Design Tokens (Spark Ai — dark theme)
- Colors: bg `#0E0F11` · card `#17191C` · log bg `#0B0C0E` · ink `#F2EFE6` · muted-strong `#c7cad0` · muted `#8a8d92` · rule `#2a2d32` · soft rule `#ffffff14` · **amber accent `#E39A2B`** · danger red `#e05252` (hover `#ff6b6b`) · fit-ok green `#7da77f`.
- Type: **Inter Tight** (display: H2 30px/500, telemetry 27px/500, letter-spacing -0.02em) · **Inter** (body 14–17px) · **JetBrains Mono** (all labels/meta/inputs/logs, 11.5–15px, labels UPPERCASE with 0.04–0.08em tracking). Google Fonts, weights 400–700.
- Radius: **0 everywhere**. Shadows: **none**. Depth = hairlines + flat fills only.
- Spacing: header 64px; column padding 22–26px; card padding 16–20px; stack gaps 20px; grid gaps 12–16px.
- Brand rules: "Ai" is always written `Ai`; headings take a trailing **amber period**; status marks are squares; `§ NN —` section labels; `·` separators; **no emoji**.

## Assets
No raster assets. All icons are inline stroke SVGs (24×24 viewBox, stroke 1.6, round caps/joins): sliders (Model Database), trash can, warning triangle. Fonts from Google Fonts.

## Screenshots
- `screenshots/01-idle-both-stopped.png` — default state, both servers stopped
- `screenshots/02-model-selected.png` — library model selected, assign buttons visible
- `screenshots/03-running-telemetry.png` — model launched on RX 7900 XT with live telemetry, sparkline, and logs

## Files
- `GPU Command Center.dc.html` — the full interactive prototype (markup + simulated logic). The `<x-dc>` template section contains all layout/styles inline; the `Component` class contains the simulated behavior to replace with real API calls. The 20-model library inside it is sample data — the real list comes from scanning the model directory.
