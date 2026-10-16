#!/usr/bin/env python3
"""Render assets/uptime.svg (daily availability, last 90 days) and the
uptime table in README.md from the files in data/."""

import argparse
import json
import re
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TZ = ZoneInfo("America/Argentina/Buenos_Aires")
DAYS = 90
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

# Layout (px)
PAD = 24
LABEL_W = 316
CELL = 6
GAP = 2
ROW = 16
PCT_W = 64
HEADER_H = 74
SECTION_H = 26

LEVELS = [("nacional", "Nacional"), ("subnacional", "Provincias y municipios")]
LEGEND = [
    ("full", "100%"),
    ("most", "90–99,9%"),
    ("some", "1–89,9%"),
    ("none", "0%"),
    ("empty", "sin datos"),
]


def load_day(portal_id, day):
    path = DATA / portal_id / f"{day.isoformat()}.json"
    if not path.exists():
        return None
    checks = json.loads(path.read_text())["checks"]
    return sum(c["up"] for c in checks), len(checks), checks


def bucket(up, total):
    if not total:
        return "empty"
    if up == total:
        return "full"
    ratio = up / total
    if ratio >= 0.9:
        return "most"
    return "some" if up else "none"


def pct(up, total):
    if not total:
        return "—"
    if up in (0, total):
        return f"{100 * up // total}%"
    # Never round a partial outage up to 100%.
    value = min(100 * up / total, 99.9)
    text = f"{value:.1f}"
    return text.replace(".", ",") + "%"


def summarize(portals, end):
    days = [end - timedelta(days=i) for i in range(DAYS - 1, -1, -1)]
    rows = []
    for portal in portals:
        cells, last_checks = [], []
        for day in days:
            loaded = load_day(portal["id"], day)
            if loaded:
                up, total, checks = loaded
                last_checks = checks
            else:
                up, total = 0, 0
            cells.append((up, total))
        rows.append({"portal": portal, "cells": cells, "last": last_checks})
    return days, rows


def label(portal):
    # Ids double as directory names, so a path is written with "_" there.
    return portal["id"].replace("_", "/")


def window(cells, n):
    up = sum(u for u, _ in cells[-n:])
    total = sum(t for _, t in cells[-n:])
    return up, total


