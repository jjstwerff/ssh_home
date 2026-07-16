<!-- SPDX-License-Identifier: LGPL-3.0-or-later -->
# SFTP file & directory API — mirror loft's native `File` (design for PLAN Step 7.1)

**Goal.** Browsing and viewing a remote file over SFTP should feel *identical* to loft's
native file handling. A consumer that already knows `file(p).content()` / `.files()` /
`.format` should read a **remote** tree the same way — the only difference being *which*
filesystem, expressed as the `Session` the handle comes from.

The rule: **reuse the stdlib's `File` shape, don't invent a parallel one.** Reuse its enums
verbatim, mirror the `File` struct and its methods 1:1, and keep the single unavoidable
delta (a remote handle needs a connection) as small and obvious as possible.

## The native reference (loft stdlib, `default/02_files.loft`)

- Enums — **reused as-is, never re-declared:**
  `Format { TextFile, LittleEndian, BigEndian, Directory, NotExists }`,
  `FileResult { Ok, NotFound, PermissionDenied, IsDirectory, NotDirectory, Other }` + `.ok()`.
- `struct File { path: text, size: integer, format: Format, … }`;  `file(path) -> File`.
- Handle methods: `content() -> text?`, `lines() -> vector<text>`, `write(v) -> FileResult`,
  `files() -> vector<File>` (list a directory as handles), `exists() -> boolean`.
- Path free-fns: `is_dir(path)`, `is_file(path)`, `list_dir(path) -> vector<text>?`,
  `read_bytes(path) -> vector<u8>?`, `write_bytes(path, bytes)`, `mkdir(path)` / `mkdir_all`,
  `delete(path)`, `move(from, to)`, `mtime(path)`.
- Path-text methods: `dir()`, `basename()`, `join(other)`, `resolve(target)`, `path_sep()`,
  `starts_with` / `ends_with`.

## The SFTP mirror

**Types — reuse the stdlib `Format` / `FileResult` unchanged.** A remote entry's
`.format == Format.Directory` and an op's `FileResult.PermissionDenied` are the *same types*
a native consumer already matches on. `RemoteFile` mirrors `File`, plus the one addition —
the `Session`:

```loft
pub struct RemoteFile {
  path: text,        // full remote path                     (== File.path)
  size: integer,     // bytes                                 (== File.size)
  format: Format,    // TextFile / Directory / NotExists      (== File.format; stdlib enum)
  session: Session,  // the connection — the ONE addition vs native File
}
```

**Constructor — the only shape difference from native `file(path)`:** it hangs off the
`Session`, because a remote file needs a connection.

```loft
pub fn file(self: Session, path: text) -> RemoteFile;   //  s.file(p)   mirrors   file(p)
```

**Handle methods — 1:1 with native `File`:**

```loft
pub fn content(self: RemoteFile) -> text?;              // == File.content   (whole-file text)
pub fn lines(self: RemoteFile) -> vector<text>;         // == File.lines
pub fn read_bytes(self: RemoteFile) -> vector<u8>?;     // binary (images); mirrors free read_bytes
pub fn write(self: RemoteFile, v: text) -> FileResult;  // == File.write
pub fn files(self: RemoteFile) -> vector<RemoteFile>;   // == File.files  (list dir → handles)
pub fn exists(both: RemoteFile) -> boolean;             // == File.exists (format != NotExists)
pub fn is_dir(both: RemoteFile) -> boolean;             // convenience for `format == Directory`
pub fn is_file(both: RemoteFile) -> boolean;
```

**Path operations — mirror the native free-fns, as `Session` methods** (identical names +
`FileResult` returns; they take a `Session` only because they need the connection):

```loft
pub fn is_dir(self: Session, path: text) -> boolean;
pub fn list_dir(self: Session, path: text) -> vector<text>?;
pub fn read_bytes(self: Session, path: text) -> vector<u8>?;
pub fn write_bytes(self: Session, path: text, bytes: vector<u8>) -> boolean;
pub fn mkdir(self: Session, path: text) -> FileResult;
pub fn delete(self: Session, path: text) -> FileResult;
pub fn move(self: Session, from: text, to: text) -> FileResult;
pub fn mtime(self: Session, path: text) -> integer;
```

**Path-text helpers — already shared; NO remote version.** A remote path is just `text`, so
the stdlib `dir()`, `basename()`, `join()`, `resolve()`, `path_sep()`, `starts_with` /
`ends_with` work verbatim on remote paths. Path manipulation is identical local vs remote.

## The parity, side by side

