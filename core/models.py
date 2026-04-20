# core/models.py

"""
Data structures used across the application.
These classes describe the information exchanged
between eye tracker, UI and language model.
"""

from dataclasses import dataclass, field
from typing import List, Optional


# ----------------------------------
# Gaze sample from eye tracker
# ----------------------------------

@dataclass
class GazeSample:
    """
    Represents one gaze measurement from the eye tracker.
    """

    x: int
    y: int

    timestamp: float

    fixation_duration: float = 0.0

    valid: bool = True


# ----------------------------------
# Issue detected in the text
# ----------------------------------

@dataclass
class Issue:
    """
    Represents an error found in the user's sentence.
    """

    start: int
    end: int
    word: str

    suggestions: List[str]

    category: str = "unknown"
    explanation: str = ""


# ----------------------------------
# Issue returned by the LLM
# ----------------------------------

@dataclass
class IssueResult:
    """
    Raw issue returned by the language model.
    """

    error_text: str
    suggestion: str
    category: str
    explanation: str

    start: Optional[int] = None
    end: Optional[int] = None


# ----------------------------------
# Result of full sentence correction
# ----------------------------------

@dataclass
class CorrectionResult:
    """
    Full correction result returned by the model.
    """

    original_sentence: str
    corrected_sentence: str

    issues: List[IssueResult] = field(default_factory=list)