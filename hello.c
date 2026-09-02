/* Smoke test. Nothing to do with SQLite: this exists only to prove that
 * emscripten's glue code survives inside a PDF viewer. If this prints
 * and the button works, the plumbing is fine and any later failure is
 * SQLite's problem, not the toolchain's.
 */

#include <stdio.h>
#include <string.h>
#include <emscripten.h>

EMSCRIPTEN_KEEPALIVE
void sqlpdf_exec(const char *sql) {
    printf("engine received %d bytes\n", (int)strlen(sql));
    printf("echo: %s\n", sql);
}

EMSCRIPTEN_KEEPALIVE
const char *sqlpdf_version(void) {
    return "hello";
}

int main(void) {
    printf("emscripten glue is alive inside the pdf\n");
    printf("press run to send a string through ccall\n");
    return 0;
}
