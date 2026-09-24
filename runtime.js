/* Document level script #2. Runs after the engine, so by the time this
 * is parsed the SQLite banner is already sitting in SQLPDF_BUFFER.
 *
 * At the top level of a document level script `this` is the Doc object,
 * which is the only way to reach getField from inside a function later.
 */

var SQLPDF_DOC = this;

var SQLPDF_ROWS = 24;
var SQLPDF_COLS = 78;
var SQLPDF_LINES = [];

function sqlpdf_wrap(text) {
    var out = [];
    var parts = String(text).split("\n");
    for (var i = 0; i < parts.length; i++) {
        var line = parts[i];
        if (line.length === 0) { out.push(""); continue; }
        while (line.length > SQLPDF_COLS) {
            out.push(line.substring(0, SQLPDF_COLS));
            line = line.substring(SQLPDF_COLS);
        }
        out.push(line);
    }
    return out;
}

function sqlpdf_flush() {
    var i;
    for (i = 0; i < SQLPDF_BUFFER.length; i++) {
        var wrapped = sqlpdf_wrap(SQLPDF_BUFFER[i]);
        for (var j = 0; j < wrapped.length; j++) SQLPDF_LINES.push(wrapped[j]);
    }
    SQLPDF_BUFFER = [];

    while (SQLPDF_LINES.length > SQLPDF_ROWS) SQLPDF_LINES.shift();

    for (i = 0; i < SQLPDF_ROWS; i++) {
        var field = SQLPDF_DOC.getField("out" + i);
        if (field) field.value = SQLPDF_LINES[i] || "";
    }
}

function sqlpdf_echo(text) {
    SQLPDF_BUFFER.push(text);
    sqlpdf_flush();
}

function sqlpdf_run() {
    var field = SQLPDF_DOC.getField("input");
    if (!field) return;

    var sql = String(field.value);
    if (!sql.replace(/\s/g, "").length) {
        sqlpdf_echo("type a query first");
        return;
    }

    sqlpdf_echo("> " + sql);

    /* Hold the repaint until the query is done. Otherwise every printed
     * row rewrites all the output fields, which is slow for big results. */
    SQLPDF_READY = false;
    try {
        Module.ccall("sqlpdf_exec", null, ["string"], [sql]);
    } catch (e) {
        SQLPDF_BUFFER.push("engine crashed: " + e);
    }
    SQLPDF_READY = true;
    sqlpdf_flush();
}

function sqlpdf_clear() {
    SQLPDF_LINES = [];
    SQLPDF_BUFFER = [];
    sqlpdf_flush();
}

function sqlpdf_on_ready() {
    sqlpdf_flush();
}

/* generate.py wraps the engine in a try block and stores the error here.
 * Without this the console would just stay empty if the engine failed. */
if (typeof SQLPDF_BOOT_ERROR !== "undefined" && SQLPDF_BOOT_ERROR) {
    SQLPDF_BUFFER.push("engine failed to start: " + SQLPDF_BOOT_ERROR);
}

SQLPDF_READY = true;

sqlpdf_flush();
