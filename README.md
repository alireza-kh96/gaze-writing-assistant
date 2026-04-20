\# Gaze-Based Writing Assistant



This project presents a gaze-driven writing assistant that uses eye tracking as an implicit interaction signal to support writing.



\## Overview



Traditional writing assistance tools require explicit interaction, such as clicking buttons or requesting help manually.  

This system introduces a different approach by using gaze as an implicit signal.



When the user focuses on a sentence, the system automatically detects attention and triggers language model processing.



\## Features



\- Gaze-based sentence detection

\- Automatic grammar correction

\- Style and simplification suggestions

\- Real-time feedback in the UI

\- Logging of gaze and interaction events



\## System Architecture



The system consists of the following components:



\- PyQt6-based user interface

\- Gazepoint eye tracker (TCP/XML communication)

\- Gaze interpretation (fixation detection)

\- Interaction logic module

\- OpenAI API (GPT-4o-mini) for language processing

\- Background workers using QThread

\- Logging module (CSV)



\## Technologies Used



\- Python

\- PyQt6

\- Gazepoint eye tracker

\- OpenAI API

\- QThread (for concurrency)



\## How It Works



1\. The user writes text in the editor

2\. The eye tracker captures gaze data in real time

3\. The system detects fixation on a sentence

4\. If a fixation is detected, the system triggers analysis

5\. The sentence is sent to the language model

6\. Feedback is displayed in the UI



\## Example Capabilities



\- Grammar correction

\- Error highlighting

\- Style improvement

\- Sentence simplification



\## Notes



\- Requires Gazepoint eye tracker running locally

\- Requires OpenAI API key



\## Author



Alireza Khornegah  

University of Pavia

