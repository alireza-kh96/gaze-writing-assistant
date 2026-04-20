import json
import os
import re
from typing import Any

from openai import OpenAI

from core.models import CorrectionResult, IssueResult

try:
    from config import OPENAI_API_KEY
except Exception:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

class OpenAICorrectionEngine:
    def __init__(self, model: str):
        self.model = model
        self.client = OpenAI(api_key=OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"))

    # ---------------------------------------------------------
    # Public: grammar correction
    # ---------------------------------------------------------
    def correct_sentence(self, sentence: str) -> CorrectionResult:
        prompt = f"""
You are an English grammar correction assistant.

Analyze the following sentence and correct grammar, spelling, and wording mistakes.

Return ONLY valid JSON in this exact format:
{{
  "corrected_sentence": "corrected sentence here",
  "issues": [
    {{
      "error_text": "wrong word or phrase",
      "suggestion": "best correction",
      "category": "grammar_or_spelling",
      "explanation": "short explanation"
    }}
  ]
}}

Rules:
- Return only JSON.
- Do not include markdown fences.
- If the sentence is already correct, return the original sentence and an empty issues list.
- Keep the corrected sentence natural and concise.
- For each issue, use the best single correction in "suggestion".

Sentence:
{sentence}
""".strip()

        raw_text = self._create_text_response(prompt)
        data = self._parse_json(raw_text)

        corrected_sentence = data.get("corrected_sentence", sentence)
        issues_data = data.get("issues", [])

        issues: list[IssueResult] = []
        for item in issues_data:
            if not isinstance(item, dict):
                continue

            issues.append(
                IssueResult(
                    error_text=str(item.get("error_text", "")).strip(),
                    suggestion=str(item.get("suggestion", "")).strip(),
                    category=str(item.get("category", "grammar_or_spelling")).strip(),
                    explanation=str(item.get("explanation", "")).strip(),
                    start=None,
                    end=None,
                )
            )

        return CorrectionResult(
            original_sentence=sentence,
            corrected_sentence=corrected_sentence,
            issues=issues,
        )

    # ---------------------------------------------------------
    # Public: academic + simpler style check
    # ---------------------------------------------------------
    def check_academic_style(self, sentence: str) -> dict:
        prompt = f"""
You are an English academic writing assistant.

Analyze the following sentence for writing style.

Tasks:
1. Classify the tone as one of these:
   - informal
   - neutral
   - academic

2. Decide whether it is suitable for academic writing.
3. Provide a more academic version of the sentence.
4. Provide a simpler version of the sentence.
5. Give a short explanation.

Return ONLY valid JSON in this exact format:
{{
  "tone": "informal",
  "suitable_for_academic": false,
  "academic_version": "Rewritten academic sentence here.",
  "simpler_version": "Simpler sentence here.",
  "explanation": "Short explanation here."
}}

Rules:
- Return only JSON.
- Do not include markdown fences.
- The academic_version must sound formal, clear, and suitable for academic writing.
- The simpler_version must be easier to read while preserving the original meaning.
- If the sentence is already academic, still provide an academic_version and a simpler_version.
- Keep both rewritten versions grammatically correct and natural.

Sentence:
{sentence}
""".strip()

        raw_text = self._create_text_response(prompt)
        data = self._parse_json(raw_text)

        return {
            "tone": str(data.get("tone", "neutral")).strip(),
            "suitable_for_academic": bool(data.get("suitable_for_academic", False)),
            "academic_version": str(data.get("academic_version", sentence)).strip(),
            "simpler_version": str(data.get("simpler_version", sentence)).strip(),
            "explanation": str(data.get("explanation", "")).strip(),
        }

    # ---------------------------------------------------------
    # Internal: API call
    # ---------------------------------------------------------
    def _create_text_response(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
        )

        text = getattr(response, "output_text", "")
        if not text:
            raise ValueError("OpenAI response did not contain output_text.")

        return text.strip()

    # ---------------------------------------------------------
    # Internal: robust JSON parsing
    # ---------------------------------------------------------
    def _parse_json(self, raw_text: str) -> dict[str, Any]:
        cleaned = self._strip_code_fences(raw_text)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            candidate = match.group(0)
            return json.loads(candidate)

        raise ValueError(f"Model did not return valid JSON. Raw output:\\n{raw_text}")

    def _strip_code_fences(self, text: str) -> str:
        text = text.strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        return text.strip()