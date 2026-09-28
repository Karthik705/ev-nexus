import os
import json
import time
import sys
import typing
import io

if hasattr(sys.stdout, "reconfigure"):
    typing.cast(io.TextIOWrapper, sys.stdout).reconfigure(encoding='utf-8')
from negotiation_types import LLMParsedRequest
from typing import Optional

# Model alias — resolves automatically to the current GA Flash release so this
# code does not need updating on every Google model rotation.
# Per ai.google.dev/gemini-api/docs/models (checked 2026-09-23), gemini-flash-latest
# currently points to gemini-3.8-flash.
# If you need to pin an explicit version, replace with e.g. "gemini-3.8-flash".
GEMINI_MODEL = "gemini-flash-latest"


class GeminiNegotiator:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            try:
                with open(".env", "r") as f:
                    for line in f:
                        if line.startswith("GEMINI_API_KEY="):
                            self.api_key = line.strip().split("=", 1)[1]
                            os.environ["GEMINI_API_KEY"] = self.api_key
            except Exception:
                pass

        self.client = None
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"❌ Error initializing Gemini Client: {e}")

        # Explicit call-level counters — never silent about failures.
        self.call_count = 0
        self.success_count = 0
        self.fallback_count = 0
        self.error_log: list[tuple[str, str]] = []  # (error_type, message) entries

    def negotiate(self, driver_message: str) -> tuple[Optional[LLMParsedRequest], float, bool]:
        """
        Parses driver_message into LLMParsedRequest.
        Returns: (parsed_request, latency_seconds, success_bool)

        Failures are NEVER silent: every failure increments fallback_count and
        appends a classified entry to error_log.
        """
        self.call_count += 1

        if not self.client:
            self.fallback_count += 1
            self.error_log.append(("NO_CLIENT", "Gemini client not initialised (missing/invalid API key)"))
            return None, 0.0, False

        start_time = time.time()

        prompt = f"""
You are the AI Charging Station Dispatcher.
Your task is to parse the driver's natural language request into a strict JSON schema.

Driver Message: "{driver_message}"

Extract the following:
1. "urgency_level": Must be exactly one of ["LOW", "MEDIUM", "HIGH", "CRITICAL"].
2. "deadline_minutes": Integer representing the deadline in minutes. null if not mentioned or vague.
3. "reason_category": Short category (e.g., "COMMUTE", "EMERGENCY", "LATE", "CASUAL").
4. "claimed_constraints": Array of string constraints (e.g., ["needs fast charger", "low budget"]).
5. "requested_port_type": String (e.g., "150kW") or null.
6. "confidence": Float between 0.0 and 1.0 indicating how clear the request is.
7. "explanation": 1-sentence reasoning for the extraction.

Output ONLY valid JSON. No markdown backticks.

Example Output:
{{
  "urgency_level": "HIGH",
  "deadline_minutes": 25,
  "reason_category": "LATE",
  "claimed_constraints": [],
  "requested_port_type": null,
  "confidence": 0.9,
  "explanation": "Driver explicitly stated they are running late and have 25 minutes."
}}
"""
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={"temperature": 0.0}  # Deterministic
            )

            raw_text = (response.text or "").replace("```json", "").replace("```", "").strip()
            data = json.loads(raw_text)

            req = LLMParsedRequest(
                urgency_level=data.get("urgency_level", "MEDIUM"),
                deadline_minutes=data.get("deadline_minutes"),
                reason_category=data.get("reason_category", "UNKNOWN"),
                claimed_constraints=data.get("claimed_constraints", []),
                requested_port_type=data.get("requested_port_type"),
                confidence=float(data.get("confidence", 0.5)),
                explanation=data.get("explanation", "")
            )

            latency = time.time() - start_time
            self.success_count += 1
            return req, latency, True

        except Exception as e:
            latency = time.time() - start_time
            error_type = self._classify_error(e)
            msg = f"{error_type}: {e}"
            print(f"❌ Gemini API Error [{error_type}]: {e}")
            self.fallback_count += 1
            self.error_log.append((error_type, str(e)))
            return None, latency, False

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        """Classify exception into a short error-type label.

        ORDER MATTERS: more-specific checks must come before general ones.

        Priority:
          1. AUTH_ERROR   — 401/403/UNAUTHENTICATED (check first; 401 body
                            contains 'access' which would otherwise hit RATE_LIMIT)
          2. MODEL_NOT_FOUND — 404 / model retired or access-restricted
          3. RATE_LIMIT   — 429 / quota exhausted
          4. PARSE_ERROR  — malformed JSON in the response
          5. TIMEOUT      — network/deadline exceeded
          6. UNKNOWN_ERROR — catch-all
        """
        name = type(exc).__name__
        text = str(exc).lower()

        # 1. Auth errors (401, 403, UNAUTHENTICATED) — check FIRST
        if ("401" in text or "403" in text or "unauthenticated" in text
                or "api_key" in text or "access_token_type_unsupported" in text):
            return "AUTH_ERROR"

        # 2. Model not found / retired / access-restricted (404)
        #    Covers: model retirement, gemini-2.5 access restriction for new keys,
        #    and any future model-string changes.
        if ("404" in text
                or "not found" in text
                or "is no longer available" in text
                or "model_not_found" in text
                or "notfound" in text):
            return "MODEL_NOT_FOUND"

        # 3. Rate limit / quota exhaustion
        if "429" in text or "quota" in text or "resource_exhausted" in text or "rate_limit" in text:
            return "RATE_LIMIT"

        # 4. JSON parse error in LLM response
        if "json" in name.lower() or isinstance(exc, (json.JSONDecodeError, ValueError)):
            return "PARSE_ERROR"

        # 5. Network / deadline timeout
        if "timeout" in text or "deadline" in text:
            return "TIMEOUT"

        return "UNKNOWN_ERROR"

    def print_call_stats(self, prefix: str = "") -> None:
        """Print a summary of call outcomes. Call after a batch of negotiations."""
        label = f"[{prefix}] " if prefix else ""
        total = self.call_count
        if total == 0:
            return
        print(
            f"  {label}negotiate() calls: {total} total | "
            f"✅ {self.success_count} succeeded | "
            f"⚠️  {self.fallback_count} fell back to telemetry"
        )
        if self.error_log:
            from collections import Counter
            counts = Counter(t for t, _ in self.error_log)
            print(f"  {label}Error breakdown: {dict(counts)}")

    def reset_stats(self) -> None:
        """Reset counters between experiment runs."""
        self.call_count = 0
        self.success_count = 0
        self.fallback_count = 0
        self.error_log.clear()


if __name__ == "__main__":
    negotiator = GeminiNegotiator()
    req, lat, succ = negotiator.negotiate("I have 10% battery and need to leave in 15 minutes.")
    print(f"Success: {succ} in {lat:.2f}s")
    if succ:
        print(req)
    negotiator.print_call_stats("test")