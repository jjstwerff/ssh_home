<!-- Copyright (c) 2026 Jurjen Stellingwerff  SPDX-License-Identifier: LGPL-3.0-or-later -->

# Gap 01 — an ordered input-event queue for `lib/graphics`

**Proposal to `loft-lang/loft` (lib/graphics).** Additive; the existing polling API
stays.

## Problem

`lib/graphics` input is game-style **polling**:

- `gl_key_pressed(keycode)` — is-key-down over a 0–255 index. `key_index`
  (`native/src/lib.rs`) lowercases characters and maps a handful of named keys
  (arrows 128–131, Shift/Ctrl 132/133, F1–F12 135–146); everything else → `None`.
- `gl_mouse_x/y`, `gl_mouse_button`, `gl_mouse_wheel`.
- wasm (`loft-gl.js`) mirrors this, and per `@PLN18` collapses **touch onto the
  single mouse** ("a tap = button 0").

This loses everything a text/terminal app needs, and the losses are the same on
both backends:

1. **No text / Unicode / IME.** Uppercase, accented, composed, and soft-keyboard
   (Android IME) characters are unrepresentable — only lowercased ASCII key *codes*.
2. **No key-repeat**, so held keys don't auto-repeat.
3. **No per-event modifiers** — you can poll `KEY_CTRL` but can't bind a discrete
   "Ctrl+C event" without race-prone frame sampling.
