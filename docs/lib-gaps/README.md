<!-- Copyright (c) 2026 Jurjen Stellingwerff  SPDX-License-Identifier: LGPL-3.0-or-later -->

# Library gap designs

ssh_home is a pure-loft app on loft's `lib/graphics`. Building it surfaced gaps in
loft's existing libraries and toolchain. These are being **closed** inside
`loft-lang` (where we have commit rights), not just filed as wishes:

- **Gap 01 — `lib/graphics` input** → implemented in `loft-lang/loft-libs-graphics`.
  The keycode-**polling** input model can't carry a terminal (or an Android soft
  keyboard): no Unicode/IME text, no key-repeat, no per-event modifiers, several
  named keys unmapped, no multitouch. Design + invariant:
  [01-graphics-input-events.md](01-graphics-input-events.md).

- **Gap 02 — Android** splits into two pieces:
  - **Build target** = loft **compiler** work → a concrete, implementation-ready
    handoff for the loft agent:
    [../loft-compiler/android-build-target.md](../loft-compiler/android-build-target.md).
  - **`lib/graphics` EGL/`ANativeWindow` backend** → `loft-lang/loft-libs-graphics`;
    design in [02-android-target-and-backend.md](02-android-target-and-backend.md)
    Part B; blocked on the build target.

Separately, **SSH transport is a new library** in `loft-lang/loft-libs-net`
(alongside `web`/`server`) — not a gap in an existing lib, but tracked with this
work. See [../../PLAN.md](../../PLAN.md) Step 4.

ssh_home v1 (Linux) works around whatever isn't ready yet (see PLAN.md). Each design
states one load-bearing **invariant** and a **falsifiable** test. Grounded in the
real code: `loft-libs-graphics/graphics` (the `gl_*` API + winit backend + `loft-gl.js`
shim) and `loft-libs-net/web` (the `#native` FFI pattern the SSH lib mirrors).
