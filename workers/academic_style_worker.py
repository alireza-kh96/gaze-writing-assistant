from PyQt6.QtCore import QObject, pyqtSignal

class AcademicStyleWorker(QObject):

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, engine, sentence: str):
        super().__init__()
        self.engine = engine
        self.sentence = sentence.strip()

    def run(self):
        try:

            # safety check
            if not self.sentence:
                self.finished.emit(
                    {
                        "tone": "neutral",
                        "suitable_for_academic": False,
                        "academic_version": "",
                        "simpler_version": "",
                        "explanation": "Sentence is empty.",
                    }
                )
                return

            result = self.engine.check_academic_style(self.sentence)

            if not isinstance(result, dict):
                raise ValueError("Invalid result returned from engine.")

            # guarantee keys exist
            result.setdefault("tone", "neutral")
            result.setdefault("suitable_for_academic", False)
            result.setdefault("academic_version", "")
            result.setdefault("simpler_version", "")
            result.setdefault("explanation", "")

            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))