4. **Unmapped named keys** a terminal must send: Enter has no `KEY_*` constant
   (native emits `\r`=13 but there's no name), and Backspace, Delete, Insert,
   Home, End, PageUp, PageDown are dropped by `key_index` entirely.
5. **No multitouch** — pinch/two-finger gestures are impossible when touches fold
   into one mouse.

## Design: one ordered event queue, drained per frame

Add an **event queue** alongside the polling API (which keeps working, derived
from the same events). It follows the library's existing *poll-then-latched-read*
convention (as `ws_poll` + `ws_msg_*` accessors do):

```loft
// Advance to the next buffered input event and latch it.
// Returns its type tag, or EV_NONE (0) when the queue is drained.
pub fn gl_next_event() -> integer;      // #native "loft_gl_next_event"

// Event type tags:
EV_NONE = 0;
EV_KEY_DOWN = 1;   EV_KEY_UP = 2;   EV_TEXT = 3;
EV_MOUSE_DOWN = 4; EV_MOUSE_UP = 5; EV_MOUSE_MOVE = 6; EV_WHEEL = 7;
EV_TOUCH_BEGIN = 8; EV_TOUCH_MOVE = 9; EV_TOUCH_END = 10;
EV_RESIZE = 11;

// Typed accessors read the currently-latched event:
pub fn gl_event_key() -> integer;      // named/keycode (extended set below)
pub fn gl_event_mods() -> integer;     // bitmask: MOD_SHIFT|CTRL|ALT|SUPER
pub fn gl_event_repeat() -> boolean;   // key-repeat
pub fn gl_event_text() -> text;        // UTF-8 for EV_TEXT (1+ codepoints, IME)
pub fn gl_event_x() -> float;          // mouse/touch position (pixels)
pub fn gl_event_y() -> float;
pub fn gl_event_button() -> integer;   // 1=left 2=right 4=middle
pub fn gl_event_wheel() -> integer;    // wheel delta (EV_WHEEL)
pub fn gl_event_touch_id() -> integer; // stable id per finger (multitouch)

MOD_SHIFT = 1; MOD_CTRL = 2; MOD_ALT = 4; MOD_SUPER = 8;
```

Consumer loop:

```loft
gl_poll_events();
while (t = gl_next_event()) != EV_NONE {
  if t == EV_TEXT { feed_pty(gl_event_text()); }
  else if t == EV_KEY_DOWN { feed_pty(encode_key(gl_event_key(), gl_event_mods())); }
  else if t == EV_TOUCH_BEGIN || t == EV_TOUCH_MOVE || t == EV_TOUCH_END {
    gesture_on_touch(gl_event_touch_id(), t, gl_event_x(), gl_event_y());
  }
  // ...
}
```

**Extend the named-key set** (fill the reserved indices; keep existing numbers
stable so no consumer shifts): add `KEY_ENTER=13`, `KEY_BACKSPACE=8`,
`KEY_DELETE`, `KEY_INSERT`, `KEY_HOME`, `KEY_END`, `KEY_PAGEUP`, `KEY_PAGEDOWN`,
and mirror them in `key_index`.

### The one invariant

**Lossless, ordered, exactly-once:** each host input becomes exactly one queued
loft event, delivered in arrival order, and the queue drains to `EV_NONE` every
frame. Text is delivered as `EV_TEXT` (semantic characters, incl. IME commits);
`EV_KEY_DOWN`/`UP` carry named/non-text keys and modifiers. A key that produces
text yields **both** a key-down (for shortcut binding) and a text event (for
insertion) — mirroring winit's `KeyEvent{logical_key,text}` and the browser's
`keydown`+`input`.

## Backend mapping

- **native (winit, already in the loop):** buffer `WindowEvent::KeyboardInput`
  (`KeyEvent{logical_key, text, state, repeat}`) → key-down/up + optional text;
  `Ime(Commit(String))` → text; `ModifiersChanged` → mods; `MouseInput`,
  `CursorMoved`, `MouseWheel` → mouse; `Touch{phase,location,id}` → touch;
  `Resized` → resize. Enable IME with `window.set_ime_allowed(true)`. The polling
  state (`keys` set, `mouse*`) is updated from the same events (back-compat).
- **wasm (`loft-gl.js`):** add `input`/`compositionend` → `EV_TEXT`,
  `keydown`/`keyup` (with `e.key`, `e.getModifierState`) → key events, `wheel` →
  `EV_WHEEL`, and real `touchstart/move/end` via `changedTouches` → touch events
  (keep the existing touch→mouse mapping only for the legacy polling API).
- **Android (Gap 02):** `android-activity` key + IME events and `MotionEvent`
  pointers feed the same queue — so app code is identical across targets.

## Gestures (pure loft, on top — not a backend concern)

Tap/pan/pinch/swipe are a **deterministic function of the ordered touch stream**,
so they belong in portable loft, not in each backend. A small recognizer
(shippable as a tiny `gesture` lib, or vendored in the app) consumes `EV_TOUCH_*`:

- `Tap{x,y}` — down+up within space/time thresholds.
- `Pan{dx,dy}` — one active touch moving.
- `Pinch{scale,cx,cy}` — two touches; `scale = dist_now / dist_start`, centroid `(cx,cy)`.
- `Swipe{dir,vx}` — one touch moving fast enough to cross a **velocity + distance**
  threshold; `dir ∈ {left,right,up,down}`. Distinguished from `Pan` purely by
  velocity — a slow move stays `Pan`.

The recognizer only **classifies**; the action mapping is the consumer's. ssh_home
maps a horizontal `Swipe{right}` → send `Enter` (accept an agent's highlighted
default) and `Swipe{left}` → `Esc`, while vertical drag/scroll stays scroll — see
that repo's DESIGN.md §1a "one-gesture accept".

Because it's pure, it is **unit-testable with synthetic touch sequences — no
window, no device.** Desktop, which has no touch, feeds the recognizer synthetic
pinch from `Ctrl+wheel` (and a horizontal `Swipe` from a fast `Shift+wheel` or a
key) at the app layer.

## Verification (falsifiable)

- **Mapping (Rust unit):** winit/JS event → `(tag, fields)` is a pure function;
  table-test it, incl. the new named keys and IME commit.
- **Invariant (headless integration):** under `xvfb-run`, inject a known sequence
  with `xdotool` (`type "Héllo"`, `key Ctrl+c`, `key Home`, mouse click+drag) and
  assert the drained loft event sequence equals the injected one — order preserved,
  nothing lost or duplicated, `"Héllo"` arrives as `EV_TEXT` UTF-8, `Ctrl+c` as
  `EV_KEY_DOWN key='c' mods=MOD_CTRL`. On wasm, the same via headless-Chromium
  dispatching `KeyboardEvent`/`TouchEvent`. A dropped or reordered event fails.
- **Gestures (pure loft unit):** feed a synthetic two-finger sequence → assert the
  `Pinch.scale` series; a single down/up → `Tap`; a **fast** horizontal drag →
  `Swipe{right}`, and the **same path slower** → `Pan` (not `Swipe`) — pinning the
  velocity threshold. No device needed.
