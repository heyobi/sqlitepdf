/* sqlite.pdf - C bridge between SQLite and the PDF javascript runtime.
 *
 * Everything this file prints on stdout ends up in the PDF console,
 * because pre.js overrides Module.print. There is no filesystem in
 * play: the database lives in memory, so SQLite never touches a VFS
 * file and we avoid every I/O headache asm.js would give us.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sqlite3.h"

#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#else
#define EMSCRIPTEN_KEEPALIVE
#endif

#define MAX_COLS 12
#define MAX_ROWS 200
#define MAX_CELL 48
#define MIN_WIDTH 3
#define LINE_WIDTH 78
#define LINE_MAX 256

static sqlite3 *db = NULL;

static char headers[MAX_COLS][MAX_CELL];
static char cells[MAX_ROWS][MAX_COLS][MAX_CELL];
static int widths[MAX_COLS];

static void copy_cell(char *dst, const char *src) {
    size_t i = 0;
    if (!src) src = "NULL";
    while (src[i] && i < MAX_CELL - 1) {
        char c = src[i];
        dst[i] = (c == '\n' || c == '\r' || c == '\t') ? ' ' : c;
        i++;
    }
    /* Mark values cut here too, otherwise the column looks complete
     * because the stored copy and the column width now agree. */
    if (src[i]) dst[i - 1] = '~';
    dst[i] = '\0';
}

/* Natural width per column, then shrink the widest one repeatedly until
 * the whole row fits the console. The alternative, a fixed width, either
 * wastes space on short columns or cuts long values that would have fit. */
static void size_columns(int ncol, int nrow) {
    int i, r, total, widest;

    for (i = 0; i < ncol; i++) {
        int w = (int)strlen(headers[i]);
        for (r = 0; r < nrow; r++) {
            int len = (int)strlen(cells[r][i]);
            if (len > w) w = len;
        }
        widths[i] = w < MIN_WIDTH ? MIN_WIDTH : w;
    }

    for (;;) {
        total = 3 * (ncol - 1);
        widest = 0;
        for (i = 0; i < ncol; i++) {
            total += widths[i];
            if (widths[i] > widths[widest]) widest = i;
        }
        if (total <= LINE_WIDTH || widths[widest] <= MIN_WIDTH) break;
        widths[widest]--;
    }
}

static void print_row(int ncol, char values[][MAX_CELL]) {
    char line[LINE_MAX];
    size_t len = 0;
    int i, j;

    for (i = 0; i < ncol; i++) {
        int w = widths[i];
        int value_len = (int)strlen(values[i]);

        if (len + (size_t)w + 3 >= LINE_MAX) break;

        for (j = 0; j < w; j++)
            line[len++] = j < value_len ? values[i][j] : ' ';
        if (value_len > w) line[len - 1] = '~';

        if (i != ncol - 1) {
            line[len++] = ' ';
            line[len++] = '|';
            line[len++] = ' ';
        }
    }
    line[len] = '\0';
    printf("%s\n", line);
}

static void print_rule(int ncol) {
    char line[LINE_MAX];
    size_t len = 0;
    int i, j;

    for (i = 0; i < ncol; i++) {
        if (len + (size_t)widths[i] + 3 >= LINE_MAX) break;
        for (j = 0; j < widths[i]; j++) line[len++] = '-';
        if (i != ncol - 1) {
            line[len++] = '-';
            line[len++] = '+';
            line[len++] = '-';
        }
    }
    line[len] = '\0';
    printf("%s\n", line);
}

static void run_one(sqlite3_stmt *stmt) {
    int ncol = sqlite3_column_count(stmt);
    int nrow = 0;
    int overflow = 0;
    int rc, i;

    if (ncol > MAX_COLS) ncol = MAX_COLS;

    if (ncol == 0) {
        while (sqlite3_step(stmt) == SQLITE_ROW) {}
        printf("ok, %d change%s\n", sqlite3_changes(db),
               sqlite3_changes(db) == 1 ? "" : "s");
        return;
    }

    for (i = 0; i < ncol; i++)
        copy_cell(headers[i], sqlite3_column_name(stmt, i));

    /* Rows are buffered because column widths cannot be known until the
     * last one has been seen. The cap keeps a careless select from
     * eating the heap; the console only shows a couple dozen lines. */
    while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
        if (nrow >= MAX_ROWS) { overflow = 1; break; }
        for (i = 0; i < ncol; i++)
            copy_cell(cells[nrow][i], (const char *)sqlite3_column_text(stmt, i));
        nrow++;
    }

    size_columns(ncol, nrow);
    print_row(ncol, headers);
    print_rule(ncol);
    for (i = 0; i < nrow; i++) print_row(ncol, cells[i]);

    if (overflow)
        printf("(first %d rows, more were discarded)\n", nrow);
    else
        printf("(%d row%s)\n", nrow, nrow == 1 ? "" : "s");
}

EMSCRIPTEN_KEEPALIVE
void sqlpdf_exec(const char *sql) {
    const char *tail = sql;

    if (!db) {
        printf("database is not open\n");
        return;
    }

    while (tail && *tail) {
        sqlite3_stmt *stmt = NULL;
        const char *next = NULL;

        if (sqlite3_prepare_v2(db, tail, -1, &stmt, &next) != SQLITE_OK) {
            printf("error: %s\n", sqlite3_errmsg(db));
            return;
        }
        if (!stmt) break;

        run_one(stmt);

        if (sqlite3_finalize(stmt) != SQLITE_OK)
            printf("error: %s\n", sqlite3_errmsg(db));

        tail = next;
    }
}

EMSCRIPTEN_KEEPALIVE
const char *sqlpdf_version(void) {
    return sqlite3_libversion();
}

/* A tiny seed dataset so the document has something to show on open. */
static const char *SEED =
    "create table cities(name text, country text, pop integer);"
    "insert into cities values"
    " ('Istanbul','TR',15900000),"
    " ('Ankara','TR',5800000),"
    " ('Izmir','TR',4400000),"
    " ('Amsterdam','NL',920000),"
    " ('Nijmegen','NL',180000);";

int main(void) {
    char *err = NULL;

    if (sqlite3_open(":memory:", &db) != SQLITE_OK) {
        printf("could not open in-memory database\n");
        return 1;
    }

    if (sqlite3_exec(db, SEED, NULL, NULL, &err) != SQLITE_OK) {
        printf("seed failed: %s\n", err ? err : "unknown");
        sqlite3_free(err);
    }

    printf("sqlite %s running inside a pdf\n", sqlite3_libversion());
    printf("table 'cities' is preloaded. try:\n");
    printf("  select country, sum(pop) from cities group by country;\n");
    return 0;
}
