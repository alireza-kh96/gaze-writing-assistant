# config.py

"""
This file stores all project configuration values.

If we want to change behaviour of the system,
we modify values here instead of editing the whole code.
"""

import os

# -----------------------------
# OpenAI settings
# -----------------------------

OPENAI_MODEL = "gpt-4o-mini"

# API key (recommended to load from environment variable)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# -----------------------------
# Eye tracker settings
# -----------------------------

GAZEPOINT_HOST = "127.0.0.1"
GAZEPOINT_PORT = 4242

# -----------------------------
# Timing settings (milliseconds)
# -----------------------------

# Time required for a fixation on a sentence
FIXATION_THRESHOLD_MS = 600

# Time required to trigger word suggestions
WORD_DWELL_THRESHOLD_MS = 700

# Time required to activate suggestion buttons
SUGGESTION_DWELL_THRESHOLD_MS = 800

# -----------------------------
# UI drawing settings
# -----------------------------

SHOW_GAZE_DEFAULT = True
MOUSE_GAZE_DEFAULT = True

# Size of gaze uncertainty circle
GAZE_CIRCLE_RADIUS_PX = 35

# -----------------------------
# Editor layout settings
# -----------------------------

# number of spaces used for indentation
EDITOR_INDENT_SPACES = 3

# editor line spacing (percentage)
EDITOR_LINE_SPACING = 150

# -----------------------------
# Logging settings
# -----------------------------

LOGS_DIR = "logs"

# -----------------------------
# Debug settings
# -----------------------------

PRINT_OPENAI_PROMPTS = False
PRINT_OPENAI_RESPONSES = False