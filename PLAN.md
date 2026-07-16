<!-- Copyright (c) 2026 Jurjen Stellingwerff  SPDX-License-Identifier: LGPL-3.0-or-later -->

# PLAN — ssh_home implementation, in small verifiable steps

Every step is independently verifiable. The bulk (the VT emulator) is pure and
deterministic, so it is proven with **golden PNGs**; logic is proven with unit
assertions; SSH is proven **live** against a local `sshd`. See [DESIGN.md](DESIGN.md)
for the *what/why*; this is the *how*, ordered so the test harness exists before
the thing it tests.

## Verification legend

- **(G) golden PNG** — render a frame, `gl_screenshot` → PNG, compare to a committed
  `golden/*.png`. Runs headless under `xvfb-run` (GL needs a real context; there is
  no surfaceless path). `BLESS=1` regenerates goldens. Small per-pixel tolerance
  absorbs GPU/AA variance; the monospace font is **bundled in-repo** (`fonts/`) and
  pinned so rasterization is reproducible.
- **(U) unit** — a pure loft assertion on the grid model or an encoder's output
  bytes; no window, fast, exact.
- **(L) live** — run against a local `sshd` (or a throwaway sshd container) and, for
  integration, a scripted `tmux` with volatility removed (status/clock off) so
  frames are deterministic.

## Technical grounding (from loft's `lib/graphics`, verified in ../loft)

- Render loop: `gl_create_window(w,h,title)`, `gl_poll_events()` (false = close),
  `gl_clear(0xRRGGBBAA)`, `gl_swap_buffers()`, resize via `WindowEvent::Resized`.
- Capture: `gl_screenshot(w,h,path)` (reads `GL_BACK`; call after draws, before swap).
- Text: `gl_load_font(path)`, `gl_measure_text(font,text,size)`, `gl_text_height`.
  There is **no one-call text blit** — glyphs are rasterized (fontdue) into a CPU
  `Canvas` and uploaded via `gl_upload_canvas(data,w,h)→tex`, then drawn as a
  textured quad. Step 0.3 pins this into a **monospace glyph atlas** (the efficient
  terminal path).
- Input: **polling only** — `gl_key_pressed(keycode)`, `gl_mouse_x/y`,
  `gl_mouse_button`, `gl_mouse_wheel` (accumulated, reset on read).

### Three gaps this plan works around (and later closes)

1. **Keyboard is not a text stream.** `gl_key_pressed` is is-key-down over a 0–255
   keycode index — no character/IME/key-repeat. v1 synthesizes PTY bytes from
   keycodes + Shift/Ctrl (covers ASCII, Enter, arrows, Ctrl-*, enough to drive tmux
   and type the password). Full Unicode/IME → extend `lib/graphics` (winit already
   carries the events) — a `loft-lang/loft` contribution.
2. **No touch/pinch events.** The native backend wires mouse + wheel, not `Touch`.
   On Linux, tap≈click, scroll≈wheel, pinch≈**Ctrl+wheel / `+`-`-` keys**. Real
   multitouch + pinch is part of the Android backend (wire winit `Touch`/gesture).
3. **GL needs a display.** Headless = `xvfb-run`, not a surfaceless context.

---

## Step 0 — Build the harness first (instrument before building)

- **0.1 Skeleton + capture.** `loft.toml`, `src/main.loft`: open a window,
  `gl_clear(0x101010FF)`, `gl_screenshot`, exit. **Verify (G):** under `xvfb-run`
  the PNG matches a committed solid-color golden; a wrong clear color mismatches
  (prove the harness can *fail* before trusting it).
- **0.2 Golden runner.** A `[[test]]`/script that runs the program headless,
  captures PNG(s), compares to `golden/` via `lib/imaging` decode + tolerance;
  `BLESS=1` regenerates. **Verify:** two runs identical; a corrupted golden fails.
- **0.3 Glyph atlas + one line of text.** Rasterize printable ASCII once into a
  monospace atlas texture; draw the string "READY". **Verify (G):** "READY" golden.
  Pins the text primitive the whole emulator sits on.