```loft
// native — list a project dir + read a file
for f in file(root).files() {
  if f.format == Directory { println("d {f.path.basename()}"); }
  else                     { println("  {f.path.basename()}  {f.size}"); }
}
src = file(root.join(".bashrc")).content() ?? "";

// remote (ssh_home) — the SAME code; only `s.` scopes it to the connection
for f in s.file(root).files() {
  if f.format == Directory { println("d {f.path.basename()}"); }
  else                     { println("  {f.path.basename()}  {f.size}"); }
}
src = s.file(root.join(".bashrc")).content() ?? "";
```

So Step 7.2's browser walks `s.file(cwd).files()`, and 7.3's viewer shows `sel.content()`
(text) or `sel.read_bytes()` (image) — the path stack uses the stdlib `join`/`dir`/`basename`
with no remote-specific code.

## Binary & text handling (mirrors native's `Format`-driven modes)

Native already carries the binary/text distinction in `File.format` (`TextFile` vs
`LittleEndian` / `BigEndian`) and splits the read surface into `content() -> text?` (text)
and `read_bytes() -> vector<u8>?` (binary). `RemoteFile` mirrors both, so the viewer's
text-vs-image decision is native-identical:

- `sel.content() -> text?` — the remote bytes decoded as UTF-8 text (the viewer's text path;
  `null` if unreadable). Same NUL-safe transport as the shell (`byte_at`).
- `sel.read_bytes() -> vector<u8>?` — the raw bytes, untouched — for images (PNG/JPEG via a
  `lib/graphics` decode) or a hex/size preview of anything else.
