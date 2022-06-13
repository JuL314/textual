from __future__ import annotations

from rich.segment import Segment

from typing import cast, Generic, Iterable, TypeVar

from collections.abc import Container
from dataclasses import dataclass

from rich.console import RenderableType
from rich.padding import Padding
from rich.style import Style
from rich.text import Text, TextType

from ..widget import Widget
from ..geometry import Size
from .._lru_cache import LRUCache
from ..reactive import Reactive
from .._types import Lines
from ..scroll_view import ScrollView
from .._segment_tools import line_crop


CellType = TypeVar("CellType")


@dataclass
class Column:
    label: Text
    width: int
    visible: bool = False
    index: int = 0


@dataclass
class Cell:
    value: object


class Header(Widget):
    pass


class DataTable(ScrollView, Generic[CellType]):

    CSS = """
    DataTable Header {
        display: none;
        text-style: bold;
        background: $primary;
        color: $text-primary;
    }
    """

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.columns: list[Column] = []
        self.data: dict[int, list[CellType]] = {}
        self.row_count = 0

        self._cells: dict[int, list[Cell]] = {}

        self._cell_render_cache: dict[tuple[int, int], Lines] = LRUCache(10000)

    show_header = Reactive(True)
    fixed_rows = Reactive(1)
    fixed_columns = Reactive(1)

    def compose(self):
        yield Header()

    def _update_dimensions(self) -> None:
        max_width = sum(column.width for column in self.columns)

        self.virtual_size = Size(max_width, len(self.data) + self.show_header)

    def add_column(self, label: TextType, *, width: int = 10) -> None:
        text_label = Text.from_markup(label) if isinstance(label, str) else label
        self.columns.append(Column(text_label, width, index=len(self.columns)))
        self._update_dimensions()
        self.refresh()

    def add_row(self, *cells: CellType) -> None:
        self.data[self.row_count] = list(cells)
        self.row_count += 1
        self._update_dimensions()
        self.refresh()

    def get_row(self, y: int) -> list[CellType | Text]:

        if y == 0 and self.show_header:
            row = [column.label for column in self.columns]
            return row

        data_offset = y - 1 if self.show_header else 0
        data = self.data.get(data_offset)
        if data is None:
            return [Text() for column in self.columns]
        else:
            return data

    def _render_cell(self, y: int, column: Column) -> Lines:

        cell_key = (y, column.index)
        if cell_key not in self._cell_render_cache:
            cell = self.get_row(y)[column.index]
            lines = self.app.console.render_lines(
                Padding(cell, (0, 1)),
                self.app.console.options.update_dimensions(column.width, 1),
            )
            self._cell_render_cache[cell_key] = lines

        return self._cell_render_cache[cell_key]

    def _render_line(self, y: int, x1: int, x2: int) -> list[Segment]:

        width = self.content_region.width

        cell_segments: list[list[Segment]] = []
        rendered_width = 0
        for column in self.columns:
            lines = self._render_cell(y, column)
            rendered_width += column.width
            cell_segments.append(lines[0])

        header_style = self.query("Header").first().rich_style

        fixed: list[Segment] = sum(cell_segments[: self.fixed_columns], start=[])
        fixed_width = sum(column.width for column in self.columns[: self.fixed_columns])

        fixed = list(Segment.apply_style(fixed, header_style))

        line: list[Segment] = []
        extend = line.extend
        for segments in cell_segments:
            extend(segments)
        segments = fixed + line_crop(line, x1 + fixed_width, x2, width)
        line = Segment.adjust_line_length(segments, width)

        if y == 0 and self.show_header:
            line = list(Segment.apply_style(line, header_style))

        return line

    def render_lines(
        self, line_range: tuple[int, int], column_range: tuple[int, int]
    ) -> Lines:
        scroll_x, scroll_y = self.scroll_offset
        y1, y2 = line_range
        y1 += scroll_y
        y2 += scroll_y

        x1, x2 = column_range
        x1 += scroll_x
        x2 += scroll_x

        fixed_lines = [
            list(self._render_line(y, x1, x2)) for y in range(0, self.fixed_rows)
        ]
        lines = [list(self._render_line(y, x1, x2)) for y in range(y1, y2)]
        if fixed_lines:
            lines = fixed_lines + lines[self.fixed_rows :]

        (base_background, base_color), (background, color) = self.colors
        style = Style.from_color(color.rich_color, background.rich_color)
        lines = [list(Segment.apply_style(line, style)) for line in lines]

        return lines
