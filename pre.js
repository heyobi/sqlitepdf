/* Prepended to the emscripten output with --pre-js.
 *
 * Two jobs. First, capture everything the C side prints, because the
 * engine boots before the UI script is parsed and we must not lose the
 * banner. Second, fake the handful of host globals that emscripten's
 * shell target expects and a PDF viewer does not have.
 */

var SQLPDF_BUFFER = [];
var SQLPDF_READY = false;

var Module = typeof Module !== "undefined" ? Module : {};

Module["noExitRuntime"] = true;
Module["print"] = function (text) {
    SQLPDF_BUFFER.push(String(text));
    if (SQLPDF_READY && typeof sqlpdf_flush === "function") sqlpdf_flush();
};
Module["printErr"] = Module["print"];

Module["onRuntimeInitialized"] = function () {
    if (typeof sqlpdf_on_ready === "function") sqlpdf_on_ready();
};

/* Emscripten's shell environment probes for these. Chrome's PDF engine
 * has none of them, and an unguarded reference throws before main runs. */
if (typeof performance === "undefined") {
    performance = { now: function () { return Date.now(); } };
}
if (typeof console === "undefined") {
    console = {
        log: function (t) { Module["print"](t); },
        warn: function (t) { Module["print"](t); },
        error: function (t) { Module["print"](t); }
    };
}
/* SQLite's unix VFS asks for randomness, and emscripten answers by
 * reaching for crypto.getRandomValues, then aborting outright when it is
 * missing. Math.random is not cryptographic, but nothing here depends on
 * that: it feeds temp names and the built in random() function. */
if (typeof crypto === "undefined") {
    crypto = {
        getRandomValues: function (array) {
            for (var i = 0; i < array.length; i++) {
                array[i] = (Math.random() * 256) | 0;
            }
            return array;
        }
    };
}

/* No timers exist inside a PDF. Chrome's viewer has nothing at all and
 * Acrobat spells it app.setTimeOut, so emscripten's reference to
 * setTimeout kills the whole script before main runs. Everything here is
 * synchronous, so running the callback immediately is the right shim.
 * setInterval deliberately never fires: a repeating callback with no
 * event loop to break it would hang the viewer. */
if (typeof setTimeout === "undefined") {
    setTimeout = function (fn, delay) {
        if (typeof fn === "function") fn();
        return 0;
    };
    clearTimeout = function () {};
    setInterval = function () { return 0; };
    clearInterval = function () {};
}

/* Emscripten embeds the static data as base64 when the memory init file
 * is disabled, and reaches for atob to decode it. A PDF has no atob, and
 * the resulting throw happens before main, silently. */
if (typeof atob === "undefined") {
    atob = function (input) {
        var chars =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        var str = String(input).replace(/=+$/, "");
        var output = "";
        var bc = 0, bs = 0, buffer, idx = 0;

        for (; (buffer = str.charAt(idx++)); ) {
            buffer = chars.indexOf(buffer);
            if (buffer === -1) continue;
            bs = bc % 4 ? bs * 64 + buffer : buffer;
            if (bc++ % 4) {
                output += String.fromCharCode(255 & (bs >> ((-2 * bc) & 6)));
            }
        }
        return output;
    };
}
if (typeof btoa === "undefined") {
    btoa = function (input) {
        var chars =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        var str = String(input);
        var output = "";
        for (var block = 0, charCode, i = 0, map = chars;
             str.charAt(i | 0) || ((map = "="), i % 1);
             output += map.charAt(63 & (block >> (8 - (i % 1) * 8)))) {
            charCode = str.charCodeAt((i += 3 / 4));
            block = (block << 8) | charCode;
        }
        return output;
    };
}
if (typeof read === "undefined") {
    read = function () { throw "no file access in a pdf"; };
}
if (typeof readbuffer === "undefined") {
    readbuffer = read;
}
if (typeof quit === "undefined") {
    quit = function () {};
}
