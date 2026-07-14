<!-- Copyright (c) 2026 Jurjen Stellingwerff  SPDX-License-Identifier: LGPL-3.0-or-later -->

# Gap 02 — an Android build target + a `lib/graphics` Android GL backend

**Proposal to `loft-lang/loft`.** Two independent pieces: a toolchain target (Part
A) and a graphics backend (Part B). Part A gates all Android work; Part B rides on
loft's roadmap item `GFX.PORTABLE`.

## Where things stand

- loft targets today: host `--native`, `--html` (WebGL2), `--native-wasm`
  (wasm32-wasip2), `wasi`. There is **no `aarch64-linux-android`** — `build-native`
  is host-only; cross-compile exists only for wasm.
- `lib/graphics` native backend is glutin + winit + `gl` on X11/Wayland (desktop).
  winit already supports Android via `android-activity`, but there is **no EGL /
  `ANativeWindow` backend** and no lifecycle handling.

## Part A — a loft `aarch64-linux-android` target

loft `--native` already lowers loft → Rust → rustc. The target adds "point rustc
at the Android triple + NDK, emit a JNI-loadable `.so`, package an APK":

1. **Cross-compile:** `--target aarch64-linux-android` (plus `armv7`/`x86_64` for
   emulators), linked with the **NDK clang** (mirror `cargo-ndk`'s linker/AR/sysroot
   env). Output a `cdylib` `.so`.
2. **Entry point:** a `NativeActivity`/`android-activity` (`GameActivity`) glue
   whose `android_main` calls the loft program's `main`. No app-developer Java —
   the APK ships the generated `.so` + a stock manifest + the activity glue.
3. **Package:** emit the `.so` and drive an APK build (a `cargo-apk`-style step, or
   emit a Gradle-less APK skeleton). Proposed surface: `loft build android` and
   `loft --native-android [out.apk]`, symmetric with `--html`/`--native-wasm`.

**Invariant:** a loft program that builds and runs under host `--native` builds an
APK whose on-device `main` is the *same program* — no source changes, only the
backend swap. (Same guarantee `--html` already gives for the browser.)

**Verification:** build a hello-world loft `.so`; load it in a minimal APK on the
Android emulator; assert `main` runs (marker over `adb logcat`). Then a graphics
program: render one frame, `gl_screenshot` on-device, `adb pull` the PNG, compare
to the desktop golden within tolerance — proving one source renders identically on
both backends.

## Part B — `lib/graphics` EGL / `ANativeWindow` backend

The desktop backend already drives a winit `ApplicationHandler` event pump; the
Android port reuses that loop and swaps the context/surface + input source:

1. **Context/surface:** create an **EGL** context on the `ANativeWindow` winit
   hands over. Target **GLES 3.0** — the common subset with the desktop `gl` 3.3
   path the terminal uses (textured quads + one shader set written as
   `#version 300 es`, which also runs on desktop, so shaders stay single-source).
2. **Lifecycle (the fiddly, no-desktop-analog part):** Android destroys the GL
   surface on background/rotate and recreates it on resume. On surface-destroyed,
   drop the EGL surface; on surface-created, recreate it **and re-upload all GL
   resources** (the glyph-atlas texture, VAOs, shaders) before the next frame.
3. **Input:** route `android-activity` key/IME events and `MotionEvent` pointers
   into the Gap 01 event queue — so app code is byte-identical to desktop.
4. **DPI:** report the display density so the DPI-aware default text size (PLAN
   Step 1.2) is correct on real screens.

**Invariant:** across any surface destroy→recreate (background, rotate), no draw
call targets a dead context, and after recreation every GL object referenced by a
draw has been rebuilt — so the first post-resume frame is correct, not blank/crashy.

**Verification:** on the emulator, script rotate + background/foreground between
frames; assert (a) no crash, (b) the post-resume frame matches the pre-rotate
golden (via `gl_screenshot` + `adb pull`). A backend that skips resource re-upload
fails (b); one that draws during the destroyed window fails (a).

## Sequencing

Part A first (it gates everything and is independently testable with a non-graphics
`.so`). Part B rides `GFX.PORTABLE`; if that lands the portable `Renderer`/`Scene`
+ wgpu path first, Part B becomes "wgpu on Android" instead of hand-rolled EGL —
the app is unaffected because it only ever touches the `gl_*` / renderer surface,
never the backend. See [../../DESIGN.md](../../DESIGN.md) §9 for that open decision.
