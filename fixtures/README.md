# VT corpus fixtures (Step 2.6)

Recorded real terminal byte streams, replayed through the emulator to prove it
against real-world escape sequences (not just hand-built ones).

## `session.vt` — a real `less -R` frame (144 bytes)

Captured from actual `less` rendering `corpus_src.txt` on a 32x10 terminal:

```sh
TERM=xterm-256color script -q \
  -c "stty rows 10 cols 32; less -R corpus_src.txt" /tmp/less.raw <<<'q'
# then slice the terminal frame out of script(1)'s wrapper: from the first
# `ESC[?1049h` up to (but not including) less's quit-cleanup `\r ESC[K`, so the
# drawn reverse-video status line survives.
```

The exact bytes are embedded in `src/main.loft` as `corpus_bytes()` (so the app
needs no file I/O); this directory keeps the provenance. The frame exercises
alt-screen (`?1049h`), a reverse-video status line, `EL`, `SGR` reset and CRLF row
advance — plus sequences the emulator deliberately IGNORES (title-stack `t`,
DECCKM `?1h`, keypad `ESC=`), proving unknown sequences are skipped gracefully.

`scene=vt6` renders it (`golden/vt6.png`); `vttest6` asserts the normalized screen.
