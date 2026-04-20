"""
This file handles saving logs for the project.

We save two CSV files:

1. events log
2. gaze log
"""

import csv
import time
from pathlib import Path
from datetime import datetime


class SessionLogger:
    """
    This class creates log files and writes interaction data into them.
    """

    def __init__(self, base_dir="logs"):
        """
        Create the logs folder if it does not exist,
        and create two CSV files for the current session.
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.events_path = self.base_dir / f"session_{timestamp}_events.csv"
        self.gaze_path = self.base_dir / f"session_{timestamp}_gaze.csv"

        self._events_file = open(self.events_path, "w", newline="", encoding="utf-8")
        self._gaze_file = open(self.gaze_path, "w", newline="", encoding="utf-8")

        self.events_writer = csv.writer(self._events_file)
        self.gaze_writer = csv.writer(self._gaze_file)

        self.events_writer.writerow([
            "t_ms",
            "event",
            "mode",
            "engine",
            "sentence_start",
            "sentence_end",
            "sentence_text",
            "issue_word",
            "issue_start",
            "issue_end",
            "suggestion",
            "note",
        ])

        self.gaze_writer.writerow([
            "t_ms",
            "x_global",
            "y_global",
            "valid_global",
            "x_editor",
            "y_editor",
            "valid_editor",
            "fixation",
            "fix_ms",
        ])

        self.session_start_time = time.monotonic()

    def now_ms(self) -> int:
        """
        Return elapsed time since session start in milliseconds.
        """
        return int((time.monotonic() - self.session_start_time) * 1000)

    def log_event(self, event: str, **kwargs):
        """
        Save one event row into events CSV.
        """
        self.events_writer.writerow([
            self.now_ms(),
            event,
            kwargs.get("mode", ""),
            kwargs.get("engine", ""),
            kwargs.get("sentence_start", ""),
            kwargs.get("sentence_end", ""),
            (kwargs.get("sentence_text", "") or "").replace("\n", "\\n"),
            kwargs.get("issue_word", ""),
            kwargs.get("issue_start", ""),
            kwargs.get("issue_end", ""),
            kwargs.get("suggestion", ""),
            (kwargs.get("note", "") or "").replace("\n", "\\n"),
        ])
        self._events_file.flush()

    def log_gaze(self, **kwargs):
        """
        Save one gaze row into gaze CSV.
        """
        self.gaze_writer.writerow([
            self.now_ms(),
            kwargs.get("x_global", ""),
            kwargs.get("y_global", ""),
            kwargs.get("valid_global", ""),
            kwargs.get("x_editor", ""),
            kwargs.get("y_editor", ""),
            kwargs.get("valid_editor", ""),
            kwargs.get("fixation", ""),
            kwargs.get("fix_ms", ""),
        ])
        self._gaze_file.flush()

    def close(self):
        """
        Close both CSV files safely.
        """
        try:
            self._events_file.close()
            self._gaze_file.close()
        except Exception:
            pass