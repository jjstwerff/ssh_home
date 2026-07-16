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

## Implementation notes (Step 7.1)

- A **second SSH channel on the existing `Session`** (`russh` + `russh-sftp`), opened lazily
  on the first file op — the shell channel is untouched, so tmux keeps running while you
  browse or pull a file. One connection, one auth.
- Native FFI mirrors the shell path: `n_sftp_list` / `n_sftp_read` / `n_sftp_write` /
  `n_sftp_stat` behind the same `LoftStore` + byte-buffer marshaling as `send` / `recv` /
  `byte_at` (binary-safe; `read_bytes` returns raw bytes read via `byte_at`).
- Ships additively — an `ssh 0.2.0` (same crate) or a sibling `loft-libs-net/sftp` layered on
  the `Session`. No change to the shell surface.
- **Verify** as PLAN Step 7.1: (L) against a mock/real SFTP — `list_dir` returns seeded
  entries; a **binary** download is byte-exact (sha vs source); upload + re-list round-trips;
  and a `RemoteFile` walk prints the same shape a native `File` walk would.
