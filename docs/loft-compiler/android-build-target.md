<!-- Copyright (c) 2026 Jurjen Stellingwerff  SPDX-License-Identifier: LGPL-3.0-or-later -->

# Compiler design — a loft `android` build target (handoff for the loft agent)

**Audience:** the agent working in `loft-lang/loft`. This is **compiler/toolchain
work** (in `../loft`), out of scope for the ssh_home / lib repos. It is written so
you can pick it up and implement without re-deriving the shape. Grounded in the
current driver (`src/native_utils.rs`, `src/manifest.rs`, `src/wasm_gl.rs`), and
mirrors the existing browser/WASM target `@F54`.

## Goal & invariant

Add a cross-compile target that turns a loft program into an **Android app** —
`aarch64-linux-android` (+ emulator triples), linked with the NDK, packaged as an
APK whose `NativeActivity` runs the program's `main`.

**Invariant (the definition of done):** a loft program that builds and runs under
host `--native` builds an APK whose on-device `main` is the *same program*, with no
source changes — only the backend swaps. This is the exact guarantee `--html`
already gives for the browser. Every milestone below is a falsifiable check of a
slice of it.

## What already exists to mirror (`@F54`, the browser/WASM target)

The driver already cross-compiles to a non-host triple; Android is a third shape
next to `--native-wasm` (`wasm32-wasip2`) and `--html`:

- **`src/native_utils.rs`** owns the cross rustc invocation as a *(triple ×
  feature-set)* pair (see the `WasmRuntimeShape` enum ~L149–161, the `--target`
  arg ~L267, the isolated `--target-dir` ~L283, and per-target prebuilt-rlib
  lookup ~L967). This is where an Android target descriptor is added.
- **`src/manifest.rs`** parses `loft.toml` targets (`html` → `--html`, `wasi` →
  `--native-wasm`, ~L25) and per-target override tables (`[native.wasm]` ~L161/497).
  Android adds a `android` target + a `[native.android]` table, symmetrically.
- **`src/wasm_gl.rs` / `src/wasm_assets.rs`** (`@F54`) show how a GPU/asset target
  wires an entry/boot shim. Android's entry shim is the analog (below).
- CLI flag recognition sits beside `--native-wasm` / `--html` in the driver
  front-end (`src/main.rs` / `src/bin/`).

File this as a new `@F##` in `loft-lang/features`, tracked via a `loft-lang/plans`
`@PLAN`.

## Design

### 1. Target descriptor (`native_utils.rs`)

Add an `AndroidAbi` shape beside `WasmRuntimeShape`, one variant per ABI:

| ABI | rustc triple | use |
|---|---|---|
| arm64-v8a | `aarch64-linux-android` | real devices (primary) |
| armeabi-v7a | `armv7-linux-androideabi` | old devices |
| x86_64 | `x86_64-linux-android` | emulator |

