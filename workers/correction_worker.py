# workers/correction_worker.py

"""
This file defines a worker object that runs sentence correction
in a background thread.

Why?
Because API calls can take time, and we do not want the UI to freeze.
"""

from PyQt6.QtCore import QObject, pyqtSignal

from engine.openai_engine import OpenAICorrectionEngine
from core.models import CorrectionResult

class CorrectionWorker(QObject):
    """
    Worker object that sends one sentence to the language model
    in a background thread.
    """

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, engine: OpenAICorrectionEngine, sentence: str):
        """
        Store the engine and the sentence to be checked.
        """
        super().__init__()
        self.engine = engine
        self.sentence = sentence.strip()

    def run(self):
        """
        Run the correction request.
        If successful, emit 'finished'.
        If an error happens, emit 'error'.
        """
        try:
            if not self.sentence:
                self.finished.emit(
                    CorrectionResult(
                        original_sentence="",
                        corrected_sentence="",
                        issues=[],
                    )
                )
                return

            result: CorrectionResult = self.engine.correct_sentence(self.sentence)
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))