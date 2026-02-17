import json
import os
import re
from typing import Any, Dict, Optional, Protocol

import requests


class Provider(Protocol):
    def generate(self, user_message: str) -> Optional[str]:
        ...


class HuggingFaceProvider:
    def __init__(self) -> None:
        self.api_token = os.getenv("HF_API_TOKEN")
        self.endpoint = "https://api-inference.huggingface.co/models/tiiuae/falcon-7b-instruct"

    def generate(self, user_message: str) -> Optional[str]:
        if not self.api_token:
            return None

        prompt = (
            "You are an intent parser for a Lucknow bus chatbot.\n"
            "Rules:\n"
            "1) For greetings or small talk, return only JSON: {\"intent\":\"greeting\"}.\n"
            "2) For travel query, return only JSON with keys exactly: {\"from\":\"\",\"to\":\"\",\"after_time\":\"\"}.\n"
            "3) If intent cannot be extracted, return: {\"from\":\"\",\"to\":\"\",\"after_time\":\"\"}.\n"
            "4) Never answer route details.\n"
            f"User: {user_message}\n"
            "JSON:"
        )

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        body = {
            "inputs": prompt,
            "parameters": {
                "temperature": 0.1,
                "max_new_tokens": 120,
                "return_full_text": False,
            },
        }

        try:
            response = requests.post(self.endpoint, headers=headers, json=body, timeout=20)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                text = payload[0].get("generated_text", "")
                return text if isinstance(text, str) else None
            if isinstance(payload, dict) and isinstance(payload.get("generated_text"), str):
                return payload["generated_text"]
        except Exception:
            return None

        return None


class IntentParser:
    def __init__(self, provider: Optional[Provider] = None) -> None:
        self.provider = provider or HuggingFaceProvider()
        self.generic_words = {"here", "there", "somewhere", "anywhere", "place", "destination", "source"}

    def parse_intent(self, message: str) -> Dict[str, str]:
        model_output = self.provider.generate(message)
        parsed = self._parse_model_output(model_output)

        if parsed is not None:
            return parsed

        return self._rule_fallback(message)

    def _parse_model_output(self, raw_text: Optional[str]) -> Optional[Dict[str, str]]:
        if not raw_text:
            return None

        payload = self._extract_json(raw_text)
        if payload is None:
            return None

        intent_value = str(payload.get("intent", "")).strip().lower()
        if intent_value == "greeting":
            return {
                "type": "greeting",
                "from": "",
                "to": "",
                "after_time": "",
            }

        if {"from", "to", "after_time"}.issubset(payload.keys()):
            return {
                "type": "route_query",
                "from": self._clean_place(str(payload.get("from", ""))),
                "to": self._clean_place(str(payload.get("to", ""))),
                "after_time": self._clean_after_time(str(payload.get("after_time", ""))),
            }

        return None

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None

    def _rule_fallback(self, message: str) -> Dict[str, str]:
        text = " ".join(message.strip().lower().split())

        if self._is_greeting(text):
            return {
                "type": "greeting",
                "from": "",
                "to": "",
                "after_time": "",
            }

        route = self._extract_route(text)
        if route is not None:
            return {
                "type": "route_query",
                "from": route["from"],
                "to": route["to"],
                "after_time": route["after_time"],
            }

        return {
            "type": "unknown",
            "from": "",
            "to": "",
            "after_time": "",
        }

    def _is_greeting(self, text: str) -> bool:
        patterns = [r"\bhi+\b", r"\bhello+\b", r"\bhey+\b", r"\bthanks?\b", r"\bhow are you\b"]
        return any(re.search(pattern, text) for pattern in patterns)

    def _extract_route(self, text: str) -> Optional[Dict[str, str]]:
        patterns = [
            r"from\s+(?P<from>.+?)\s+to\s+(?P<to>.+?)\s+after\s+(?P<time>\d{1,2}:\d{2})$",
            r"(?P<from>.+?)\s+to\s+(?P<to>.+?)\s+after\s+(?P<time>\d{1,2}:\d{2})$",
            r"from\s+(?P<from>.+?)\s+to\s+(?P<to>.+)$",
            r"(?P<from>.+?)\s+to\s+(?P<to>.+)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            return {
                "from": self._clean_place(match.group("from")),
                "to": self._clean_place(match.group("to")),
                "after_time": self._clean_after_time(match.groupdict().get("time", "")),
            }

        return None

    def _clean_place(self, value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z\s]", " ", value)
        cleaned = " ".join(cleaned.lower().split())
        cleaned = re.sub(r"^(bus\s+from\s+|from\s+)", "", cleaned)
        cleaned = re.sub(r"^(bus\s+to\s+|to\s+)", "", cleaned)
        if cleaned in self.generic_words:
            return ""
        return cleaned

    def _clean_after_time(self, value: str) -> str:
        text = value.strip()
        if not text:
            return ""
        return text if re.match(r"^\d{1,2}:\d{2}$", text) else ""
