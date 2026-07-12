#!/usr/bin/env python3
"""Export labels/MIA_GoldenLabels_v1.xlsx (sheet GoldenLabels) to
labels/golden_labels.csv (UTF-8), then lint the CSV against the frozen v1 rubric.

Run from anywhere:  python3 scripts/lint_golden_labels.py

Lint rules (exactly the four requested):
  1. Terminal_State is one of the five allowed states.
  2. Failure_Code is blank or only comma-separated codes from the rubric registry
     (valid = entries with a `code:` key under failure_codes.outcome/process; nursery
     candidate_codes and unknown tokens are violations).
  3. Every criterion column identity..kb_fidelity is Pass, Fail, or NA.
  4. Every Call_ID resolves to transcripts/raw/<Call_ID>.txt.
"""
import csv
import os
import re
import zipfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = os.path.join(ROOT, "labels", "MIA_GoldenLabels_v1.xlsx")
CSV_OUT = os.path.join(ROOT, "labels", "golden_labels.csv")
RUBRIC = os.path.join(ROOT, "rubric", "rubric.yaml")
RAW_DIR = os.path.join(ROOT, "transcripts", "raw")
SHEET = "GoldenLabels"

TERMINAL_STATES = {
    "Resolved by Mia", "Transferred", "Callback captured",
    "Declined & redirected", "Failed",
}
VERDICTS = {"Pass", "Fail", "NA"}
CRITERION_COLS = ["identity", "intent_class", "terminal_correct", "scope",
                  "dropoff", "transfer_hygiene", "callback_quality", "kb_fidelity"]

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def read_sheet_openpyxl(path, sheet):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    rows = [["" if v is None else str(v) for v in r]
            for r in ws.iter_rows(values_only=True)]
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]


def read_sheet_stdlib(path, sheet):
    """xlsx = zip of XML; this workbook stores strings inline (no sharedStrings)."""
    z = zipfile.ZipFile(path)
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {rel.get("Id"): rel.get("Target") for rel in rels}
    target = None
    for s in wb.find(M + "sheets"):
        if s.get("name") == sheet:
            target = relmap[s.get(R + "id")]
            break
    if target is None:
        raise SystemExit("sheet %r not found in workbook" % sheet)
    target = target.lstrip("/")
    if not target.startswith("xl/"):
        target = "xl/" + target

    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(M + "t"))
                  for si in sst.findall(M + "si")]

    def col_idx(ref):
        c = 0
        for ch in re.match(r"([A-Z]+)", ref).group(1):
            c = c * 26 + (ord(ch) - 64)
        return c - 1

    def cell_text(c):
        t = c.get("t")
        if t == "inlineStr":
            is_ = c.find(M + "is")
            return "".join(n.text or "" for n in is_.iter(M + "t")) if is_ is not None else ""
        v = c.find(M + "v")
        if v is None:
            return ""
        if t == "s":
            return shared[int(v.text)]
        return v.text or ""

    root = ET.fromstring(z.read(target))
    rows = []
    for r in root.find(M + "sheetData").findall(M + "row"):
        cells, maxc = {}, -1
        for c in r.findall(M + "c"):
            i = col_idx(c.get("r"))
            cells[i] = cell_text(c)
            maxc = max(maxc, i)
        rows.append([cells.get(i, "") for i in range(maxc + 1)])
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]


def read_sheet(path, sheet):
    try:
        import openpyxl  # noqa: F401
        return read_sheet_openpyxl(path, sheet), "openpyxl"
    except ImportError:
        return read_sheet_stdlib(path, sheet), "stdlib(zipfile+ElementTree)"


def load_registry(path):
    """Valid codes = every `- code:` under failure_codes, scoped BEFORE `nursery:`."""
    text = open(path, encoding="utf-8").read()
    if "failure_codes:" not in text:
        raise SystemExit("no failure_codes section in rubric")
    fc = text.split("failure_codes:", 1)[1]
    before_nursery = re.split(r"^\s*nursery:", fc, flags=re.M)[0]
    return re.findall(r"^\s*-\s*code:\s*([A-Z_]+)", before_nursery, re.M)


def report(title, viols, fmt):
    print("\n%s" % title)
    if not viols:
        print("  ✓ No violations")
        return
    for excel_row, cid, extra in viols:
        print("  ✗ row %-2d · %-20s · %s" % (excel_row, cid, fmt % extra))


def main():
    grid, backend = read_sheet(XLSX, SHEET)
    header, data = grid[0], grid[1:]

    with open(CSV_OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)  # QUOTE_MINIMAL: quotes only cells with , " or newline
        w.writerow(header)
        w.writerows(data)
    print("Wrote %s  (%d data rows, %d cols; reader=%s)"
          % (os.path.relpath(CSV_OUT, ROOT), len(data), len(header), backend))

    registry = set(load_registry(RUBRIC))
    print("Loaded registry from rubric.yaml: %d codes -> %s"
          % (len(registry), ", ".join(sorted(registry))))

    ts_i = header.index("Terminal_State")
    fc_i = header.index("Failure_Code")
    cid_i = header.index("Call_ID")
    crit_i = [header.index(c) for c in CRITERION_COLS]
    raw_files = set(os.listdir(RAW_DIR)) if os.path.isdir(RAW_DIR) else set()

    v1, v2, v3, v4 = [], [], [], []
    for n, row in enumerate(data):
        excel_row = n + 2  # header is row 1
        cid = row[cid_i].strip()
        if row[ts_i].strip() not in TERMINAL_STATES:
            v1.append((excel_row, cid, row[ts_i].strip()))
        fc = row[fc_i].strip()
        if fc:
            for tok in fc.split(","):
                tok = tok.strip()
                if tok and tok not in registry:
                    v2.append((excel_row, cid, tok))
        for name, ci in zip(CRITERION_COLS, crit_i):
            val = row[ci].strip()
            if val not in VERDICTS:
                v3.append((excel_row, cid, "%s=%r" % (name, val)))
        if cid + ".txt" not in raw_files:
            v4.append((excel_row, cid, cid + ".txt"))

    print("\n" + "=" * 72)
    print("LINT REPORT — labels/golden_labels.csv  (%d data rows, Excel rows 2–%d)"
          % (len(data), len(data) + 1))
    print("=" * 72)
    report("Rule 1 — Terminal_State in allowed set:", v1, "invalid Terminal_State=%r")
    report("Rule 2 — Failure_Code tokens in registry:", v2, "unknown code %r")
    report("Rule 3 — criterion cells in {Pass,Fail,NA}:", v3, "%s")
    report("Rule 4 — Call_ID has a transcript file:", v4, "missing %s")
    print("\nTOTAL VIOLATIONS: %d" % (len(v1) + len(v2) + len(v3) + len(v4)))

    print("\n" + "=" * 72)
    print("FIRST 3 ROWS OF THE CSV (header + 3 data rows, re-read from disk)")
    print("=" * 72)
    with open(CSV_OUT, encoding="utf-8", newline="") as f:
        allrows = list(csv.reader(f))
    for ri in range(min(4, len(allrows))):
        label = "HEADER (row 1)" if ri == 0 else "DATA row %d" % (ri + 1)
        print("\n[%s]" % label)
        for col, val in zip(allrows[0], allrows[ri]):
            shown = val if len(val) <= 90 else val[:90] + " …(%d chars total)" % len(val)
            print("  %-16s = %s" % (col, shown))


if __name__ == "__main__":
    main()