## Step 1 — Cell grid renderer (pure; golden-verified)

- **1.1 Grid model + draw.** `cols×rows` of cells `{codepoint, fg, bg, attrs}`;
  render as textured quads from the atlas. **Verify (G):** a fixed pattern
  (box-border + text) matches golden. **(U):** atlas has a quad per printable code.
- **1.2 Geometry + DPI default.** cols×rows derived from window size ÷ cell size;
  DPI-aware default cell size. **Verify (U):** `(win, cell) → (cols, rows)` table.
  **(G):** same text at two sizes → two goldens with different grid dims.

## Step 2 — VT/ANSI emulator (pure; the bulk — golden + model assertions)

Each sub-step: a byte fixture → mutate grid → assert model + render golden.

- **2.1 Text + C0** (LF, CR, BS, HT), cursor advance, right-margin wrap (DECAWM).
- **2.2 CSI cursor moves** (CUU/D/F/B, CUP) + **erase** (ED/EL).
- **2.3 SGR** — bold, 16 / 256 / truecolor fg+bg, reverse, underline.
- **2.4 Scroll region** (DECSTBM), index / reverse-index, line insert/delete.
- **2.5 Modes tmux needs** — alt-screen (1049), cursor show/hide, and the
  **mouse-tracking modes 1000/1002/1006** (latch a flag so input encoding switches on).
- **2.6 Corpus replay** — record real byte streams (`vim`, `htop`, a `tmux` frame)
  as fixtures; replay → **(G)** golden + **(U)** normalized-text assert. The
  confidence step: proves the emulator against real-world escape sequences.

## Step 3 — Input encoding (pure; unit-verified)

- **3.1 Keyboard → PTY bytes** — printable ASCII, Enter (CR), Backspace, Tab, Esc,
  arrows (CSI), Ctrl-letters (0x01–0x1A), from polled keycodes + modifiers.
  **Verify (U):** event → exact-bytes table.
- **3.2 Mouse → SGR** — click at pixel `(x,y)` + cell size → `ESC[<b;col;row M/m`;
  wheel → scroll — gated by the mouse-mode flag from 2.5. **Verify (U):** pixel→SGR
  table; no emission when mouse mode is off.
- **3.3 Zoom → resize** — a pinch/zoom step (Ctrl+wheel on Linux) changes cell size,
  recomputes cols×rows, emits a resize. **Verify (U):** zoom → new cols×rows.
  **(G):** same content at two zoom levels.

## Step 4 — SSH transport (russh FFI; live-verified)

Mirror `lib/web/native`: `native/` cdylib with `loft-ffi`/`loft-ffi-macros`,
`#native "n_ssh_*"` in `src/ssh.loft`, a tokio runtime behind a **sync/polling**
surface, binary bytes via the NUL-safe `pack_*`/`byte_at` path.

- **4.1 Crate skeleton** — `ssh_connect(host,port)→h`, `ssh_auth_password(h,user,pw)→bool`,
  `ssh_open_shell(h,cols,rows)→bool`, `ssh_write(h,bytes)`, `ssh_read(h)→bytes`
  (non-blocking), `ssh_resize(h,cols,rows)`, `ssh_close(h)`. **Verify (L):** against
  a local `sshd`, connect+auth+`echo LOFT_OK`+read returns the marker; wrong
  password → `false`.
- **4.2 Binary round-trip** — write `printf '\033[31mX\033[0m'` remotely, read back
  through the FFI, assert bytes exact (NUL-safe). **Verify (U/L).**
- **4.3 Resize propagation** — `ssh_resize` then remote `stty size` reports the set
  dims. **Verify (L).**

## Step 5 — Linux v1 integration (the deliverable)

- **5.1 Wire the loop** — SSH read → emulator → render; keyboard/mouse → encoders →
  `ssh_write`; resize/zoom → `ssh_resize`. Auto-run the startup command (default
  `tmux attach`) on connect; password typed via the keyboard text path.
- **5.2 Integration goldens (L+G)** — against local `sshd` + a scripted `tmux` with
  status/clock off: golden key frames for after-attach, after-click-select,
  after-scroll. **(U):** normalized grid text.