- `sel.format` — SFTP has no text/binary notion on the wire (it's all bytes), so `format` is
  set on `open` by a cheap **sniff** (extension + a NUL / UTF-8 check on the first block),
  exactly the way a native editor decides — never by the transport. The result *is* a stdlib
  `Format`, so:

```loft
if sel.format == TextFile { show_text(sel.content() ?? "") }
else                      { show_image_or_hex(sel.read_bytes()) }   // identical to a native viewer
```

## Loading a loft store from the remote — no mmap, `store_load` still works

`store_persist_bind` (the mmap-backed store) **cannot** cross SFTP — there is no remote mmap,
and it isn't needed here. But the **non-mmap** reader `store_load(r, path)` — the same
wasm-safe heap-store decoder the browser store-app reaches over HTTP via `store_load_url` — CAN:
SFTP-fetch the store image to bytes, decode into the reference. So the remote surface mirrors
`store_load`, **not** `store_persist_bind`:

```loft
pub fn store_load(self: Session, r: reference, path: text) -> boolean;   //  == native store_load(r, path)
```

`s.store_load(db, "/srv/app/layout.store")` reads the remote image over SFTP and decodes it
into `db` — bytes never mmap'd, exactly as `store_load_url` does over HTTP; a consumer then
queries `db` identically to a locally `store_load`ed one, only the *source* (SFTP) differs.
Paged `store_load_key` / `store_load_range` variants can follow if partial remote reads are
wanted — they'd SFTP-`pread` the needed ranges instead of the whole image.

## Deltas from native (each unavoidable or deferrable)

- **Session-scoped constructor** (`s.file(p)` vs `file(p)`) — a remote file needs a
  connection. The single irreducible difference; everything downstream is identical.
- **Whole-file reads first** — the native `File` streaming surface (`current` / `next` /
  seek) is deferred; the viewer reads whole files. Add SFTP `pread`/`pwrite` streaming later
  if a large-file/random-access need appears.
- **Async behind a sync face** — like the shell channel, SFTP runs on the tokio runtime
  behind the same blocking/polling FFI; `content()` / `files()` block on the round-trip.

## Implementation — safe small steps

**Architecture.** One **additive** capability: a second SSH channel on the *existing*
authenticated `Session` (`russh` + `russh-sftp`), opened lazily on the first file op. Native
FFI mirrors the shell path — `n_sftp_open` / `n_sftp_list` / `n_sftp_read` / `n_sftp_write` /
`n_sftp_stat` / `n_sftp_mkdir` / … behind the same `LoftStore` + byte-buffer marshaling as
`send` / `recv` / `byte_at` (binary-safe; `read_bytes` returns raw bytes via `byte_at`). Ships
as `ssh 0.2.0` (same crate) or a sibling `loft-libs-net/sftp`.

**What makes the steps *safe*.** Every step is: (a) **additive** — a new symbol, and the shell
surface (`ssh 0.1.x`) is never edited; (b) **independently verified** before the next is begun;
(c) **deterministic** — a seeded mock SFTP tree + golden images, no clocks; (d) small and
reversible. Two gates recur at every lib step:
- **shell-still-green** — re-run the `ssh 0.1.x` live smoke (PLAN Step 4) after each lib step; the
  terminal must be provably unbroken (this is the whole point of "additive").
- **interpret == native** — the step passes on both backends. (No `--html`: a browser has no raw
  socket — § top. And `--native` needs the P269 install fix — see routing's `loft-feedback.md`.)

Verification legend as in [PLAN.md](../PLAN.md): **(U)** unit · **(G)** golden PNG · **(L)** live.

### Phase A — the lib (native `File` mirror over SFTP)

- **A0 — Mock SFTP + harness (fail first).** Extend `tools/mock_sshd.py` with paramiko's
  `SFTPServer` over a seeded tree: a text file, a binary file (with NUL bytes), a subdir, and a
  small loft store. **(L):** the harness opens the SFTP subsystem; a wrong path errors cleanly —
  prove it can *fail* before trusting it.
- **A1 — Open the channel (shell untouched).** `open_sftp(self: Session)` opens the second
  channel lazily. **(L):** with a shell open *and echoing*, open SFTP; assert the shell still
  echoes AND SFTP is open — the **shell-still-green** gate, first proof the design is additive.
- **A2 — List a directory.** `s.list_dir(path) -> vector<text>?` and `s.file(path).files() ->
  vector<RemoteFile>` (path/size/format from the SFTP stat). **(L):** the seeded dir → the exact
  entries; a missing dir → `null`; a file → `NotDirectory`. **(U):** the `RemoteFile` fields
  populate.
- **A3 — Read text.** `sel.content() -> text?` / `sel.lines()` via `n_sftp_read`. **(L):** a
  seeded text file → byte-exact content; a missing file → `null`.
- **A4 — Read binary + format sniff.** `sel.read_bytes() -> vector<u8>?` (raw, NUL-safe);
  `format` set on open by the extension + a NUL/UTF-8 sniff. **(L):** a binary file (with NULs)
  downloads **byte-exact** (sha vs source); its `format` is binary, a text file's is `TextFile`.
- **A5 — Write + mutate.** `write` / `write_bytes` / `mkdir` / `delete` / `move` → `FileResult`.
  **(L):** write→re-read matches; mkdir→list shows it; move→re-list; delete→gone; each returns the
  right `FileResult`.
- **A6 — `store_load` over SFTP (no mmap).** `s.store_load(r, path)` fetches the remote image and
  decodes via the non-mmap reader. **(L):** `store_load` a seeded remote store; a known-record
  query matches the *same store loaded locally* — mmap never involved.
- **A7 — Parity gate + publish.** Full lib suite on `--interpret` **and** `--native`; the
  `ssh 0.1.x` smoke still green (no regression). Publish `ssh 0.2.0` / the `sftp` lib. **Verify:**
  interpret == native; the shell surface is unchanged.

### Phase B — the app (browser + viewer)

- **B0 — Browser model (pure).** cwd + entries (`s.file(cwd).files()`) + selection + path stack;
  descend / `..` / select. **(U):** the navigation model against a seeded listing.
- **B1 — Browser render.** Listing → Grid: dirs vs files, a size column, selection via SGR
  reverse. **(G):** a listing golden. **(U):** entries → cells.
- **B2 — Text viewer.** Open a text file → a scrollable pane (reuse the Grid + line-wrap + the
  scroll model). **(G):** a text-view golden. **(U):** the wrap/scroll model.
- **B3 — Binary / image viewer.** Image `format` → decode via `lib/graphics` + render; else a
  hex/size summary. **(G):** an image-view golden (a seeded small PNG); a non-image binary → a hex
  golden.
- **B4 — Download / upload to phone storage.** A selected file's `read_bytes()` → local storage
  (byte-exact); upload reads local → `write_bytes`. Linux v1: a config'd local dir. **(L):** an sha
  round-trip.
- **B5 — Mode toggle + wire into the app loop.** A terminal ↔ files toggle (gesture/key) so tmux
  stays live while browsing; fold the browser/viewer into the Step 5 loop. **(G+L):** switch to
  files → browse → view → back to terminal, with the tmux session unaffected (a key frame after
  each transition).

**First reviewable slice: A0–A2** (mock + additive channel + listing) — it stands up the whole
verification story and proves the shell-still-green gate before any read / write / render, exactly
as Steps 0–1 did for the main app.