Each carries: the triple, the feature-set (start from `--native`'s; `random` etc.),
its **isolated `--target-dir`** (so Android artifacts never collide with host/wasm —
same discipline as the wasm tree), and `crate-type = ["cdylib"]` (a JNI-loadable
`lib<name>.so`). Default build = arm64-v8a; `--all-abis` (or `[native.android].abis`)
fans out.

### 2. NDK toolchain wiring

Discover the NDK (`ANDROID_NDK_HOME` / `ANDROID_NDK_ROOT`; error with a clear
"install the NDK / set ANDROID_NDK_HOME" if absent — the same shape as the
rustc-probe error path). Per triple, set the linker to the NDK clang and the API
level (default **`24`**), mirroring `cargo-ndk`'s env, e.g. for arm64:

```
CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER = $NDK/toolchains/llvm/prebuilt/<host>/bin/aarch64-linux-android24-clang
CC_aarch64-linux-android  = …/aarch64-linux-android24-clang
AR_aarch64-linux-android  = …/llvm-ar
```

`rustup target add <triple>` must be present (probe + actionable error). No
`-Wl,-rpath` (Android has no rpath; the loader finds `.so` in the APK's `lib/<abi>/`).

### 3. Entry point — `NativeActivity` / `android-activity`

An APK has no `main()`; Android calls `ANativeActivity_onCreate` (or, via
`android-activity`/GameActivity, `android_main`). Provide a small **runtime entry
shim** (the analog of the wasm boot in `wasm_gl.rs`) that:

- exposes `android_main(app: AndroidApp)` from the generated cdylib,
- stores the `AndroidApp`/`ANativeWindow` handle where `lib/graphics`' Android
  backend (Gap 02 Part B, separate) will read it, and
- calls the loft program's `main`.

No app-developer Java: ship a stock `AndroidManifest.xml` (declaring the
`NativeActivity` + `android.app.lib_name = <name>`) and, if using GameActivity, the
one prebuilt activity class. This shim + manifest are compiler-owned templates.

### 4. Packaging — APK

After the per-ABI `.so` builds: assemble `lib/<abi>/lib<name>.so` + the manifest +
resources into an APK, `zipalign`, and **debug-sign** (`apksigner` with the
auto-generated debug keystore — dev installs need a signature; release signing is
the user's). Two viable engines: shell out to the SDK build-tools
(`aapt2`/`zipalign`/`apksigner`), or adopt `cargo-apk`'s pipeline. Prefer the
build-tools path (fewer deps, matches how loft already shells to `rustc`).

### 5. Surfaces

Symmetric with `--html` / `--native-wasm`:

- CLI: `loft --native-android [out.apk]` (default `<script>.apk`).
- Project: `loft build android`; `loft.toml` `[[target]] android` + optional
  `[native.android]` (abis, min-api, app-id, label, icon).

## Milestones (each independently verifiable)

- **M0 — cross-compile.** A non-graphics loft program → `aarch64-linux-android`
  `.so`. **Verify:** `file lib<name>.so` = "ELF 64-bit LSB shared object, ARM
  aarch64"; expected symbols present. No emulator needed. *(Proves §1–2.)*
- **M1 — hello on device.** Minimal `NativeActivity` APK loads the `.so`;
  `android_main` runs the loft program; a `println` marker appears in
  `adb logcat`. **Verify:** grep logcat for the marker on an emulator/device.
  *(Proves §3.)*
- **M2 — one-command APK.** `loft --native-android` emits an installable signed
  debug APK. **Verify:** `adb install` succeeds; launch shows the marker. *(Proves §4–5.)*
- **M3 — GPU frame (unblocks lib/graphics Part B).** A `lib/graphics` program
  renders one frame; `gl_screenshot` on-device → `adb pull` PNG → compare to the
  desktop golden within tolerance. **Verify:** pixel match. *(Proves the invariant
  end-to-end: same source, same picture, host vs Android.)*

## What this unblocks (separate work, not here)

- **`lib/graphics` EGL/`ANativeWindow` backend** — ssh_home `docs/lib-gaps/02` Part B
  (in `loft-libs-graphics`): GLES-3.0 context on the `ANativeWindow` this shim
  captures, surface destroy/recreate lifecycle.
- **Input-event queue Android source** — ssh_home `docs/lib-gaps/01`: route
  `android-activity` key/IME + `MotionEvent` into the queue.

## Non-goals / open

- iOS (same pattern, later); release signing (user-supplied keystore).
- If `GFX.PORTABLE` + wgpu lands first, Part B changes but **this target does not** —
  the app only ever touches the `gl_*`/renderer surface, never the backend.

## Reference pointers (current code)

`src/native_utils.rs` (WasmRuntimeShape ~149, `--target` ~267, target-dir ~283,
prebuilt rlibs ~967) · `src/manifest.rs` (targets ~25, `[native.wasm]` ~161/497) ·
`src/wasm_gl.rs` (`@F54` boot shim) · driver flag site in `src/main.rs`/`src/bin/`.
