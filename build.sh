#!/usr/bin/env bash
# Build the javascript engine, then wrap it in a PDF.
#
# A PDF viewer's javascript engine has no WebAssembly, so the C code has
# to come out as plain javascript. Two toolchains can do that:
#
#   emscripten 1.x  fastcomp backend, emits real asm.js
#   emscripten 2.x+ wasm2js, compiles the wasm back down to javascript
#
# The second is the maintained one. This script detects which you have
# and picks the matching flags, because several of them were renamed.

set -euo pipefail

TARGET="${1:-sqlite}"

SQLITE_URL="https://sqlite.org/2025/sqlite-amalgamation-3500400.zip"

ROOT="$(cd "$(dirname "$0")" && pwd)"
BUILD="${ROOT}/build"
OUT="${ROOT}/out"

mkdir -p "${BUILD}" "${OUT}"

for required in pre.js runtime.js generate.py; do
    if [ ! -f "${ROOT}/${required}" ]; then
        echo "missing ${required}: every source file must sit next to build.sh" >&2
        exit 1
    fi
done

if ! command -v emcc >/dev/null 2>&1; then
    echo "emcc not on PATH: source emsdk_env.sh first" >&2
    exit 1
fi

EMCC_MAJOR="$(emcc --version | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 | cut -d. -f1)"
echo "emscripten major version: ${EMCC_MAJOR}"

if [ "${EMCC_MAJOR}" -ge 2 ]; then
    # wasm2js path. SINGLE_FILE inlines everything, which matters because
    # anything loaded as a side file cannot be reached from inside a PDF.
    BACKEND_FLAGS=(
        -s WASM=0
        -s SINGLE_FILE=1
        -s EXPORTED_RUNTIME_METHODS='["ccall","cwrap"]'
    )
else
    # fastcomp path. Without this the initial memory lands in a .mem file
    # that the glue tries to read at startup, and there is no filesystem.
    BACKEND_FLAGS=(
        -s WASM=0
        --memory-init-file 0
        -s EXTRA_EXPORTED_RUNTIME_METHODS='["ccall","cwrap"]'
    )
fi

if [ "${TARGET}" = "hello" ]; then
    SOURCES=("${ROOT}/hello.c")
    INCLUDES=()
    SQLITE_FLAGS=()
    NAME="hello"
else
    if [ ! -f "${BUILD}/sqlite/sqlite3.c" ]; then
        mkdir -p "${BUILD}/sqlite"
        if [ ! -f "${BUILD}/sqlite/sqlite.zip" ]; then
            curl -L -o "${BUILD}/sqlite/sqlite.zip" "${SQLITE_URL}"
        fi
        # Extracted with python rather than unzip: python is already a hard
        # requirement here and unzip is not installed everywhere.
        python3 - "${BUILD}/sqlite" <<'EXTRACT'
import os, sys, zipfile

target = sys.argv[1]
with zipfile.ZipFile(os.path.join(target, "sqlite.zip")) as archive:
    for member in archive.namelist():
        name = os.path.basename(member)
        if not name:
            continue
        with archive.open(member) as src:
            with open(os.path.join(target, name), "wb") as dst:
                dst.write(src.read())
print("extracted the amalgamation")
EXTRACT
    fi
    SOURCES=("${BUILD}/sqlite/sqlite3.c" "${ROOT}/main.c")
    INCLUDES=(-I "${BUILD}/sqlite")
    NAME="sqlite"
    # If the amalgamation refuses to compile, drop these one at a time.
    SQLITE_FLAGS=(
        -DSQLITE_THREADSAFE=0
        -DSQLITE_OMIT_LOAD_EXTENSION
        -DSQLITE_OMIT_DEPRECATED
        -DSQLITE_OMIT_SHARED_CACHE
        -DSQLITE_OMIT_UTF16
        -DSQLITE_OMIT_PROGRESS_CALLBACK
        -DSQLITE_DEFAULT_MEMSTATUS=0
        -DSQLITE_DQS=0
        -DSQLITE_TEMP_STORE=3
        -DSQLITE_MAX_EXPR_DEPTH=0
    )
fi

cd "${ROOT}"

emcc \
    -O3 \
    "${BACKEND_FLAGS[@]}" \
    -s LEGACY_VM_SUPPORT=1 \
    -s ENVIRONMENT=shell \
    -s TOTAL_MEMORY=67108864 \
    -s ALLOW_MEMORY_GROWTH=0 \
    -s NO_EXIT_RUNTIME=1 \
    -s EXPORTED_FUNCTIONS='["_main","_sqlpdf_exec","_sqlpdf_version","_malloc","_free"]' \
    -s ASSERTIONS=0 \
    --closure 0 \
    ${SQLITE_FLAGS[@]+"${SQLITE_FLAGS[@]}"} \
    ${INCLUDES[@]+"${INCLUDES[@]}"} \
    --pre-js "${ROOT}/pre.js" \
    "${SOURCES[@]}" \
    -o "${OUT}/${NAME}.js"

echo "engine: $(du -h "${OUT}/${NAME}.js" | cut -f1)"

python3 "${ROOT}/generate.py" \
    --engine "${OUT}/${NAME}.js" \
    --runtime "${ROOT}/runtime.js" \
    --output "${OUT}/${NAME}.pdf"
