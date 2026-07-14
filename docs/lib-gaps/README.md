<!-- Copyright (c) 2026 Jurjen Stellingwerff  SPDX-License-Identifier: LGPL-3.0-or-later -->

# Library gap designs

ssh_home is a pure-loft app built on loft's `lib/graphics`. Building it surfaces
gaps in that existing library (and in the loft toolchain). Each gap here is a
**design proposal to `loft-lang/loft`** — drafted from the consumer side that hit
it, in the spirit of the repo's dogfooding loop (loft store/engine requests are
filed as issues on `loft-lang/loft`; this repo is the test-bed).

ssh_home v1 (Linux) is designed to **work around** these gaps (see [../../PLAN.md](../../PLAN.md));
these designs are what makes the *Android* target and the *full* interaction model
land cleanly, and they benefit every loft app that needs text input or touch.

| # | Gap | Existing lib affected | Proposal |
|---|---|---|---|
| 01 | Keyboard is keycode-polling only — no Unicode/IME text, no key-repeat, no per-event modifiers, several named keys unmapped; and touch collapses to a single mouse (no multitouch) | `lib/graphics` (both native + wasm backends) | [01-graphics-input-events.md](01-graphics-input-events.md) |
| 02 | No Android build target; `lib/graphics` has no Android windowing/GL backend | loft toolchain + `lib/graphics` | [02-android-target-and-backend.md](02-android-target-and-backend.md) |

Both are grounded in the current code (`../loft/tests/fixtures/libs/graphics`):
`gl_key_pressed(keycode)`/`gl_mouse_*` polling, the winit `key_index` map
(`native/src/lib.rs`), the `KEY_*` block (`src/graphics.loft`), and the wasm
`loft-gl.js` input shim.
