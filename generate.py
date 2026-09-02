#!/usr/bin/env python3
"""Build sqlite.pdf: a PDF whose form fields are a SQLite shell.

No external dependencies. The file is assembled by hand because none of
the usual libraries will emit a document level JavaScript name tree, and
that tree is the whole trick: the engine is a PDF object that the viewer
executes the moment the document opens.
"""

import argparse
import os
import zlib

PAGE_W, PAGE_H = 612, 792

OUT_ROWS = 24
ROW_H = 19
ROW_TOP = 596
PANEL_BOTTOM = ROW_TOP - OUT_ROWS * ROW_H

INPUT_RECT = [40, 660, 572, 716]
RUN_RECT = [40, 620, 130, 648]
CLEAR_RECT = [142, 620, 250, 648]


class PDF:
    def __init__(self):
        self.objects = [None]

    def reserve(self):
        self.objects.append(None)
        return len(self.objects) - 1

    def put(self, num, body):
        self.objects[num] = body
        return num

    def add(self, body):
        return self.put(self.reserve(), body)

    def stream(self, data, extra=""):
        if isinstance(data, str):
            data = data.encode("utf-8")
        packed = zlib.compress(data, 9)
        head = "<< /Length %d /Filter /FlateDecode %s>>" % (len(packed), extra)
        return self.add(head.encode("ascii") + b"\nstream\n" + packed + b"\nendstream")

    def render(self):
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0] * len(self.objects)

        for num in range(1, len(self.objects)):
            body = self.objects[num]
            if body is None:
                raise ValueError("object %d was reserved but never filled" % num)
            if isinstance(body, str):
                body = body.encode("utf-8")
            offsets[num] = len(out)
            out += b"%d 0 obj\n" % num + body + b"\nendobj\n"

        xref = len(out)
        out += b"xref\n0 %d\n" % len(self.objects)
        out += b"0000000000 65535 f \n"
        for num in range(1, len(self.objects)):
            out += b"%010d 00000 n \n" % offsets[num]
        out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % len(self.objects)
        out += b"startxref\n%d\n%%%%EOF\n" % xref
        return bytes(out)


def escape_string(text):
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def page_content():
    parts = [
        "BT /Helv 18 Tf 40 750 Td (sqlite.pdf) Tj ET",
        "BT /Helv 9 Tf 160 750 Td (a sqlite shell running inside this document) Tj ET",
        "0.6 G 0.6 w 40 740 m 572 740 l S",
        "BT /Helv 9 Tf 40 722 Td (query) Tj ET",
        "BT /Helv 9 Tf 40 604 Td (output) Tj ET",
        # the console panel, drawn behind the read only text fields
        "0.96 0.96 0.96 rg 40 %d 532 %d re f" % (PANEL_BOTTOM, ROW_TOP - PANEL_BOTTOM),
        "0.55 0.55 0.55 RG 0.6 w 40 %d 532 %d re S" % (PANEL_BOTTOM, ROW_TOP - PANEL_BOTTOM),
    ]
    return "\n".join(parts)


def button_appearance(pdf, label, rect, font_ref):
    w = rect[2] - rect[0]
    h = rect[3] - rect[1]
    text_x = max(6, (w - len(label) * 5.5) / 2)
    content = (
        "q 0.87 0.87 0.9 rg 0 0 %g %g re f "
        "0.25 0.25 0.25 RG 0.7 w 0.35 0.35 %g %g re S "
        "BT /Helv 11 Tf 0 g %g %g Td (%s) Tj ET Q"
        % (w, h, w - 0.7, h - 0.7, text_x, h / 2 - 4, escape_string(label))
    )
    extra = (
        "/Type /XObject /Subtype /Form /BBox [0 0 %g %g] "
        "/Resources << /Font << /Helv %d 0 R >> >> " % (w, h, font_ref)
    )
    return pdf.stream(content, extra)


