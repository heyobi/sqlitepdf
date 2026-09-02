# sqlite.pdf

A PDF document that contains a working SQLite shell. You type a query in
a fillable form field, press a button, and the rows appear in a stack of
read only text fields that behave like a terminal.

## How it works

The engine is SQLite compiled to asm.js, not WebAssembly. The javascript
engine inside a PDF viewer has no WASM, so the C code has to come out the
other side as plain javascript. Emscripten 1.39.20 is the last release
that can still do that.

The compiled engine is stored as a document level javascript object, which
the viewer executes the moment the file opens. A second script sets up the
console and the query function. Both share one global scope, so the button
action is a one liner that calls into the engine through `Module.ccall`.

Output never leaves the document. `printf` in C goes to `Module.print`,
which pushes lines into a buffer, and the buffer is painted into the
`out0` ... `out23` fields.

## Build

Smoke test first. This compiles a few lines of C with the exact same
flags and wraps them in a PDF, which tells you whether the emscripten
glue survives the viewer without waiting on a multi megabyte engine:

```
./build.sh hello
```

Then the real thing. This clones emsdk, pins 1.39.20, downloads the
SQLite amalgamation, compiles, and writes `out/sqlite.pdf`:

```
./build.sh
```

To iterate on the layout without waiting for a compile:

```
python3 generate.py --dummy --output out/skeleton.pdf
```

## Files

- `main.c` - opens an in memory database, runs queries, prints rows
- `pre.js` - output buffer plus shims for host globals the PDF lacks
- `runtime.js` - the console and the button handlers
- `generate.py` - hand rolled PDF writer, no dependencies
- `build.sh` - toolchain setup and compile

## Known risk points

The database is `:memory:` on purpose. A file backed database would drag
in the emscripten filesystem and a VFS, and every one of those calls is a
place where the PDF sandbox can bite.

`--memory-init-file 0` is not optional. At `-O2` and above emscripten
splits the initial memory into a separate `.mem` file and the glue tries
to load it on startup. There is no filesystem inside a PDF, so the engine
would never boot.

`-s ENVIRONMENT=shell` makes emscripten emit code that probes for `read`,
`quit` and friends. `pre.js` defines them, but if the generated engine
still throws on open, look there first: an unguarded host reference is
the most likely cause and it fails silently before `main` runs.

If the amalgamation refuses to compile, drop the `SQLITE_OMIT_*` flags one
at a time. Some of them assume a full source build rather than the
amalgamation.

Viewer support is not uniform. Chrome and Acrobat run document level
javascript. Firefox needs `pdfjs.enableScripting` and implements a smaller
API surface, so treat it as a stretch goal rather than a target.

`NeedAppearances` is set so the viewer generates field appearances itself.
Without it the fields render empty in some viewers even though the values
are correct underneath.
