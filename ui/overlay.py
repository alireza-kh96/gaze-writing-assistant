"""
This file contains the gaze overlay widget.

The overlay is drawn on top of the text editor viewport.

It is responsible for:
- drawing the gaze circle
- finding the sentence under gaze
- detecting fixation
- drawing sentence area and fixation underline
"""

import time
from typing import Optional, Tuple

from PyQt6.QtCore import Qt, QPoint, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtWidgets import QWidget, QPlainTextEdit

from config import FIXATION_THRESHOLD_MS, GAZE_CIRCLE_RADIUS_PX
from core.models import GazeSample

class GazeOverlay(QWidget):
    """
    Transparent widget drawn on top of the editor viewport.

    It visualizes gaze and sentence focus.
    """

    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor.viewport())

        self.editor = editor

        self.gaze = GazeSample(
            x=0,
            y=0,
            timestamp=0.0,
            fixation_duration=0.0,
            valid=False,
        )

        self.show_uncertainty = True
        self.uncertainty_radius_px = GAZE_CIRCLE_RADIUS_PX

        self.current_sentence_rect: Optional[QRectF] = None
        self.current_sentence_start: Optional[int] = None
        self.current_sentence_end: Optional[int] = None
        self.current_sentence_text: str = ""

        self.fixation_threshold_ms = FIXATION_THRESHOLD_MS

        self._candidate_key: Optional[Tuple[int, int]] = None
        self._candidate_start_t: Optional[float] = None

        self.fixation_active = False
        self.fixation_ms = 0

        self.aoi_padding_top = 12
        self.aoi_padding_bottom = 12

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def reset_fixation(self):
        """
        Reset fixation state.
        """
        self.fixation_active = False
        self.fixation_ms = 0
        self._candidate_key = None
        self._candidate_start_t = None

    def set_gaze(self, x: int, y: int, valid: bool, fixation_duration: float = 0.0):
        """
        Update the current gaze position and refresh overlay state.
        """
        self.gaze = GazeSample(
            x=x,
            y=y,
            timestamp=time.monotonic(),
            fixation_duration=fixation_duration,
            valid=valid,
        )

        self._update_sentence_aoi()
        self._update_fixation()
        self.update()

    def _find_sentence_range(self, text: str, pos: int) -> Tuple[int, int]:
        """
        Find sentence boundaries around the cursor position.
        Sentences are separated by . ! ?
        """
        if not text:
            return (0, 0)

        pos = max(0, min(len(text), pos))

        start = pos
        while start > 0 and text[start - 1] not in ".!?":
            start -= 1

        end = pos
        while end < len(text) and text[end] not in ".!?":
            end += 1

        if end < len(text):
            end += 1

        while start < end and text[start] in " \n\t":
            start += 1

        return (start, end)

    def _update_sentence_aoi(self):
        """
        Detect which sentence is currently under gaze
        and compute its rectangle in the editor.
        """
        def _clear():
            self.current_sentence_rect = None
            self.current_sentence_start = None
            self.current_sentence_end = None
            self.current_sentence_text = ""

        if not self.gaze.valid:
            _clear()
            return

        text = self.editor.toPlainText()
        if not text.strip():
            _clear()
            return

        # If gaze is outside the visible viewport, ignore
        if not self.rect().contains(QPoint(self.gaze.x, self.gaze.y)):
            _clear()
            return

        gaze_cursor = self.editor.cursorForPosition(QPoint(self.gaze.x, self.gaze.y))
        pos = gaze_cursor.position()

        if pos < 0 or pos > len(text):
            _clear()
            return

        start, end = self._find_sentence_range(text, pos)

        if start >= end:
            _clear()
            return

        sentence_text = text[start:end].strip()
        if not sentence_text:
            _clear()
            return

        c1 = self.editor.textCursor()
        c1.setPosition(start)
        first_block = c1.block()

        c2 = self.editor.textCursor()
        c2.setPosition(max(start, end - 1))
        last_block = c2.block()

        rect_union = None
        block = first_block

        while block.isValid():
            geom = self.editor.blockBoundingGeometry(block)
            rect = geom.translated(self.editor.contentOffset())

            if rect_union is None:
                rect_union = QRectF(rect)
            else:
                rect_union = rect_union.united(QRectF(rect))

            if block == last_block:
                break

            block = block.next()

        if rect_union is None:
            _clear()
            return

        expanded = rect_union.adjusted(
            0,
            -self.aoi_padding_top,
            0,
            self.aoi_padding_bottom,
        )

        # Gaze must stay inside the expanded sentence AOI
        if not expanded.contains(QPointF(self.gaze.x, self.gaze.y)):
            _clear()
            return

        self.current_sentence_rect = expanded
        self.current_sentence_start = start
        self.current_sentence_end = end
        self.current_sentence_text = text[start:end]

    def _update_fixation(self):
        """
        Detect fixation based on sentence stability over time.
        """
        if self.current_sentence_start is None or self.current_sentence_end is None:
            self.reset_fixation()
            return

        key = (self.current_sentence_start, self.current_sentence_end)
        now = time.monotonic()

        if self._candidate_key != key:
            self._candidate_key = key
            self._candidate_start_t = now
            self.fixation_active = False
            self.fixation_ms = 0
            return

        if self._candidate_start_t is None:
            self._candidate_start_t = now

        elapsed_ms = int((now - self._candidate_start_t) * 1000.0)
        self.fixation_ms = elapsed_ms
        self.fixation_active = elapsed_ms >= self.fixation_threshold_ms

    def resizeEvent(self, event):
        """
        Keep overlay size equal to editor viewport size.
        """
        self.setGeometry(self.editor.viewport().rect())
        super().resizeEvent(event)

    def paintEvent(self, event):
        """
        Draw gaze circle, sentence rectangle, and fixation underline.
        """
        if not self.gaze.valid:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1) Draw gaze circle
        if self.show_uncertainty:
            pen = QPen(QColor(0, 120, 255, 140))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(QColor(0, 120, 255, 25))

            radius = self.uncertainty_radius_px
            painter.drawEllipse(QPoint(self.gaze.x, self.gaze.y), radius, radius)

        # 2) Draw sentence area
        if self.current_sentence_rect is not None:
            pen = QPen(QColor(0, 180, 0, 200))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.current_sentence_rect)

            # 3) Draw fixation underline
            if self.fixation_active:
                underline_pen = QPen(QColor(255, 165, 0, 220))
                underline_pen.setWidth(4)
                painter.setPen(underline_pen)

                y = int(self.current_sentence_rect.bottom()) - 3
                painter.drawLine(
                    int(self.current_sentence_rect.left()) + 8,
                    y,
                    int(self.current_sentence_rect.right()) - 8,
                    y,
                )

        # 4) Draw gaze center point
        center_pen = QPen(QColor(255, 0, 0, 200))
        center_pen.setWidth(3)
        painter.setPen(center_pen)
        painter.setBrush(QColor(255, 0, 0, 180))
        painter.drawEllipse(QPoint(self.gaze.x, self.gaze.y), 4, 4)