def build(engine_js, runtime_js):
    pdf = PDF()

    catalog = pdf.reserve()
    pages = pdf.reserve()
    page = pdf.reserve()

    contents = pdf.stream(page_content())
    helv = pdf.add(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    cour = pdf.add(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"
    )

    # The viewer swallows exceptions thrown by document level scripts, so a
    # broken engine looks identical to a missing one. Wrapping it keeps the
    # failure visible. A try block does not create a scope for var or for
    # function declarations, so every global the glue defines still lands
    # where the runtime script expects it.
    engine_js = (
        "var SQLPDF_BOOT_ERROR = null;\ntry {\n"
        + engine_js
        + "\n} catch (e) {\n"
        "  SQLPDF_BOOT_ERROR = String((e && e.message) ? e.message : e);\n}\n"
    )

    engine_stream = pdf.stream(engine_js)
    engine_action = pdf.add("<< /S /JavaScript /JS %d 0 R >>" % engine_stream)
    runtime_stream = pdf.stream(runtime_js)
    runtime_action = pdf.add("<< /S /JavaScript /JS %d 0 R >>" % runtime_stream)

    fields = []

    fields.append(
        pdf.add(
            "<< /Type /Annot /Subtype /Widget /FT /Tx /T (input) /Ff 4096 "
            "/Rect [%d %d %d %d] /DA (/Cour 9 Tf 0 g) /F 4 /P %d 0 R "
            "/V (select country, sum\\(pop\\) from cities group by country;) "
            "/MK << /BG [0.97 0.97 0.97] /BC [0.55 0.55 0.55] >> >>"
            % (INPUT_RECT[0], INPUT_RECT[1], INPUT_RECT[2], INPUT_RECT[3], page)
        )
    )

    for name, label, rect, js in (
        ("run", "Run query", RUN_RECT, "sqlpdf_run();"),
        ("clear", "Clear output", CLEAR_RECT, "sqlpdf_clear();"),
    ):
        ap = button_appearance(pdf, label, rect, helv)
        fields.append(
            pdf.add(
                "<< /Type /Annot /Subtype /Widget /FT /Btn /Ff 65536 /T (%s) "
                "/Rect [%d %d %d %d] /F 4 /P %d 0 R /AP << /N %d 0 R >> "
                "/DA (/Helv 11 Tf 0 g) "
                "/MK << /BG [0.87 0.87 0.9] /BC [0.25 0.25 0.25] /CA (%s) >> "
                "/AA << /U << /S /JavaScript /JS (%s) >> >> >>"
                % (name, rect[0], rect[1], rect[2], rect[3], page, ap,
                   escape_string(label), escape_string(js))
            )
        )

    for i in range(OUT_ROWS):
        top = ROW_TOP - i * ROW_H
        fields.append(
            pdf.add(
                "<< /Type /Annot /Subtype /Widget /FT /Tx /T (out%d) /Ff 1 "
                "/Rect [40 %d 572 %d] /DA (/Cour 9 Tf 0 g) /F 4 /P %d 0 R "
                "/V () >>" % (i, top - ROW_H, top, page)
            )
        )

    annots = " ".join("%d 0 R" % f for f in fields)

    pdf.put(
        page,
        "<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
        "/Resources << /Font << /Helv %d 0 R /Cour %d 0 R >> >> /Annots [%s] >>"
        % (pages, PAGE_W, PAGE_H, contents, helv, cour, annots),
    )
    pdf.put(pages, "<< /Type /Pages /Kids [%d 0 R] /Count 1 >>" % page)
    pdf.put(
        catalog,
        "<< /Type /Catalog /Pages %d 0 R "
        "/AcroForm << /Fields [%s] /NeedAppearances true /DA (/Helv 0 Tf 0 g) "
        "/DR << /Font << /Helv %d 0 R /Cour %d 0 R >> >> >> "
        "/Names << /JavaScript << /Names [(a_engine) %d 0 R (b_runtime) %d 0 R] >> >> >>"
        % (pages, annots, helv, cour, engine_action, runtime_action),
    )

    return pdf.render()


DUMMY_ENGINE = """
var SQLPDF_BUFFER = [];
var SQLPDF_READY = false;
var Module = { ccall: function () { SQLPDF_BUFFER.push("dummy engine, no sqlite here"); } };
SQLPDF_BUFFER.push("dummy engine loaded");
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", default="out/sqlite.js")
    parser.add_argument("--runtime", default="runtime.js")
    parser.add_argument("--output", default="out/sqlite.pdf")
    parser.add_argument("--dummy", action="store_true",
                        help="build the shell without the compiled engine")
    args = parser.parse_args()

    if args.dummy:
        engine = DUMMY_ENGINE
    else:
        with open(args.engine, "r", encoding="utf-8", errors="replace") as handle:
            engine = handle.read()

    with open(args.runtime, "r", encoding="utf-8") as handle:
        runtime = handle.read()

    data = build(engine, runtime)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "wb") as handle:
        handle.write(data)

    print("wrote %s (%.1f KB)" % (args.output, len(data) / 1024.0))


if __name__ == "__main__":
    main()