def render_svg(days, rows, end):
    grid_w = DAYS * CELL + (DAYS - 1) * GAP
    width = PAD + LABEL_W + grid_w + PCT_W + PAD
    by_level = [(title, [r for r in rows if r["portal"]["level"] == key]) for key, title in LEVELS]
    by_level = [(t, rs) for t, rs in by_level if rs]
    grid_h = sum(SECTION_H + len(rs) * ROW for _, rs in by_level)
    axis_y = HEADER_H + grid_h + 8
    legend_y = axis_y + 34
    height = legend_y + 24

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d" '
        'font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif">',
        '<title id="t">Disponibilidad de portales de datos abiertos de Argentina</title>',
        f'<desc id="d">Porcentaje diario de chequeos exitosos por portal, últimos {DAYS} días hasta el {end.isoformat()}.</desc>',
        "<style>",
        ".bg{fill:#fcfcfb}.t1{fill:#0b0b0b}.t2{fill:#52514e}.rule{stroke:#e4e3df}",
        ".full{fill:#0ca30c}.most{fill:#fab219}.some{fill:#ec835a}.none{fill:#d03b3b}.empty{fill:#e4e3df}",
        "@media (prefers-color-scheme: dark){",
        ".bg{fill:#1a1a19}.t1{fill:#f0efec}.t2{fill:#c3c2b7}.rule{stroke:#33332f}.empty{fill:#33332f}}",
        "text{font-size:12px}.h1{font-size:16px;font-weight:600}.h2{font-size:12px;font-weight:600}",
        ".mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11.5px}",
        "</style>",
        f'<rect class="bg" width="{width}" height="{height}" rx="8"/>',
        f'<text class="t1 h1" x="{PAD}" y="{PAD + 12}">Disponibilidad de portales de datos abiertos de Argentina</text>',
        f'<text class="t2" x="{PAD}" y="{PAD + 32}">Porcentaje de chequeos exitosos por día (cada 30 min), '
        f'últimos {DAYS} días · hasta el {end.day} {MONTHS[end.month - 1]} {end.year}</text>',
    ]

    gx = PAD + LABEL_W
    px = gx + grid_w + PCT_W
    out.append(f'<text class="t2" x="{px}" y="{HEADER_H - 6}" text-anchor="end">{DAYS} días</text>')

    y = HEADER_H
    for title, level_rows in by_level:
        out.append(f'<text class="t1 h2" x="{PAD}" y="{y + 17}">{escape(title)}</text>')
        out.append(f'<line class="rule" x1="{PAD}" x2="{px}" y1="{y + SECTION_H - 3.5}" y2="{y + SECTION_H - 3.5}"/>')
        y += SECTION_H
        for row in level_rows:
            portal = row["portal"]
            cy = y + (ROW - 12) / 2
            out.append(f'<text class="t1 mono" x="{PAD}" y="{y + 12}">{escape(label(portal))}</text>')
            for i, (up, total) in enumerate(row["cells"]):
                x = gx + i * (CELL + GAP)
                out.append(f'<rect class="{bucket(up, total)}" x="{x}" y="{cy}" width="{CELL}" height="12" rx="1.5"/>')
            up, total = window(row["cells"], DAYS)
            out.append(f'<text class="t2" x="{px}" y="{y + 12}" text-anchor="end">{pct(up, total)}</text>')
            y += ROW

    # Month ticks under the grid.
    for i, day in enumerate(days):
        if day.day == 1 or i == 0:
            x = gx + i * (CELL + GAP)
            tick = f"{day.day} {MONTHS[day.month - 1]}" if i == 0 else MONTHS[day.month - 1]
            if i != 0 and (i < 6 or i > DAYS - 7):
                continue
            out.append(f'<line class="rule" x1="{x + 0.5}" x2="{x + 0.5}" y1="{axis_y - 6}" y2="{axis_y}"/>')
            out.append(f'<text class="t2" x="{x}" y="{axis_y + 14}">{tick}</text>')
    last_x = gx + grid_w
    out.append(f'<text class="t2" x="{last_x}" y="{axis_y + 14}" text-anchor="end">{end.day} {MONTHS[end.month - 1]}</text>')

    x = gx
    for cls, name in LEGEND:
        out.append(f'<rect class="{cls}" x="{x}" y="{legend_y - 10}" width="10" height="10" rx="2"/>')
        out.append(f'<text class="t2" x="{x + 15}" y="{legend_y}">{escape(name)}</text>')
        x += 15 + len(name) * 7 + 18
    out.append("</svg>")
    return "\n".join(out) + "\n"


def render_table(rows):
    lines = [
        "| Portal | Último chequeo | 7 días | 90 días |",
        "|---|---|--:|--:|",
    ]
    for row in rows:
        portal = row["portal"]
        last = row["last"][-1] if row["last"] else None
        if last is None:
            status = "—"
        elif last["up"]:
            status = "🟢 disponible"
        else:
            error = " ".join(last.get("error", "caído").split()).replace("|", "\\|")
            status = f"🔴 {error}"
        lines.append(
            f"| [{label(portal)}]({portal['url']}) | {status} | "
            f"{pct(*window(row['cells'], 7))} | {pct(*window(row['cells'], DAYS))} |"
        )
    return "\n".join(lines)


def update_readme(table, end):
    readme = ROOT / "README.md"
    text = readme.read_text()
    block = f"<!-- uptime:start -->\n_Actualizado el {end.isoformat()}._\n\n{table}\n<!-- uptime:end -->"
    text = re.sub(r"<!-- uptime:start -->.*?<!-- uptime:end -->", lambda _: block, text, flags=re.S)
    readme.write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", help="último día incluido (YYYY-MM-DD); por defecto, ayer")
    args = parser.parse_args()
    today = datetime.now(TZ).date()
    end = date.fromisoformat(args.end) if args.end else today - timedelta(days=1)

    portals = json.loads((ROOT / "portals.json").read_text())
    days, rows = summarize(portals, end)
    (ROOT / "assets" / "uptime.svg").write_text(render_svg(days, rows, end))
    update_readme(render_table(rows), end)


if __name__ == "__main__":
    main()