- **5.3 Config** — host, port (`42022`), startup command, default text size.
  **Verify (U):** parsed values; run with an overridden port.
- **5.4 Manual acceptance** — run against the real laptop on `42022`: attach tmux,
  click a window, scroll, type. The real sign-off.

## Step 6 — Speech stand-in, then Android (later)

- **6.1 Input-source abstraction** — on Linux a text field / stdin stands in for
  speech and routes to the selected window (same path as keyboard). **Verify (U).**
- **Android gaps** (file as `loft-lang/loft` issues): `aarch64-linux-android` build
  target; `lib/graphics` EGL/`ANativeWindow` backend; the input-event queue (winit
  `Touch` + IME text); speech engine (whisper-FFI, or a thin JNI shim). Concrete
  library-addition designs: [docs/lib-gaps/](docs/lib-gaps/).

## Step 7 — File transfer + directory browsing (SFTP; a natural later extension)

Grabbing a file off the laptop onto the phone (a log, a photo, a document) and browsing
the remote filesystem is the obvious next want once the terminal works. It composes
cleanly onto everything above and needs **no redesign** — SSH multiplexes channels, so
this is an **additive second channel on the same authenticated `Session`**; the shell
keeps running untouched while a transfer proceeds.

- **7.1 SFTP lib surface — mirror loft's native `File`** (full spec:
  [docs/sftp-file-api.md](docs/sftp-file-api.md)). Extend the `ssh` lib (an `ssh 0.2.0`, or a
  sibling `loft-libs-net/sftp`) with an SFTP subsystem backed by `russh-sftp`, shaped **1:1 on
  the stdlib file API**: reuse `Format` / `FileResult`; a `RemoteFile` (path/size/format/session)
  with `content()` / `lines()` / `read_bytes()` / `files()` / `write()` / `exists()`; `s.file(path)`
  the sole shape delta vs native `file(path)`; `Session` methods mirror the path free-fns
  (`list_dir` / `read_bytes` / `mkdir` / `move` / `mtime`); path-text helpers (`join`/`dir`/
  `basename`) are shared unchanged. **Binary vs text is `Format`-driven** (`content()` text,
  `read_bytes()` binary — sniffed on open, never by transport). A remote loft **store** loads via
  the non-mmap `s.store_load(r, path)` (mmap / `store_persist_bind` can't cross SFTP; the
  byte-decode reader — same one the browser store-app uses over HTTP — can). Additive: a second
  channel on the existing `Session`, shell untouched. **Verify (L):** a `RemoteFile` walk prints
  the same shape a native `File` walk would; a **binary** download is byte-exact (sha vs source);
  upload + re-list round-trips; `store_load` of a remote image queries identically to a local one.
- **7.2 File browser — show project files** — render the remote directory listing in the
  grid: tap to descend / `..` to ascend, a mode toggle (or swipe) between terminal ↔ files
  so the tmux session stays live. **Verify (G+U):** a listing golden + the navigation model
  (path stack, selection).
- **7.3 File viewer — view them** — open a selected file (`read_file`) into a **scrollable
  read-only pane**: text renders through the existing Grid/Canvas path (line-wrap + scroll,
  no PTY needed); images (PNG/JPEG) via a `lib/graphics` decode, later. This is the heart of
  the feature — glance at a config, a log, a source file on the phone without a shell dance.
  **Verify (G):** a text-file view golden; **(U):** the wrap/scroll model.
- **7.4 Download / upload to phone storage** — save a viewed/selected file locally
  (byte-exact) and upload back; on Linux v1 "phone storage" is a config'd local dir.
  **Verify (L):** sha round-trip.

Out of scope for the shell-only `ssh 0.1.x` on purpose (YAGNI for the terminal); recorded
here so Steps 4–6 stay compatible with it (they already are — one `Session`, many channels).

---

## Suggested first PR boundary

Steps **0–1** (harness + a golden-verified grid renderer) make a self-contained,
reviewable slice that stands up the entire verification story with zero external
dependencies — the right place to stop and check the approach before the emulator
and SSH work.
