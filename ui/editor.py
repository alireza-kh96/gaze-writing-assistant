from PyQt6.QtCore import pyqtSignal, Qt, QRectF
from PyQt6.QtGui import (
    QTextCursor,
    QKeyEvent,
    QTextBlockFormat,
    QPainter,
    QColor,
    QTextOption,
)
from PyQt6.QtWidgets import QPlainTextEdit

class ClickablePlainTextEdit(QPlainTextEdit):
    clicked_pos = pyqtSignal(int)

    PREFIX = "\n   "
    GUIDE_TEXT = "Type your English sentence here..."

    def __init__(self, parent=None):
        super().__init__(parent)

        self._resetting = False
        self._protecting = False

        # Let Qt handle wrapping
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)

        # No fake outer white margin
        self.setViewportMargins(0, 0, 0, 0)

        self.set_line_spacing()
        self.reset_to_prefix()

        self.cursorPositionChanged.connect(self._protect_cursor)

    # ------------------------------------------------
    # Appearance
    # ------------------------------------------------
    def set_line_spacing(self):
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)

        fmt = QTextBlockFormat()
        fmt.setLineHeight(150, 1)

        cursor.setBlockFormat(fmt)
        cursor.clearSelection()

    # ------------------------------------------------
    # Reset
    # ------------------------------------------------
    def reset_to_prefix(self):
        self._resetting = True
        self.setPlainText(self.PREFIX)

        cursor = self.textCursor()
        cursor.setPosition(len(self.PREFIX))
        self.setTextCursor(cursor)

        self._resetting = False
        self.viewport().update()

    def is_effectively_empty(self):
        return self.toPlainText() == self.PREFIX

    # ------------------------------------------------
    # Placeholder
    # ------------------------------------------------
    def paintEvent(self, event):
        super().paintEvent(event)

        if not self.is_effectively_empty():
            return

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setPen(QColor(140, 140, 140))
        painter.setFont(self.font())

        fm = painter.fontMetrics()
        content_offset = self.contentOffset()

        # start from second line + after 3 spaces
        x = content_offset.x() + fm.horizontalAdvance("   ")
        y = content_offset.y() + (fm.height() * 2)

        rect = QRectF(
            x,
            y - fm.ascent(),
            max(200, self.viewport().width() - x - 20),
            fm.height() + 6,
        )

        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft, self.GUIDE_TEXT)
        painter.end()

    # ------------------------------------------------
    # Mouse
    # ------------------------------------------------
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked_pos.emit(self.textCursor().position())

    # ------------------------------------------------
    # Cursor protection
    # ------------------------------------------------
    def _protect_cursor(self):
        if self._resetting or self._protecting:
            return

        cursor = self.textCursor()
        min_pos = len(self.PREFIX)

        if cursor.position() < min_pos:
            self._protecting = True
            cursor.setPosition(min_pos)
            self.setTextCursor(cursor)
            self._protecting = False

    # ------------------------------------------------
    # Replacement helper for main_window
    # ------------------------------------------------
    def replace_range_and_keep_layout(self, start: int, end: int, new_text: str):
        """
        Replace a range of text, preserving the editor structure.
        New text is inserted as-is, but if the document becomes empty,
        prefix is restored.
        """
        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(new_text)

        cursor.setPosition(start + len(new_text))
        self.setTextCursor(cursor)

        if not self.toPlainText():
            self.reset_to_prefix()

    # ------------------------------------------------
    # Keyboard handling
    # ------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        cursor = self.textCursor()
        min_pos = len(self.PREFIX)

        # Never allow deleting the protected prefix
        if event.key() == Qt.Key.Key_Backspace:
            if not cursor.hasSelection() and cursor.position() <= min_pos:
                return

            if cursor.hasSelection():
                start = min(cursor.position(), cursor.anchor())
                if start < min_pos:
                    return

        if event.key() == Qt.Key.Key_Delete:
            if not cursor.hasSelection() and cursor.position() < min_pos:
                return

            if cursor.hasSelection():
                start = min(cursor.position(), cursor.anchor())
                if start < min_pos:
                    return

        # Home key should go to start of editable area on first editable line
        if event.key() == Qt.Key.Key_Home:
            block = cursor.block()
            if block.blockNumber() <= 1:
                cursor.setPosition(min_pos)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            self.setTextCursor(cursor)
            return

        super().keyPressEvent(event)

        # If user somehow removes everything, restore prefix
        if not self.toPlainText():
            self.reset_to_prefix()

        # Keep cursor out of protected area
        self._protect_cursor()