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
- attaches `tmux` and renders it in a phone-width terminal;
- (later) shows four panes — touch to switch, drag to scroll — with **speech**
  to enter prompts into the active pane.

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
| SSH session logic (framing, `tmux -CC` parse, resize) | **loft** | new library in this repo |
| SSH transport | **Rust `russh` via loft FFI** | password auth; the "rust lib" |

`tmux -CC` (control mode) is the mechanism for the four-pane UX: each pane is a
structured `%output` stream, so the client renders each as its own full-width
virtual screen and switches by touch — no attempt to squeeze four panes onto one
phone-width grid.

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
- Password is typed into the on-screen terminal (soft keyboard on Android).
- Host/port configurable; default port `42022`.

## 6. Staged plan

1. **Linux-native v1** — `lib/graphics` on-screen terminal, password SSH via the
   russh FFI lib, a single `tmux` pane. Runs `--native` on Linux; this proves the
   entire shared stack with zero Android risk.
2. **Panes + input** — `tmux -CC`, four virtual screens, touch-to-switch,
   drag-to-scroll.
3. **Speech** — recognized text injected as keystrokes into the active pane.
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
