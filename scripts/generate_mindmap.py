#!/usr/bin/env python3
"""Generate a standalone SVG feature mind map for barloni-gram-seva.

Mirrors the ASCII "Feature mind map" in README.md, but as a scalable image
(docs/feature-mindmap.svg) that renders inline on GitHub. Re-run this script
whenever the feature set changes:

    python scripts/generate_mindmap.py

No third-party dependencies (standard library only).
"""
from __future__ import annotations

import html
import os
import shutil
import subprocess

# --- Feature tree -----------------------------------------------------------
# Each node is (label, [children]). Keep labels short; the README holds the
# long-form descriptions. Colour comes from the top-level branch it hangs off.

TREE = (
    "barloni-gram-seva",
    [
        ("\U0001F464 Residents", [
            ("Schemes", [
                ("Browse & search directory", []),
                ("Scheme detail", []),
                ("Sources & references", []),
                ("“My schemes”", []),
                ("Eligibility dispute", []),
            ]),
            ("Account & profile", [
                ("Sign up / log in", []),
                ("One-time profile", []),
                ("Edit profile (approval)", []),
                ("Change own password", []),
                ("Share profile (WhatsApp)", []),
            ]),
            ("Documents (locker)", [
                ("Upload many at once", []),
                ("Admin approval", []),
                ("View / download", []),
                ("WhatsApp share", []),
            ]),
            ("Complaints", [
                ("File a complaint", []),
                ("Public board (anonymous)", []),
                ("Track status", []),
                ("Withdraw", []),
                ("Status notifications", []),
                ("Who’s responsible", []),
            ]),
        ]),
        ("\U0001F6E0️ Admins", [
            ("Dashboard", []),
            ("Schemes (add/edit/delete)", []),
            ("Change requests", []),
            ("Document approvals", []),
            ("Complaints", [
                ("Ward analytics", []),
            ]),
            ("Officials directory", []),
            ("Users & roles", []),
            ("Data (CSV import/export)", []),
            ("Activity log", []),
            ("Help / tour", []),
        ]),
        ("\U0001F451 Superadmin & approval engine", [
            ("Roles (user < admin < superadmin)", []),
            ("Bootstrap admin from .env", []),
            ("Approval policy (per-action)", []),
            ("Deferred execution", []),
            ("Approvals queue (N approvers)", []),
            ("Superadmin override", []),
            ("Wired actions", []),
        ]),
        ("\U0001F512 Security (internet-facing)", [
            ("Rate limiting / lockout", []),
            ("Security headers", []),
            ("Session cookies", []),
            ("Hardening", []),
            ("Access control", []),
            ("serve-prod.sh", []),
        ]),
        ("\U0001F310 White-label & deploy", [
            ("Per-village instance", []),
            ("Branding from .env", []),
            ("One-click start", []),
            ("Production launcher", []),
        ]),
        ("\U0001F9EA Quality", [
            ("Security checks", []),
            ("Functional checks", []),
            ("API e2e checks", []),
            ("~336 checks", []),
        ]),
    ],
)

# Per-branch colours (index matches order of top-level children above).
BRANCH_COLORS = [
    "#2b6cb0",  # Residents   - blue
    "#2f855a",  # Admins      - green
    "#805ad5",  # Superadmin  - purple
    "#c53030",  # Security    - red
    "#0987a0",  # White-label - teal
    "#b7791f",  # Quality     - amber
]

ROOT_COLOR = "#1a202c"

# --- Layout -----------------------------------------------------------------
COL_X = [30, 300, 620, 880]   # x per depth (left edge of node)
ROW_H = 30                     # vertical space per leaf row
PAD_X = 12                     # horizontal text padding inside a node
NODE_H = 24                    # node box height
TOP = 30                       # top margin
FONT = 13.5                    # base font size
CHAR_W = 8.1                   # approx char width for sizing boxes


def text_width(label: str) -> float:
    # Emoji render wider; count them roughly as 2 chars.
    extra = sum(1 for ch in label if ord(ch) > 0x2000)
    return (len(label) + extra) * CHAR_W


class Node:
    __slots__ = ("label", "children", "depth", "branch", "x", "y", "w")

    def __init__(self, label, children, depth, branch):
        self.label = label
        self.children = children
        self.depth = depth
        self.branch = branch
        self.x = COL_X[min(depth, len(COL_X) - 1)]
        self.y = 0.0
        self.w = text_width(label) + 2 * PAD_X


def build(node_tuple, depth, branch):
    label, kids = node_tuple
    node = Node(label, [], depth, branch)
    for i, kid in enumerate(kids):
        b = i if depth == 0 else branch
        node.children.append(build(kid, depth + 1, b))
    return node


