<!-- Copyright (c) 2026 Jurjen Stellingwerff  SPDX-License-Identifier: LGPL-3.0-or-later -->

# ssh_home

A **pure-loft SSH terminal for your phone.** Log into your home laptop over SSH,
attach `tmux`, and drive it from a phone-width terminal — panes you switch by
touch, scroll by drag, and (later) prompts you enter by speech.

It is written in [loft](https://github.com/loft-lang/loft) — dogfooding the
language — with a small **Rust FFI library for the SSH transport**. The UI
renders through loft's `lib/graphics` GL surface, so the *same source* runs as a
native desktop app on **Linux today** and, once loft grows an Android build
target, as a native **Android** app — no browser, no WebView.

## Authentication (security stance)

- **Password SSH auth first.** No public-key auth in v1.
- **No private key is ever stored on the device.** No key file, no agent, no
  keychain entry.
- The password is typed into the **on-screen terminal** at connect time, held in
  memory only for the SSH handshake, and never written to disk or logs.
- Host and port are fully configurable (default port `42022`).

## Status

Early scaffolding — no code yet. See [DESIGN.md](DESIGN.md) for the architecture
and the staged plan. **Linux-native, single on-screen terminal, password auth**
is the first build target; Android is a later re-target of the same source.

## Toolchain

Built with the installed `loft` on `PATH`. The SSH transport is a Rust crate
(`russh`) exposed to loft via its native FFI, mirroring how loft libraries like
`web` wrap a Rust HTTP client.

## License

LGPL-3.0-or-later, matching loft.
