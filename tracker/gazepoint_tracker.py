"""
This file handles connection to the Gazepoint eye tracker.

It:
- connects to the Gazepoint socket server
- reads incoming XML records
- extracts gaze-related values
- emits them to the UI
"""

import socket
import xml.etree.ElementTree as ET

from PyQt6.QtCore import QThread, pyqtSignal

from config import GAZEPOINT_HOST, GAZEPOINT_PORT

class GazePointThread(QThread):
    """
    Background thread for receiving gaze data from Gazepoint.
    """

    gaze_signal = pyqtSignal(float, float, float, bool)
    status_signal = pyqtSignal(str)

    def __init__(
        self,
        host: str = GAZEPOINT_HOST,
        port: int = GAZEPOINT_PORT,
        parent=None,
        print_raw: bool = False,
    ):
        """
        Store connection settings.
        """
        super().__init__(parent)

        self.host = host
        self.port = port
        self.print_raw = print_raw

        self._stop = False
        self.sock = None

    def stop(self):
        """
        Stop the thread safely and close socket connection.
        """
        self._stop = True

        try:
            if self.sock:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
        except Exception:
            pass

    def _enable_data_streams(self):
        """
        Enable the data streams needed from Gazepoint.
        """
        if not self.sock:
            return

        commands = [
            b'<SET ID="ENABLE_SEND_DATA" STATE="1" />\r\n',
            b'<SET ID="ENABLE_SEND_POG_FIX" STATE="1" />\r\n',
        ]

        for cmd in commands:
            try:
                self.sock.sendall(cmd)
            except Exception:
                pass

    def run(self):
        """
        Main thread loop:
        - connect to Gazepoint
        - receive XML lines
        - parse gaze values
        - emit them
        """
        try:
            self.status_signal.emit(f"Connecting to {self.host}:{self.port} ...")

            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5.0)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(None)

            self.status_signal.emit("Connected ✅")

            self._enable_data_streams()

            buffer = b""

            while not self._stop:
                chunk = self.sock.recv(4096)

                if not chunk:
                    break

                buffer += chunk

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        text_line = line.decode("utf-8", errors="ignore")

                        if self.print_raw:
                            print("RAW:", text_line)

                        if "<REC" not in text_line:
                            continue

                        element = ET.fromstring(text_line)

                        x_value = element.attrib.get("FPOGX")
                        y_value = element.attrib.get("FPOGY")
                        duration_value = element.attrib.get("FPOGD")
                        valid_value = element.attrib.get("FPOGV")

                        if x_value is None or y_value is None:
                            continue

                        gaze_x = float(x_value)
                        gaze_y = float(y_value)

                        fixation_duration = 0.0
                        if duration_value is not None:
                            fixation_duration = float(duration_value)

                        valid = (valid_value == "1") if valid_value is not None else True

                        # Gazepoint normalized values must stay between 0 and 1
                        if not (0.0 <= gaze_x <= 1.0 and 0.0 <= gaze_y <= 1.0):
                            valid = False

                        self.gaze_signal.emit(
                            gaze_x,
                            gaze_y,
                            fixation_duration,
                            bool(valid),
                        )

                    except Exception:
                        continue

            self.status_signal.emit("Disconnected")

        except Exception as e:
            self.status_signal.emit(f"Connection error: {e}")

        finally:
            try:
                if self.sock:
                    self.sock.close()
            except Exception:
                pass