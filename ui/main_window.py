import traceback
import difflib
import re

from PyQt6.QtCore import Qt, QTimer, QThread, QEvent, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QFont,
    QTextCursor,
    QTextCharFormat,
    QColor,
    QCursor,
)
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QToolBar,
    QComboBox,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QCheckBox,
    QTextEdit,
    QApplication,
    QSizePolicy,
    QScrollArea,
    QFrame,
)

from config import LOGS_DIR, OPENAI_MODEL
from core.logger import SessionLogger
from core.models import Issue, IssueResult
from engine.openai_engine import OpenAICorrectionEngine
from tracker.gazepoint_tracker import GazePointThread
from ui.editor import ClickablePlainTextEdit
from ui.overlay import GazeOverlay
from workers.correction_worker import CorrectionWorker
from workers.academic_style_worker import AcademicStyleWorker

class ClickableSuggestionCard(QFrame):
    clicked = pyqtSignal()

    def __init__(
        self,
        text: str,
        bg_color: str,
        text_color: str,
        border_color: str,
        parent=None,
    ):
        super().__init__(parent)

        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 10px;
            }}
            QFrame:hover {{
                border: 1px solid {text_color};
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)

        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.label.setFont(QFont("Segoe UI", 12))
        self.label.setStyleSheet(
            f"""
            QLabel {{
                color: {text_color};
                background: transparent;
                border: none;
                font-weight: 600;
            }}
            """
        )
        layout.addWidget(self.label)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Gaze Grammar - Main UI")
        self.resize(1400, 880)

        self.logger = SessionLogger(base_dir=LOGS_DIR)
        self.engine = OpenAICorrectionEngine(model=OPENAI_MODEL)

        self.tracker_thread = None
        self.worker_thread = None
        self.worker = None

        self._academic_worker_thread = None
        self._academic_worker = None

        self.issues = []
        self.active_issue = None

        self._is_check_running = False
        self._pending_sentence_range = None

        self.last_sentence_start = None
        self.last_sentence_end = None

        self.latched_sentence_start = None
        self.latched_sentence_end = None
        self.latched_sentence_text = ""

        self._gaze_global = QPoint(0, 0)
        self._gaze_valid_global = False

        self._prev_fixation_state = False
        self._checked_in_current_fixation = False
        self._last_fixation_sentence_key = None

        self._word_fixation_opened = False
        self._last_issue_key = None
        self._suppressed_issue_key = None

        # Temporary issue-panel timeout state
        self._issue_panel_token = 0
        self._issue_panel_timeout_ms = 4000

        self._last_result_original_sentence = ""
        self._last_result_corrected_sentence = ""
        self._last_result_issue_count = 0

        self._last_academic_tone = ""
        self._last_academic_explanation = ""
        self._last_academic_version = ""
        self._last_academic_suitable = False
        self._last_simpler_version = ""

        self._style_options_loaded = False
        self._typing_pause_passed = True

        # Cache to avoid repeated API calls for unchanged sentences
        self._sentence_cache: dict[str, dict] = {}
        self._skip_auto_style_load = False

        self._right_panel_mode = "default"  # default | summary | issue | style

        self._build_ui()
        self._connect_signals()
        self._setup_timer()

        self.show_default_panel()

        self.logger.log_event(
            "app_start",
            mode=self.cmb_mode.currentText(),
            engine=OPENAI_MODEL,
            note="Session started",
        )

    # =========================================================
    # UI
    # =========================================================
    def _build_ui(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.act_connect = QAction("Connect Tracker", self)
        self.act_disconnect = QAction("Disconnect", self)
        self.act_clear = QAction("Clear", self)

        toolbar.addAction(self.act_connect)
        toolbar.addAction(self.act_disconnect)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("Mode: "))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Manual", "Auto (Idle)", "Gaze-Triggered"])
        self.cmb_mode.setMinimumWidth(160)
        self.cmb_mode.setFont(QFont("Segoe UI", 11))
        toolbar.addWidget(self.cmb_mode)

        toolbar.addSeparator()
        toolbar.addAction(self.act_clear)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---------------- LEFT PANEL ----------------
        self.editor = ClickablePlainTextEdit()
        self.editor.setFont(QFont("Consolas", 22))
        self.editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.editor.setStyleSheet(
            """
            QPlainTextEdit {
                background: white;
                color: black;
                selection-background-color: #fff176;
                selection-color: black;
                border: 1px solid #dddddd;
            }
            """
        )

        left_container = QWidget()
        left_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)
        header_layout.setContentsMargins(8, 8, 8, 8)

        self.btn_check = QPushButton("Check sentence")
        self.btn_clear_marks = QPushButton("Clear highlights")

        self.btn_check.setMinimumHeight(46)
        self.btn_clear_marks.setMinimumHeight(46)
        self.btn_check.setMinimumWidth(160)
        self.btn_clear_marks.setMinimumWidth(170)

        self.btn_check.setFont(QFont("Segoe UI", 12))
        self.btn_clear_marks.setFont(QFont("Segoe UI", 12))

        header_layout.addWidget(self.btn_check)
        header_layout.addWidget(self.btn_clear_marks)
        header_layout.addStretch(1)

        self.chk_show_gaze = QCheckBox("Show gaze")
        self.chk_show_gaze.setChecked(True)
        self.chk_show_gaze.setFont(QFont("Segoe UI", 11))
        header_layout.addWidget(self.chk_show_gaze)

        self.chk_mouse_gaze = QCheckBox("Mouse = Gaze (Global Debug)")
        self.chk_mouse_gaze.setChecked(True)
        self.chk_mouse_gaze.setFont(QFont("Segoe UI", 11))
        header_layout.addWidget(self.chk_mouse_gaze)

        left_layout.addLayout(header_layout)
        left_layout.addWidget(self.editor)

        splitter.addWidget(left_container)

        self.overlay = GazeOverlay(self.editor)
        self.overlay.setGeometry(self.editor.viewport().rect())
        self.overlay.show()

        # ---------------- RIGHT PANEL ----------------
        right_panel = QWidget()
        right_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(10)

        box_suggestions = QGroupBox("Suggestions / Explanations")
        box_suggestions.setFont(QFont("Segoe UI", 12))
        suggestions_layout = QVBoxLayout(box_suggestions)
        suggestions_layout.setContentsMargins(8, 8, 8, 8)
        suggestions_layout.setSpacing(6)

        self.suggestion_scroll = QScrollArea()
        self.suggestion_scroll.setWidgetResizable(True)
        self.suggestion_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.suggestion_scroll.setStyleSheet(
            """
            QScrollArea {
                background: white;
                border: none;
            }
            """
        )

        self.suggestion_container = QWidget()
        self.suggestion_container.setStyleSheet("background: white;")
        self.suggestion_container.setMouseTracking(True)
        self.suggestion_container.mouseMoveEvent = self._on_panel_mouse_move

        self.suggestion_layout = QVBoxLayout(self.suggestion_container)
        self.suggestion_layout.setContentsMargins(6, 6, 6, 6)
        self.suggestion_layout.setSpacing(10)
        self.suggestion_layout.addStretch()

        self.suggestion_scroll.setWidget(self.suggestion_container)
        suggestions_layout.addWidget(self.suggestion_scroll)

        self.suggestion_scroll.verticalScrollBar().valueChanged.connect(
            lambda: self._reset_issue_timeout()
        )

        box_debug = QGroupBox("Debug")
        box_debug.setFont(QFont("Segoe UI", 12))
        debug_form = QFormLayout(box_debug)

        self.lbl_tracker = QLabel("Disconnected")
        self.lbl_gaze_xy = QLabel("- , -")
        self.lbl_valid = QLabel("False")
        self.lbl_sentence = QLabel("-")
        self.lbl_fixation = QLabel("False")
        self.lbl_fix_ms = QLabel("0")
        self.lbl_busy = QLabel("False")
        self.lbl_engine = QLabel(OPENAI_MODEL)

        debug_font = QFont("Segoe UI", 11)
        for lbl in [
            self.lbl_tracker,
            self.lbl_gaze_xy,
            self.lbl_valid,
            self.lbl_sentence,
            self.lbl_fixation,
            self.lbl_fix_ms,
            self.lbl_busy,
            self.lbl_engine,
        ]:
            lbl.setFont(debug_font)

        self.lbl_sentence.setWordWrap(True)

        debug_form.addRow("Eye tracker:", self.lbl_tracker)
        debug_form.addRow("Gaze (x,y):", self.lbl_gaze_xy)
        debug_form.addRow("Valid:", self.lbl_valid)
        debug_form.addRow("Sentence:", self.lbl_sentence)
        debug_form.addRow("Fixation:", self.lbl_fixation)
        debug_form.addRow("Fix ms:", self.lbl_fix_ms)
        debug_form.addRow("Busy:", self.lbl_busy)
        debug_form.addRow("Engine:", self.lbl_engine)

        right_layout.addWidget(box_suggestions, 3)
        right_layout.addWidget(box_debug, 1)

        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)

        left_container.setMinimumWidth(760)
        right_panel.setMinimumWidth(430)

        self.setCentralWidget(splitter)
        splitter.setSizes([930, 470])

        self.status = self.statusBar()
        self.status.showMessage("Ready.")

    def _connect_signals(self):
        self.btn_check.clicked.connect(self.check_current_sentence)
        self.btn_clear_marks.clicked.connect(self.clear_highlights)

        self.act_clear.triggered.connect(self.clear_all_text)
        self.act_connect.triggered.connect(self.connect_tracker)
        self.act_disconnect.triggered.connect(self.disconnect_tracker)

        self.chk_show_gaze.stateChanged.connect(self.toggle_gaze_draw)

        self.editor.clicked_pos.connect(self.on_editor_click)
        self.editor.textChanged.connect(self.on_editor_text_changed)

        QApplication.instance().installEventFilter(self)

    def _setup_timer(self):
        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(30)
        self.auto_timer.timeout.connect(self.auto_tick)
        self.auto_timer.start()

        self.typing_timer = QTimer(self)
        self.typing_timer.setSingleShot(True)
        self.typing_timer.setInterval(1200)
        self.typing_timer.timeout.connect(self.on_typing_pause_finished)

    # =========================================================
    # TYPING DEBOUNCE
    # =========================================================
    def on_editor_text_changed(self):
        self._typing_pause_passed = False
        self.typing_timer.start()
        self._clear_sentence_cache()

    def on_typing_pause_finished(self):
        self._typing_pause_passed = True

    # =========================================================
    # GENERAL HELPERS
    # =========================================================
    def set_busy(self, busy: bool):
        self._is_check_running = busy
        self.lbl_busy.setText(str(busy))
        self.btn_check.setEnabled(not busy)

    def toggle_gaze_draw(self):
        self.overlay.show_uncertainty = self.chk_show_gaze.isChecked()
        self.overlay.update()

    def normalize_sentence(self, text: str) -> str:
        return text.replace("\n", " ")

    def _make_sentence_cache_key(self, sentence_text: str) -> str:
        return self.normalize_sentence(sentence_text).strip()

    def _clear_sentence_cache(self):
        self._sentence_cache.clear()

    def _store_check_result_in_cache(self, sentence_key: str, result):
        entry = self._sentence_cache.get(sentence_key, {})
        entry["result"] = result
        self._sentence_cache[sentence_key] = entry

    def _store_style_result_in_cache(self, sentence_key: str, result: dict):
        entry = self._sentence_cache.get(sentence_key, {})
        entry["style_result"] = result
        self._sentence_cache[sentence_key] = entry

    def _apply_cached_style_result(self, result: dict):
        self._last_academic_tone = result.get("tone", "neutral")
        self._last_academic_suitable = result.get("suitable_for_academic", False)
        self._last_academic_version = result.get("academic_version", "")
        self._last_simpler_version = result.get("simpler_version", "")
        self._last_academic_explanation = result.get("explanation", "")
        self._style_options_loaded = True

        self.clear_suggestion_widgets()
        self.show_style_options_panel()
        self.status.showMessage("Style options loaded from cache.")

    def _schedule_return_to_summary(self):
        self._issue_panel_token += 1
        token = self._issue_panel_token
        QTimer.singleShot(
            self._issue_panel_timeout_ms,
            lambda: self._restore_summary_after_timeout(token),
        )

    def _restore_summary_after_timeout(self, token: int):
        if token != self._issue_panel_token:
            return

        if self._right_panel_mode != "issue":
            return

        if self.active_issue is not None:
            self._suppressed_issue_key = (self.active_issue.start, self.active_issue.end)

        self.active_issue = None
        self._word_fixation_opened = False
        self._last_issue_key = None
        self.show_sentence_summary_panel()

    def _reset_issue_timeout(self):
        if self._right_panel_mode == "issue":
            self._schedule_return_to_summary()

    def _on_panel_mouse_move(self, event):
        self._reset_issue_timeout()
        event.accept()

    def clear_suggestion_widgets(self):
        while self.suggestion_layout.count():
            item = self.suggestion_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.suggestion_layout.addStretch()

    def add_info_item(self, text: str, color=None, bold: bool = False):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        font = QFont("Segoe UI", 12)
        font.setBold(bold)
        label.setFont(font)

        if color is None:
            color = QColor(60, 60, 60)

        label.setStyleSheet(
            f"""
            QLabel {{
                color: {color.name()};
                background: transparent;
                border: none;
            }}
            """
        )

        self.suggestion_layout.insertWidget(self.suggestion_layout.count() - 1, label)

    def add_clickable_card(self, text: str, bg: str, fg: str, border: str, click_handler):
        card = ClickableSuggestionCard(
            text=text,
            bg_color=bg,
            text_color=fg,
            border_color=border,
        )

        def wrapped_handler():
            self._reset_issue_timeout()
            click_handler()

        card.clicked.connect(wrapped_handler)
        self.suggestion_layout.insertWidget(self.suggestion_layout.count() - 1, card)

    def add_corrected_sentence_card(self, sentence_text: str, click_handler):
        self.add_clickable_card(
            sentence_text,
            bg="#d4f8d4",
            fg="#005500",
            border="#6ecb6e",
            click_handler=click_handler,
        )

    def add_simpler_sentence_card(self, sentence_text: str, click_handler):
        self.add_clickable_card(
            sentence_text,
            bg="#e4f2ff",
            fg="#0b5cab",
            border="#b9dafc",
            click_handler=click_handler,
        )

    def add_academic_sentence_card(self, sentence_text: str, click_handler):
        self.add_clickable_card(
            sentence_text,
            bg="#ece7ff",
            fg="#4a2a8a",
            border="#c9b8ff",
            click_handler=click_handler,
        )

    def apply_suggestion(self, issue, suggestion_text: str):
        current_text = self.editor.toPlainText()
        current_fragment = current_text[issue.start:issue.end]

        if current_fragment == suggestion_text:
            self.status.showMessage("Suggestion already applied.")
            return

        self.editor.replace_range_and_keep_layout(issue.start, issue.end, suggestion_text)

        issue.word = suggestion_text
        issue.end = issue.start + len(suggestion_text)

        self.clear_highlights(clear_list=False)
        self.status.showMessage("Suggestion applied.")

    def apply_corrected_sentence(self):
        if not self._last_result_corrected_sentence:
            return

        if self.last_sentence_start is None or self.last_sentence_end is None:
            return

        self.editor.replace_range_and_keep_layout(
            self.last_sentence_start,
            self.last_sentence_end,
            self._last_result_corrected_sentence,
        )
        self.last_sentence_end = self.last_sentence_start + len(
            self._last_result_corrected_sentence
        )

        self.clear_highlights(clear_list=False)
        self.status.showMessage("Sentence replaced with corrected version.")

        self._last_result_original_sentence = self._last_result_corrected_sentence
        self._style_options_loaded = False
        self.load_style_options_after_correction()

    def apply_academic_version(self):
        if not self._last_academic_version:
            return

        if self.last_sentence_start is None or self.last_sentence_end is None:
            return

        self.editor.replace_range_and_keep_layout(
            self.last_sentence_start,
            self.last_sentence_end,
            self._last_academic_version,
        )
        self.last_sentence_end = self.last_sentence_start + len(self._last_academic_version)

        self.clear_highlights(clear_list=False)
        self.status.showMessage("Academic version applied.")

    def apply_simpler_version(self):
        if not self._last_simpler_version:
            return

        if self.last_sentence_start is None or self.last_sentence_end is None:
            return

        self.editor.replace_range_and_keep_layout(
            self.last_sentence_start,
            self.last_sentence_end,
            self._last_simpler_version,
        )
        self.last_sentence_end = self.last_sentence_start + len(self._last_simpler_version)

        self.clear_highlights(clear_list=False)
        self.status.showMessage("Simpler version applied.")

    def show_default_panel(self):
        self._right_panel_mode = "default"
        self.clear_suggestion_widgets()
        self.add_info_item("Suggestions will appear here.")
        self.add_info_item("Fixate on a sentence to check it.")

    def show_sentence_summary_panel(self):
        self._right_panel_mode = "summary"
        self.clear_suggestion_widgets()

        if not self._last_result_original_sentence:
            self.show_default_panel()
            return

        self.add_info_item(
            f"Sentence: {self._last_result_original_sentence}",
            color=QColor(60, 60, 60),
            bold=True,
        )

        if self._last_result_issue_count == 0:
            self.show_style_options_panel()
        else:
            self.add_info_item(
                "Corrected sentence:",
                color=QColor(0, 140, 0),
                bold=True,
            )
            self.add_corrected_sentence_card(
                self._last_result_corrected_sentence,
                self.apply_corrected_sentence,
            )

    def show_style_options_panel(self):
        self._right_panel_mode = "style"

        self.add_info_item(
            "Sentence is correct",
            color=QColor(0, 120, 0),
            bold=True,
        )

        self.add_info_item(
            "Improve writing style:",
            color=QColor(80, 80, 80),
            bold=True,
        )

        if self._last_simpler_version:
            self.add_info_item(
                "Simpler sentence:",
                color=QColor(11, 92, 171),
                bold=True,
            )
            self.add_simpler_sentence_card(
                self._last_simpler_version,
                self.apply_simpler_version,
            )

        if self._last_academic_version:
            self.add_info_item(
                "Academic version:",
                color=QColor(76, 42, 138),
                bold=True,
            )
            self.add_academic_sentence_card(
                self._last_academic_version,
                self.apply_academic_version,
            )

        if self._last_academic_explanation:
            self.add_info_item(
                f"Explanation: {self._last_academic_explanation}",
                color=QColor(90, 90, 90),
                bold=False,
            )

    def rebuild_suggestion_panel(self):
        if self._right_panel_mode == "issue" and self.active_issue is not None:
            self.show_issue_suggestions(self.active_issue)
            return

        if self._right_panel_mode == "style" and self._last_result_original_sentence:
            self.clear_suggestion_widgets()
            self.add_info_item(
                f"Sentence: {self._last_result_original_sentence}",
                color=QColor(60, 60, 60),
                bold=True,
            )
            self.show_style_options_panel()
            return

        if self._right_panel_mode == "summary" and self._last_result_original_sentence:
            self.show_sentence_summary_panel()
            return

        self.show_default_panel()

    def show_info(self, msg: str):
        self._right_panel_mode = "default"
        self.clear_suggestion_widgets()
        self.add_info_item(msg)

    def show_error(self, title: str, ex: Exception):
        self._right_panel_mode = "default"
        self.clear_suggestion_widgets()
        self.add_info_item(f"❌ {title}", color=QColor(180, 0, 0), bold=True)
        self.add_info_item(str(ex), color=QColor(90, 90, 90))

        tb = traceback.format_exc()
        for line in tb.splitlines()[:12]:
            self.add_info_item(line, color=QColor(90, 90, 90))

        self.status.showMessage("Error shown in Suggestions panel.")

    def update_debug(self):
        self.lbl_gaze_xy.setText(f"{self._gaze_global.x()} , {self._gaze_global.y()}")
        self.lbl_valid.setText(str(self._gaze_valid_global))

        sentence_text = self.overlay.current_sentence_text.strip()
        self.lbl_sentence.setText(sentence_text if sentence_text else "-")

        self.lbl_fixation.setText(str(self.overlay.fixation_active))

        shown_fix_ms = min(self.overlay.fixation_ms, 1500)
        self.lbl_fix_ms.setText(str(shown_fix_ms))

    # =========================================================
    # GAZE / MOUSE INPUT
    # =========================================================
    def latch_current_sentence(self):
        if (
            self.overlay.current_sentence_start is not None
            and self.overlay.current_sentence_end is not None
            and self.overlay.current_sentence_text.strip()
        ):
            self.latched_sentence_start = self.overlay.current_sentence_start
            self.latched_sentence_end = self.overlay.current_sentence_end
            self.latched_sentence_text = self.overlay.current_sentence_text

    def eventFilter(self, obj, event):
        if self.chk_mouse_gaze.isChecked() and event.type() == QEvent.Type.MouseMove:
            self.update_gaze_from_mouse()
        return super().eventFilter(obj, event)

    def update_gaze_from_mouse(self):
        global_pos = QCursor.pos()
        editor_pos = self.editor.viewport().mapFromGlobal(global_pos)

        x = editor_pos.x()
        y = editor_pos.y()
        valid = self.editor.viewport().rect().contains(editor_pos)

        self._gaze_global = global_pos
        self._gaze_valid_global = valid

        self.overlay.set_gaze(x, y, valid)

        if valid:
            self.latch_current_sentence()

        self.update_debug()

    def on_gaze_from_tracker(self, gx: float, gy: float, fixation_duration: float, valid: bool):
        if self.chk_mouse_gaze.isChecked():
            return

        screen = QApplication.primaryScreen()
        if screen is None:
            return

        screen_size = screen.size()
        global_x = int(gx * screen_size.width())
        global_y = int(gy * screen_size.height())

        self._gaze_global = QPoint(global_x, global_y)
        self._gaze_valid_global = valid

        local_pos = self.editor.viewport().mapFromGlobal(self._gaze_global)
        inside_editor = self.editor.viewport().rect().contains(local_pos)

        if inside_editor and valid:
            self.overlay.set_gaze(
                local_pos.x(),
                local_pos.y(),
                True,
                fixation_duration=fixation_duration,
            )
            self.latch_current_sentence()
        else:
            self.overlay.set_gaze(0, 0, False, fixation_duration=0.0)

        self.update_debug()

    # =========================================================
    # TRACKER
    # =========================================================
    def connect_tracker(self):
        if self.tracker_thread is not None and self.tracker_thread.isRunning():
            return

        self.tracker_thread = GazePointThread(print_raw=False)
        self.tracker_thread.status_signal.connect(self.on_tracker_status)
        self.tracker_thread.gaze_signal.connect(self.on_gaze_from_tracker)
        self.tracker_thread.start()

    def disconnect_tracker(self):
        if self.tracker_thread is not None:
            self.tracker_thread.stop()
            self.tracker_thread.wait(1000)
            self.tracker_thread = None
        self.lbl_tracker.setText("Disconnected")

    def on_tracker_status(self, msg: str):
        self.lbl_tracker.setText(msg)

    # =========================================================
    # SENTENCE AUTO-CHECK
    # =========================================================
    def handle_gaze_triggered_check(self):
        if self.cmb_mode.currentText() != "Gaze-Triggered":
            self._prev_fixation_state = self.overlay.fixation_active
            return

        if not self._typing_pause_passed:
            self._prev_fixation_state = self.overlay.fixation_active
            return

        current_fixation = self.overlay.fixation_active

        sentence_key = None
        if (
            self.overlay.current_sentence_start is not None
            and self.overlay.current_sentence_end is not None
        ):
            sentence_key = (
                self.overlay.current_sentence_start,
                self.overlay.current_sentence_end,
            )

        if current_fixation and not self._prev_fixation_state:
            self._checked_in_current_fixation = False
            self._last_fixation_sentence_key = sentence_key

        if not current_fixation:
            self._checked_in_current_fixation = False
            self._last_fixation_sentence_key = None

        if current_fixation and sentence_key != self._last_fixation_sentence_key:
            self._checked_in_current_fixation = False
            self._last_fixation_sentence_key = sentence_key

        if (
            current_fixation
            and not self._checked_in_current_fixation
            and not self._is_check_running
            and sentence_key is not None
        ):
            self.check_current_sentence()
            self._checked_in_current_fixation = True

        self._prev_fixation_state = current_fixation

    # =========================================================
    # ISSUE UNDER GAZE
    # =========================================================
    def issue_under_gaze(self):
        if not self.overlay.gaze.valid:
            return None

        cursor = self.editor.cursorForPosition(QPoint(self.overlay.gaze.x, self.overlay.gaze.y))
        pos = cursor.position()

        for issue in self.issues:
            if issue.start <= pos <= issue.end:
                return issue

        return None

    def handle_issue_fixation_open(self):
        if not self.overlay.fixation_active:
            self._word_fixation_opened = False
            self._last_issue_key = None
            return

        issue = self.issue_under_gaze()
        if issue is None:
            self._word_fixation_opened = False
            self._last_issue_key = None
            return

        issue_key = (issue.start, issue.end)

        # Prevent immediate reopening of the same issue after timeout
        if self._suppressed_issue_key == issue_key:
            return

        if issue_key != self._last_issue_key:
            self._word_fixation_opened = False
            self._last_issue_key = issue_key

        if not self._word_fixation_opened:
            self.show_issue_suggestions(issue)
            self._word_fixation_opened = True

    def handle_leave_issue_area(self):
        current_issue = self.issue_under_gaze()

        # If gaze is no longer on any issue, allow suppressed issues to open again later
        if current_issue is None:
            self._suppressed_issue_key = None

    # =========================================================
    # GRAMMAR CHECK
    # =========================================================
    def check_current_sentence(self):
        try:
            if self._is_check_running:
                return

            self._style_options_loaded = False

            text = self.editor.toPlainText()
            if not text.strip():
                self.show_info("Write some text first.")
                return

            start = self.overlay.current_sentence_start
            end = self.overlay.current_sentence_end
            sentence_raw = self.overlay.current_sentence_text

            if start is None or end is None or not sentence_raw.strip():
                start = self.latched_sentence_start
                end = self.latched_sentence_end
                sentence_raw = self.latched_sentence_text

            if start is None or end is None or not sentence_raw.strip():
                self.show_info("Move gaze/mouse over a sentence first.")
                return

            self.last_sentence_start = start
            self.last_sentence_end = end
            self._pending_sentence_range = (start, end)

            sentence_for_model = self.normalize_sentence(sentence_raw)
            sentence_key = self._make_sentence_cache_key(sentence_for_model)

            cached_entry = self._sentence_cache.get(sentence_key)
            if cached_entry is not None and cached_entry.get("result") is not None:
                self.status.showMessage("Loaded cached result.")
                self._skip_auto_style_load = cached_entry.get("style_result") is not None

                self.on_check_finished(cached_entry["result"])

                if cached_entry.get("style_result") is not None and self._last_result_issue_count == 0:
                    self._apply_cached_style_result(cached_entry["style_result"])

                self._skip_auto_style_load = False
                return

            self.logger.log_event(
                "check_sentence",
                mode=self.cmb_mode.currentText(),
                engine=OPENAI_MODEL,
                sentence_start=start,
                sentence_end=end,
                sentence_text=sentence_for_model,
            )

            self.set_busy(True)
            self.status.showMessage("Checking sentence with model...")

            self.worker_thread = QThread()
            self.worker = CorrectionWorker(self.engine, sentence_for_model)
            self.worker.moveToThread(self.worker_thread)

            self.worker_thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.on_check_finished)
            self.worker.error.connect(self.on_check_error)

            self.worker.finished.connect(self.worker_thread.quit)
            self.worker.error.connect(self.worker_thread.quit)

            self.worker_thread.finished.connect(self.worker.deleteLater)
            self.worker_thread.finished.connect(self.worker_thread.deleteLater)

            self.worker_thread.start()

        except Exception as ex:
            self.set_busy(False)
            self.show_error("Error in check_current_sentence", ex)

    def on_check_finished(self, result):
        try:
            self.set_busy(False)

            if self._pending_sentence_range is None:
                return

            start, end = self._pending_sentence_range
            self._pending_sentence_range = None

            self.clear_highlights(clear_list=False)

            self._word_fixation_opened = False
            self._last_issue_key = None

            text = self.editor.toPlainText()
            original_sentence = self.normalize_sentence(text[start:end]).strip()

            self._last_result_original_sentence = original_sentence
            self._last_result_corrected_sentence = result.corrected_sentence

            sentence_key = self._make_sentence_cache_key(original_sentence)
            if sentence_key:
                self._store_check_result_in_cache(sentence_key, result)

            fixed_issue_results = self.find_issue_offsets(original_sentence, result.issues)

            if not fixed_issue_results and result.corrected_sentence.strip() != original_sentence.strip():
                fixed_issue_results = self.build_fallback_issues_from_diff(
                    original_sentence,
                    result.corrected_sentence,
                )

            self.issues = []
            for ir in fixed_issue_results:
                if ir.start is None or ir.end is None:
                    continue

                abs_start = start + ir.start
                abs_end = start + ir.end

                if 0 <= abs_start < abs_end <= len(text):
                    self.issues.append(
                        Issue(
                            start=abs_start,
                            end=abs_end,
                            word=ir.error_text,
                            suggestions=[ir.suggestion] if ir.suggestion else [],
                            category=ir.category,
                            explanation=ir.explanation,
                        )
                    )

            self._last_result_issue_count = len(self.issues)

            self.apply_highlights(self.issues)

            if not self.issues:
                if not self._skip_auto_style_load:
                    self.load_style_options_after_correction()
            else:
                self.show_sentence_summary_panel()

            if not self.issues:
                self.status.showMessage("No issues found.")
                self._checked_in_current_fixation = True
                return

            self.status.showMessage("Sentence checked successfully.")
            self._checked_in_current_fixation = True

        except Exception as ex:
            self.show_error("Error in on_check_finished", ex)

    def on_check_error(self, err: str):
        self.set_busy(False)
        self._pending_sentence_range = None
        self._checked_in_current_fixation = False
        self.show_error("ChatGPT check error", Exception(err))

    # =========================================================
    # STYLE OPTIONS AFTER CORRECTION
    # =========================================================
    def load_style_options_after_correction(self):
        try:
            if self._is_check_running:
                return

            source_sentence = self._last_result_corrected_sentence or self._last_result_original_sentence
            source_sentence = source_sentence.strip()
            if not source_sentence:
                return

            sentence_key = self._make_sentence_cache_key(source_sentence)
            cached_entry = self._sentence_cache.get(sentence_key)

            if cached_entry is not None and cached_entry.get("style_result") is not None:
                self._apply_cached_style_result(cached_entry["style_result"])
                return

            self.set_busy(True)
            self.status.showMessage("Loading style options...")

            self._academic_worker_thread = QThread()
            self._academic_worker = AcademicStyleWorker(self.engine, source_sentence)
            self._academic_worker.moveToThread(self._academic_worker_thread)

            self._academic_worker_thread.started.connect(self._academic_worker.run)
            self._academic_worker.finished.connect(self.on_style_options_finished)
            self._academic_worker.error.connect(self.on_style_options_error)

            self._academic_worker.finished.connect(self._academic_worker_thread.quit)
            self._academic_worker.error.connect(self._academic_worker_thread.quit)

            self._academic_worker_thread.finished.connect(self._academic_worker.deleteLater)
            self._academic_worker_thread.finished.connect(self._academic_worker_thread.deleteLater)

            self._academic_worker_thread.start()

        except Exception as ex:
            self.set_busy(False)
            self.show_error("Error in load_style_options_after_correction", ex)

    def on_style_options_finished(self, result: dict):
        self.set_busy(False)

        self._last_academic_tone = result.get("tone", "neutral")
        self._last_academic_suitable = result.get("suitable_for_academic", False)
        self._last_academic_version = result.get("academic_version", "")
        self._last_simpler_version = result.get("simpler_version", "")
        self._last_academic_explanation = result.get("explanation", "")
        self._style_options_loaded = True

        source_sentence = (
            self._last_result_corrected_sentence or self._last_result_original_sentence
        ).strip()
        sentence_key = self._make_sentence_cache_key(source_sentence)
        if sentence_key:
            self._store_style_result_in_cache(sentence_key, result)

        self.clear_suggestion_widgets()
        self.show_style_options_panel()
        self.status.showMessage("Style options loaded.")

    def on_style_options_error(self, err: str):
        self.set_busy(False)
        self.show_error("Style options error", Exception(err))

    # =========================================================
    # ISSUE MAPPING HELPERS
    # =========================================================
    def find_issue_offsets(self, sentence: str, issue_results):
        used_ranges = []
        fixed = []

        for ir in issue_results:
            error_text = ir.error_text.strip()
            if not error_text:
                continue

            start = -1
            end = -1

            pattern = r"\b" + re.escape(error_text) + r"\b"
            match = re.search(pattern, sentence, flags=re.IGNORECASE)
            if match:
                start = match.start()
                end = match.end()

            if start == -1:
                start = sentence.find(error_text)
                end = start + len(error_text) if start != -1 else -1

            if start == -1:
                start = sentence.lower().find(error_text.lower())
                end = start + len(error_text) if start != -1 else -1

            if start == -1 and " " not in error_text:
                target = error_text.lower()
                for m in re.finditer(r"[A-Za-z']+", sentence):
                    if m.group(0).lower() == target:
                        start = m.start()
                        end = m.end()
                        break

            if start == -1 or end == -1:
                continue

            overlap = False
            for a, b in used_ranges:
                if not (end <= a or start >= b):
                    overlap = True
                    break

            if overlap:
                continue

            used_ranges.append((start, end))
            ir.start = start
            ir.end = end
            fixed.append(ir)

        return fixed

    def build_fallback_issues_from_diff(self, original: str, corrected: str):
        token_re = r"\w+|[^\w\s]"
        orig_matches = list(re.finditer(token_re, original))
        corr_matches = list(re.finditer(token_re, corrected))

        orig_tokens = [m.group(0) for m in orig_matches]
        corr_tokens = [m.group(0) for m in corr_matches]

        sm = difflib.SequenceMatcher(a=orig_tokens, b=corr_tokens)
        issues = []

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue

            orig_chunk = " ".join(orig_tokens[i1:i2]).strip()
            corr_chunk = " ".join(corr_tokens[j1:j2]).strip()

            if not orig_chunk:
                continue

            if i1 < len(orig_matches) and i2 > 0 and (i2 - 1) < len(orig_matches):
                start = orig_matches[i1].start()
                end = orig_matches[i2 - 1].end()
            else:
                start = None
                end = None

            issues.append(
                IssueResult(
                    error_text=orig_chunk,
                    suggestion=corr_chunk,
                    category="grammar_or_spelling",
                    explanation="Detected from difference between original and corrected sentence.",
                    start=start,
                    end=end,
                )
            )

        return issues

    # =========================================================
    # HIGHLIGHTING
    # =========================================================
    def apply_highlights(self, issues):
        selections = []

        for it in issues:
            try:
                sel = QTextEdit.ExtraSelection()

                cur = self.editor.textCursor()
                cur.setPosition(it.start)
                cur.setPosition(it.end, QTextCursor.MoveMode.KeepAnchor)

                fmt = QTextCharFormat()
                fmt.setBackground(QColor(255, 40, 40))
                fmt.setForeground(QColor(255, 255, 255))
                fmt.setFontUnderline(False)
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.NoUnderline)
                fmt.setFontWeight(900)

                sel.cursor = cur
                sel.format = fmt
                selections.append(sel)

            except Exception:
                pass

        self.editor.setExtraSelections(selections)
        self.editor.viewport().update()
        self.editor.update()

    def clear_highlights(self, clear_list=True):
        self.issues = []
        self.active_issue = None
        self._word_fixation_opened = False
        self._last_issue_key = None

        self.editor.setExtraSelections([])
        self.editor.viewport().update()
        self.editor.update()

        if clear_list:
            self.show_default_panel()

    def clear_all_text(self):
        self.editor.reset_to_prefix()
        self.clear_highlights()
        self._clear_sentence_cache()
        self.status.showMessage("Cleared.")

    # =========================================================
    # RIGHT PANEL DISPLAY
    # =========================================================
    def on_editor_click(self, pos: int):
        if not self.issues:
            return

        for issue in self.issues:
            if issue.start <= pos <= issue.end:
                self.show_issue_suggestions(issue)
                return

    def show_issue_suggestions(self, issue):
        self._right_panel_mode = "issue"
        self.active_issue = issue
        self.clear_suggestion_widgets()

        explanation_text = issue.explanation.strip() if issue.explanation else ""
        if not explanation_text:
            explanation_text = "No explanation available."

        self.add_info_item(
            f"Error word: {issue.word}",
            color=QColor(180, 0, 0),
            bold=True,
        )
        self.add_info_item(
            f"Category: {issue.category}",
            color=QColor(70, 70, 70),
            bold=True,
        )
        self.add_info_item(
            "Suggestions:",
            color=QColor(0, 80, 200),
            bold=True,
        )

        if issue.suggestions:
            for suggestion in issue.suggestions:
                self.add_clickable_card(
                    suggestion,
                    bg="#eaf2ff",
                    fg="#0056c7",
                    border="#b8cdf7",
                    click_handler=lambda s=suggestion, i=issue: self.apply_suggestion(i, s),
                )
        else:
            self.add_info_item(
                "No suggestion available.",
                color=QColor(90, 90, 90),
                bold=False,
            )

        self.add_info_item(
            f"Explanation: {explanation_text}",
            color=QColor(90, 90, 90),
            bold=False,
        )
        self.add_info_item(
            "You can now manually revise the sentence in the editor.",
            color=QColor(60, 60, 60),
            bold=False,
        )

        self.logger.log_event(
            "open_suggestions",
            mode=self.cmb_mode.currentText(),
            engine=OPENAI_MODEL,
            sentence_start=self.last_sentence_start,
            sentence_end=self.last_sentence_end,
            sentence_text=self.normalize_sentence(self.overlay.current_sentence_text),
            issue_word=issue.word,
            issue_start=issue.start,
            issue_end=issue.end,
        )

        self._schedule_return_to_summary()

    # =========================================================
    # MAIN LOOP
    # =========================================================
    def auto_tick(self):
        if self.chk_mouse_gaze.isChecked():
            self.update_gaze_from_mouse()

        self.handle_gaze_triggered_check()
        self.handle_issue_fixation_open()
        self.handle_leave_issue_area()
        self.update_debug()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay.setGeometry(self.editor.viewport().rect())
        self.overlay.update()

        QTimer.singleShot(0, self.rebuild_suggestion_panel)

    def closeEvent(self, event):
        try:
            self.logger.log_event(
                "app_close",
                mode=self.cmb_mode.currentText(),
                engine=OPENAI_MODEL,
                note="Session closed",
            )
            self.logger.close()

            if self.tracker_thread is not None:
                self.tracker_thread.stop()
                self.tracker_thread.wait(1000)

        except Exception:
            pass

        super().closeEvent(event)