_row = [0]  # mutable leaf counter


def assign_y(node):
    if not node.children:
        node.y = TOP + _row[0] * ROW_H
        _row[0] += 1
        return node.y
    ys = [assign_y(c) for c in node.children]
    node.y = (ys[0] + ys[-1]) / 2
    return node.y


def curve(x1, y1, x2, y2, color):
    mx = (x1 + x2) / 2
    return (f'<path d="M {x1:.1f} {y1:.1f} C {mx:.1f} {y1:.1f} {mx:.1f} {y2:.1f} '
            f'{x2:.1f} {y2:.1f}" fill="none" stroke="{color}" '
            f'stroke-width="1.6" opacity="0.55"/>')


def emit(node, parts, links):
    color = ROOT_COLOR if node.depth == 0 else BRANCH_COLORS[node.branch]
    cy = node.y
    top = cy - NODE_H / 2

    # link from this node to each child
    for c in node.children:
        links.append(curve(node.x + node.w, cy, c.x, c.y, BRANCH_COLORS[c.branch]))
        emit(c, parts, links)

    label = html.escape(node.label)
    if node.depth == 0:
        parts.append(
            f'<rect x="{node.x:.1f}" y="{top:.1f}" width="{node.w:.1f}" '
            f'height="{NODE_H}" rx="12" fill="{color}"/>'
            f'<text x="{node.x + node.w/2:.1f}" y="{cy+5:.1f}" text-anchor="middle" '
            f'font-size="{FONT+2:.0f}" font-weight="700" fill="#ffffff">{label}</text>'
        )
    elif node.depth == 1:
        parts.append(
            f'<rect x="{node.x:.1f}" y="{top:.1f}" width="{node.w:.1f}" '
            f'height="{NODE_H}" rx="12" fill="{color}"/>'
            f'<text x="{node.x + PAD_X:.1f}" y="{cy+5:.1f}" '
            f'font-size="{FONT:.1f}" font-weight="700" fill="#ffffff">{label}</text>'
        )
    elif node.children:  # internal sub-group (e.g. Residents > Schemes)
        parts.append(
            f'<rect x="{node.x:.1f}" y="{top:.1f}" width="{node.w:.1f}" '
            f'height="{NODE_H}" rx="10" fill="{color}" opacity="0.16"/>'
            f'<text x="{node.x + PAD_X:.1f}" y="{cy+5:.1f}" '
            f'font-size="{FONT:.1f}" font-weight="600" fill="{color}">{label}</text>'
        )
    else:  # leaf
        parts.append(
            f'<circle cx="{node.x+5:.1f}" cy="{cy:.1f}" r="3" fill="{color}"/>'
            f'<text x="{node.x + 14:.1f}" y="{cy+4:.1f}" '
            f'font-size="{FONT:.1f}" fill="#2d3748">{label}</text>'
        )


def main():
    root = build(TREE, 0, 0)
    assign_y(root)

    # canvas size
    height = TOP + _row[0] * ROW_H
    max_x = 0.0

    def walk(n):
        nonlocal max_x
        max_x = max(max_x, n.x + n.w)
        for c in n.children:
            walk(c)
    walk(root)
    width = max_x + 40

    parts, links = [], []
    emit(root, parts, links)

    font_stack = ("-apple-system,BlinkMacSystemFont,'Segoe UI',"
                  "'Noto Color Emoji',Roboto,Helvetica,Arial,sans-serif")
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="{font_stack}">',
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>',
        *links,   # draw links behind nodes
        *parts,
        '</svg>',
    ]

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "feature-mindmap.svg")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))
    print(f"Wrote {out_path}  ({width:.0f}x{height:.0f})")

    # Also render a PNG (README embeds the PNG since GitHub renders it inline
    # reliably). Uses a headless Chromium if one is on PATH; otherwise skips.
    png_path = os.path.join(out_dir, "feature-mindmap.png")
    if render_png(out_path, png_path, width, height):
        print(f"Wrote {png_path}")
    else:
        print("PNG skipped (no chromium/google-chrome on PATH); SVG is up to date.")


def render_png(svg_path, png_path, width, height):
    browser = next((shutil.which(b) for b in
                    ("google-chrome", "chromium", "chromium-browser", "chrome")
                    if shutil.which(b)), None)
    if not browser:
        return False
    subprocess.run(
        [browser, "--headless", "--disable-gpu", "--no-sandbox",
         "--hide-scrollbars", "--force-device-scale-factor=2",
         "--default-background-color=FFFFFFFF",
         f"--screenshot={png_path}",
         f"--window-size={width:.0f},{height:.0f}",
         "file://" + os.path.abspath(svg_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return os.path.exists(png_path)


if __name__ == "__main__":
    main()
