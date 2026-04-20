# Gaze-Based Writing Assistant

This project presents a gaze-driven writing assistant that uses eye tracking as an implicit interaction signal to support writing.

The system detects user attention based on gaze behavior and automatically triggers language model processing to provide feedback, without requiring explicit user interaction such as clicks or commands.

---

## Overview

Traditional writing assistance tools require explicit interaction, such as clicking buttons or requesting help manually.  
This interrupts the natural writing flow.

This system introduces a different approach by using gaze as an implicit signal of user attention.

When the user focuses on a sentence for a sufficient amount of time (fixation), the system automatically detects attention and triggers language model processing.

---

## Key Features

- Gaze-based sentence detection
- Automatic grammar correction
- Style and simplification suggestions
- Real-time feedback in the UI
- Logging of gaze and interaction events

---

## System Architecture

The system consists of the following components:

- **User Interface (PyQt6)**  
  Provides a text editor and displays feedback.

- **Gaze Tracking (Gazepoint)**  
  Collects real-time gaze data via TCP/XML communication.

- **Gaze Interpretation**  
  Detects fixations and user attention.

- **Interaction Logic Module**  
  Determines when to trigger analysis.

- **LLM Processing (OpenAI API – GPT-4o-mini)**  
  Generates corrections and suggestions.

- **Background Workers (QThread)**  
  Ensures non-blocking execution.

- **Logging Module (CSV)**  
  Records gaze data and system events.

---

## Technologies Used

- Python
- PyQt6
- Gazepoint eye tracker
- OpenAI API
- QThread (for concurrency)

---

## How It Works

1. The user writes text in the editor
2. The eye tracker captures gaze data in real time
3. The system detects fixation on a sentence
4. If a fixation is detected, the system triggers analysis
5. The sentence is sent to the language model
6. Feedback is displayed in the UI

---

## Example Capabilities

- Grammar correction  
  *Example:*  
  Input: **He go home.**  
  Output: **He goes home.**

- Style improvement  
  Provides more formal or clearer versions of sentences

- Sentence simplification  
  Produces shorter and more readable versions

---

## How to Run

1. Install dependencies:
pip install -r requirements.txt

2. Run the application:
python main.py

---

## Requirements

- Python 3.9+
- PyQt6
- OpenAI API key
- Gazepoint eye tracker (optional for full functionality)

---

## Notes

- The system can also run in **mouse-as-gaze mode** for testing without an eye tracker.
- An OpenAI API key is required for language model processing.

---

## Author

Alireza Khornegah  
University of Pavia
