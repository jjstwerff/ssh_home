<!-- Copyright (c) 2026 Jurjen Stellingwerff  SPDX-License-Identifier: LGPL-3.0-or-later -->

# DESIGN — ssh_home

A pure-loft, native terminal that logs into a home laptop over SSH and drives
`tmux` from a phone-width screen. This document records the architecture and the
staged plan so the rationale survives across machines.

## 1. Goal

One installable native app that:

- connects to the laptop's `sshd` (default port `42022`, configurable) — the
  **only** service the laptop needs to expose;
- authenticates with a **password**, typed each session, **never stored**;
- on connect, **auto-runs a configurable startup command** — default
  `tmux attach`, so you land straight in the latest/last-used tmux session with
  nothing to type — and renders tmux (with **mouse mode on**) faithfully in a
  phone-width terminal;
- lets **tmux own selection and scroll**: a tap forwards as a mouse click (tmux
  selects that pane/window) and a drag/flick forwards as scroll (tmux copy-mode /
  scrollback) — fully tmux-compatible, nothing reimplemented client-side;
- supports **two-finger pinch zoom** to resize text on demand, starting from a
  readable **DPI-aware default** (phone screens are hard to read). Zoom is a real
  terminal resize: each step re-derives cols×rows and sends a PTY window-change,
  so tmux reflows — bigger text simply means fewer columns;
- takes **commands by speech**, injected as keystrokes into the currently
  selected tmux pane/window. The on-screen keyboard is used only for the one-time
  password (§5) — never for command entry.

## 2. Why pure-native (not a web page)

A browser cannot open a raw TCP/SSH socket — it speaks only HTTP / WebSocket /
WebRTC / WebTransport, none of which `sshd` understands. A pure-web client would
therefore need an extra bridge process somewhere. The chosen answer avoids that
entirely: a **native app that opens the SSH socket itself**, so nothing new runs
on the laptop and there is no relay in the middle.

## 3. Architecture

```
┌─ device (Linux desktop today; Android later) ─┐        ┌─ laptop ───────┐
│  loft app  (pure loft)                        │        │                │
│    terminal grid, panes, touch/scroll, speech │        │  sshd :42022   │
│        │  gl_* draw + gl_load_font            │        │      │         │
│    lib/graphics  (GL: glutin/winit/gl/fontdue)│  SSH   │      ▼         │
│        │                                      │ (pw    │ pty + tmux -CC │
│    ssh loft lib  ── russh FFI ───────────────────auth)─▶                │
└───────────────────────────────────────────────┘        └────────────────┘
```

| Layer | Language | Notes |
|---|---|---|
| Terminal UI (grid render, panes, touch, scroll, speech) | **loft** | draws through `gl_*` + `gl_load_font` |
| GL / windowing / font | **loft `lib/graphics`** | existing; native backend = glutin + winit + gl + fontdue |
| Terminal emulator + SSH session (VT parse, mouse-event forwarding, resize) | **loft** | new library in this repo |
| SSH transport | **Rust `russh` via loft FFI** | password auth; the "rust lib" |

The four-part UX is **tmux's own**, not reimplemented. The app is a faithful VT
emulator that renders tmux's screen with tmux `mouse on`, and forwards input to
tmux: a **tap becomes an SGR mouse click** (tmux selects that pane/window) and a
**drag/flick becomes scroll** (tmux enters copy-mode and scrolls history). So
click-to-select and scrollback behave exactly as tmux does at a desktop — the
goal the maintainer set. Using tmux **windows** (full-width, one visible, tap the
status line to switch) keeps each part phone-width instead of tiling four tiny
panes. On connect the app auto-runs the startup command (default `tmux attach`),
so the latest session is already selected. (`tmux -CC` control mode stays a
fallback if native mouse tiling proves too cramped.)

**Scope consequence:** the app therefore carries **no tmux-specific code** — it is
a generic SSH terminal emulator. tmux (or vim, htop, anything mouse-aware) works
because the emulator honors the standard mouse-tracking modes the remote enables
(DECSET `1000`/`1002`/`1006`) and emits SGR mouse events back, and resizes the PTY
on layout change — all ordinary terminal behavior. The only tmux-shaped thing in
the app is the default startup string (`tmux attach`), a configurable value, not
logic. So the bulk of v1 is a **correct-enough VT emulator** (ANSI parser + a cell
grid via `gl_load_font`); SSH and input forwarding are thin layers around it.

## 4. What loft already gives us

loft's `lib/graphics` **is** the GL abstraction this needs, and it already runs
natively: one loft-facing surface (`gl_create_window`, `gl_draw`, `gl_swap_buffers`,
`gl_poll_events`, `gl_load_font`, `gl_measure_text`, ...) with three backends —
`--html` (WebGL2) and `--native` (desktop GL via glutin/winit/gl, glyphs via
fontdue). So a pure-loft terminal written once against that surface runs on Linux
today and in a browser via `--html`, unchanged.

## 5. Authentication & security

- **Password auth only** in v1 (`russh` password method). No pubkey, no agent.
- **No private key or password persisted** — the password lives in memory only
  for the handshake, is never written to disk/logs, and is re-entered each session.
- Password is typed into the on-screen terminal (soft keyboard on Android). The
  on-screen keyboard is used **only** for the password — never for commands (those
  are spoken; a password must never be spoken).
- Configurable, with these defaults: host, port `42022`, the on-connect
  **startup command** `tmux attach` (selects the latest session), and a readable
  **DPI-aware default text size** (pinch to zoom from there).

## 6. Staged plan

1. **Linux-native v1** — `lib/graphics` terminal (faithful VT), password SSH via
   the russh FFI lib, auto-run `tmux attach` on connect. Runs `--native` on Linux;
   proves the whole shared stack with zero Android risk.
2. **tmux mouse forwarding** — tap → SGR mouse click (select pane/window),
   drag/flick → scroll (tmux copy-mode). Selection + scrollback are tmux-native.
3. **Speech input** — recognized text injected as keystrokes into the selected
   tmux pane/window. (On the Linux build, mouse/keyboard stand in for touch/speech
   while iterating.)
4. **Android re-target** — the same source, with the two gaps below closed.

## 7. Android gaps (separable; both on loft's roadmap)

1. **loft Android build target.** loft today targets host-`--native`, `--html`,
   `--native-wasm`, `wasi` — no `aarch64-linux-android`. Cross-compiling `--native`
   to the NDK and packaging as a JNI `.so` in a `NativeActivity`/GameActivity APK
   is a **loft toolchain feature** → file as a `loft-lang/loft` issue. Gates
   everything Android.
2. **`lib/graphics` Android backend.** Desktop uses glutin+winit on X11/Wayland;
   Android uses **EGL on `ANativeWindow`** via `android-activity`. Same `gl_*`
   surface, GLES-3.0 subset. Because the stack is already winit-based, this is a
   port, not a rewrite.

## 8. Honest "not fully pure" leaks on Android

- **Speech** — Android's `SpeechRecognizer` is a Java API. Pure options: bundle a
  Rust speech model (e.g. whisper.cpp via FFI — same on Linux and Android, no Java,
  but heavy), or accept a thin JNI shim. Undecided.
- **Soft-keyboard / IME** text input is the fiddly Android-native corner
  (`android-activity` exposes it). No Linux analog.

## 9. Open decision (defer until Linux v1 exists)

Whether the Android GL backend rides **raw `gl_*`** (available today) or aligns
with loft's **`GFX.PORTABLE` + wgpu** roadmap (maintainer-blessed route to native
Android/iOS, but further out). Only matters once the Linux app is proven.
