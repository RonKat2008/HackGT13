"""Flow a workshop paper onto letter pages.

Locked sentences are the lines the audit must still read. They stay on one
page. Surrounding prose is ordinary body text.
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
MARGIN_X = 64
TOP_Y = 68
BOTTOM_Y = 64
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN_X
BODY = "tiro"
BODY_BOLD = "tibo"
BODY_ITALIC = "tiit"
BODY_SIZE = 10.5
BODY_LEADING = 14
HEADING_SIZE = 13
TITLE_SIZE = 18
CELL_HEIGHT = 18
COLUMN_WIDTHS = (300, 110)

Block = tuple[str, object]


def prose(text: str) -> Block:
    cleaned = " ".join(text.split())
    if re.search(r"\d", cleaned):
        raise ValueError(f"prose must not contain a digit: {cleaned[:80]}")
    if re.search(
        r"\bwe show\b|\bwe demonstrate\b|\bsignificantly\b|\brobust\b|\bconverges\b|"
        r"\bimproves\b|\boutperforms\b|\bstays under\b|\blowers\b|\bis (?:more|less)\b",
        cleaned,
        re.I,
    ):
        raise ValueError(f"prose would become a semantic claim: {cleaned[:80]}")
    if re.search(r"\([A-Z][A-Za-z\-']+(?: et al\.)?,? ?\d{4}\)", cleaned):
        raise ValueError(f"prose would become a citation claim: {cleaned[:80]}")
    return ("prose", cleaned)


def lock(text: str) -> Block:
    return ("lock", " ".join(text.split()))


class Document:
    def __init__(self, running_head: str) -> None:
        self.running_head = running_head
        self.doc = fitz.open()
        self.page: fitz.Page | None = None
        self.y = TOP_Y
        self.page_no = 0

    def save(self, path: Path) -> Path:
        page_no = 0
        for page in self.doc:
            page_no += 1
            page.draw_line(
                fitz.Point(MARGIN_X, PAGE_HEIGHT - 46),
                fitz.Point(PAGE_WIDTH - MARGIN_X, PAGE_HEIGHT - 46),
                color=(0.75, 0.72, 0.66),
                width=0.4,
            )
            page.insert_text(
                (MARGIN_X, PAGE_HEIGHT - 32),
                self.running_head,
                fontsize=8,
                fontname=BODY_ITALIC,
                color=(0.35, 0.32, 0.28),
            )
            page.insert_text(
                (PAGE_WIDTH - MARGIN_X - 12, PAGE_HEIGHT - 32),
                str(page_no),
                fontsize=8,
                fontname=BODY,
                color=(0.35, 0.32, 0.28),
            )
        self.doc.save(path, garbage=3, deflate=True)
        pages = self.doc.page_count
        self.doc.close()
        return path

    def _new_page(self) -> None:
        self.page = self.doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        self.page_no += 1
        self.y = TOP_Y
        if self.page_no > 1:
            self.page.insert_text(
                (MARGIN_X, 40),
                self.running_head,
                fontsize=8,
                fontname=BODY_ITALIC,
                color=(0.35, 0.32, 0.28),
            )
            self.page.draw_line(
                fitz.Point(MARGIN_X, 48),
                fitz.Point(PAGE_WIDTH - MARGIN_X, 48),
                color=(0.75, 0.72, 0.66),
                width=0.4,
            )
            self.y = 68

    def _room(self, need: float) -> None:
        if self.page is None or self.y + need > PAGE_HEIGHT - BOTTOM_Y:
            self._new_page()

    def _wrap(self, text: str, size: float) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            width = fitz.get_text_length(candidate, fontname=BODY, fontsize=size)
            if current and width > TEXT_WIDTH:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines or [""]

    def _write(self, text: str, size: float, leading: float, font: str, gap: float = 0) -> None:
        for line in self._wrap(text, size):
            self._room(leading)
            assert self.page is not None
            self.page.insert_text((MARGIN_X, self.y), line, fontsize=size, fontname=font)
            self.y += leading
        self.y += gap

    def title(self, text: str) -> None:
        self._new_page()
        self._write(text, TITLE_SIZE, TITLE_SIZE + 6, BODY_BOLD, gap=4)

    def authors(self, text: str) -> None:
        self._write(text, 11, 15, BODY_ITALIC, gap=0)

    def affiliation(self, text: str) -> None:
        self._write(text, 9, 12, BODY, gap=8)
        assert self.page is not None
        self.page.draw_line(
            fitz.Point(MARGIN_X, self.y),
            fitz.Point(PAGE_WIDTH - MARGIN_X, self.y),
            color=(0.2, 0.18, 0.15),
            width=0.6,
        )
        self.y += 16

    def heading(self, text: str) -> None:
        self._room(HEADING_SIZE + 18)
        self.y += 8
        self._write(text, HEADING_SIZE, HEADING_SIZE + 6, BODY_BOLD, gap=4)

    def paragraph(self, text: str) -> None:
        self._write(text, BODY_SIZE, BODY_LEADING, BODY, gap=8)

    def locked(self, text: str) -> None:
        lines = self._wrap(text, BODY_SIZE)
        need = BODY_LEADING * len(lines) + 8
        self._room(need)
        assert self.page is not None
        for line in lines:
            self.page.insert_text((MARGIN_X, self.y), line, fontsize=BODY_SIZE, fontname=BODY)
            self.y += BODY_LEADING
        self.y += 8

    def caption(self, text: str) -> None:
        self._write(text, 9, 12, BODY_ITALIC, gap=4)

    def table(self, rows: list[tuple[str, str]]) -> None:
        need = CELL_HEIGHT * len(rows) + 8
        self._room(need)
        assert self.page is not None
        x0 = MARGIN_X
        x1 = x0 + COLUMN_WIDTHS[0]
        x2 = x1 + COLUMN_WIDTHS[1]
        for first, second in rows:
            y1 = self.y + CELL_HEIGHT
            self.page.draw_rect(fitz.Rect(x0, self.y, x1, y1), color=(0.15, 0.13, 0.1), width=0.6)
            self.page.draw_rect(fitz.Rect(x1, self.y, x2, y1), color=(0.15, 0.13, 0.1), width=0.6)
            self.page.insert_text(
                (x0 + 6, y1 - 5),
                _row_text(first, second),
                fontsize=BODY_SIZE,
                fontname=BODY,
            )
            self.y = y1
        self.y += 10

    def reference(self, text: str) -> None:
        lines = self._wrap(text, 9)
        self._room(12 * len(lines) + 4)
        assert self.page is not None
        for index, line in enumerate(lines):
            x = MARGIN_X if index == 0 else MARGIN_X + 14
            self.page.insert_text((x, self.y), line, fontsize=9, fontname=BODY)
            self.y += 12
        self.y += 4


def _row_text(first: str, second: str) -> str:
    space = fitz.get_text_length(" ", fontname=BODY, fontsize=BODY_SIZE)
    used = fitz.get_text_length(first, fontname=BODY, fontsize=BODY_SIZE)
    gap = COLUMN_WIDTHS[0] - used
    return first + " " * max(1, round(gap / space)) + second


def render(path: Path, running_head: str, blocks: list[Block]) -> Path:
    document = Document(running_head)
    for kind, payload in blocks:
        if kind == "title":
            document.title(str(payload))
        elif kind == "authors":
            document.authors(str(payload))
        elif kind == "affiliation":
            document.affiliation(str(payload))
        elif kind == "heading":
            document.heading(str(payload))
        elif kind == "prose":
            document.paragraph(str(payload))
        elif kind == "lock":
            document.locked(str(payload))
        elif kind == "caption":
            document.caption(str(payload))
        elif kind == "table":
            document.table(list(payload))  # type: ignore[arg-type]
        elif kind == "reference":
            document.reference(str(payload))
        else:
            raise ValueError(kind)
    return document.save(path)
