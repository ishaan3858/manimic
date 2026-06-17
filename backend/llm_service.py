import os
import re
import asyncio
import logging
from google import genai
from google.genai import types
from google.genai.errors import APIError

logger = logging.getLogger("GeminiService")

class GeminiServiceError(Exception):
    def __init__(self, friendly_message: str, technical_details: str):
        super().__init__(friendly_message)
        self.technical_details = technical_details

class GeminiManimService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set and no API key was provided.")
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = "gemini-2.5-flash"  # Standard model for code generation

    async def _call_with_retry(self, api_call_coro_func):
        """
        Executes a Gemini API call coroutine with exponential backoff on transient errors.
        Transient errors: HTTP 500, 502, 503, 429, timeouts, and network/connection errors.
        """
        backoff_times = [2, 4, 8]
        max_attempts = len(backoff_times) + 1
        
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt > 1:
                    # Yield a progress message indicating a retry
                    yield {"type": "status", "message": "Retrying generation..."}
                
                response = await api_call_coro_func()
                yield {"type": "result", "response": response}
                return
            except Exception as e:
                is_transient = False
                status_code = None
                
                # Check for APIError from google-genai SDK
                if isinstance(e, APIError):
                    status_code = getattr(e, 'code', None) or getattr(e, 'status_code', None)
                    if status_code in [500, 502, 503, 429]:
                        is_transient = True
                    else:
                        err_str = str(e)
                        if any(f"status: {code}" in err_str or f"code {code}" in err_str for code in [500, 502, 503, 429]):
                            is_transient = True
                
                # Check for httpx / network timeouts and connection errors
                err_name = type(e).__name__.lower()
                if any(x in err_name for x in ["timeout", "connect", "network", "httperror", "readtimeout", "connectionerror"]):
                    is_transient = True
                
                # Check for built-in TimeoutError / OSError
                if isinstance(e, (OSError, TimeoutError)):
                    is_transient = True

                # Log technical details only on the backend console/logs
                logger.error(
                    f"[Gemini API Attempt {attempt}/{max_attempts}] Failed: {type(e).__name__}: {str(e)} "
                    f"(Transient: {is_transient})", 
                    exc_info=True
                )

                if is_transient and attempt <= len(backoff_times):
                    sleep_time = backoff_times[attempt - 1]
                    logger.info(f"Retrying in {sleep_time} seconds (exponential backoff)...")
                    await asyncio.sleep(sleep_time)
                else:
                    # Choose user-friendly messages for the frontend, hiding internal details
                    friendly = "AI service temporarily unavailable." if is_transient else "Generation failed. Please try again."
                    raise GeminiServiceError(
                        friendly_message=friendly,
                        technical_details=f"Exception: {type(e).__name__}, Message: {str(e)}"
                    ) from e

    async def generate_code(self, prompt: str):
        """
        Async generator that yields status updates and finally the generated code.
        """
        system_instruction = (
            "You are an expert Python developer specializing in the Manim Community Edition animation library.\n"
            "Your task is to generate complete, clean, and bug-free Manim code based on the user's description.\n\n"
            "CRITICAL GUIDELINES:\n"
            "1. Output ONLY a valid Python script. Do not include any introductory or concluding text.\n"
            "2. The code must import `from manim import *` (and optionally standard math, random modules). Do NOT import os, sys, subprocess, shutil, or any other library that poses a security risk.\n"
            "3. The script must contain exactly ONE main scene class that inherits from `Scene` (e.g., `class GenScene(Scene):`). Do NOT include multiple scenes unless they are supporting classes.\n"
            "4. The scene class must implement the `construct(self)` method containing the animation steps.\n"
            "5. Keep the animation relatively short (5 to 15 seconds) unless requested otherwise.\n"
            "6. Use modern Manim syntax. Use `self.play(...)`, `self.wait(...)`, and standard creation/transition methods like `Write`, `FadeIn`, `Transform`, `ReplacementTransform`, etc.\n"
            "7. Ensure colors are visually appealing. Use standard Manim colors like BLUE, RED, GREEN, YELLOW, PURPLE, ORANGE, WHITE, etc.\n"
            "8. Always format equations properly using MathTex if needed, but ensure they are syntactically correct and don't require external packages that aren't standard. Keep MathTex expressions simple.\n"
            "9. Return the code in a standard markdown Python code block: ```python ... ```."
        )

        async def make_call():
            return await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                )
            )
            
        try:
            async for event in self._call_with_retry(make_call):
                if event["type"] == "status":
                    yield event
                elif event["type"] == "result":
                    code = self._extract_code(event["response"].text)
                    yield {"type": "code", "code": code}
        except GeminiServiceError as e:
            yield {"type": "error", "message": str(e)}

    async def fix_code(self, original_code: str, error_message: str):
        """
        Async generator that yields status updates and finally the fixed code.
        """
        system_instruction = (
            "You are an expert Python developer specializing in the Manim Community Edition library.\n"
            "A Manim script that you previously generated has failed to compile or render.\n\n"
            "Analyze the original code and the error message provided, and generate a fixed version of the code.\n\n"
            "CRITICAL GUIDELINES:\n"
            "1. Output ONLY the fixed valid Python script in a ```python ... ``` block.\n"
            "2. Do not introduce any other code issues. Fix the specific error mentioned in the error message.\n"
            "3. Ensure the class name and basic concept of the animation are preserved.\n"
            "4. Ensure no unauthorized imports are used."
        )

        user_content = f"Original Code:\n```python\n{original_code}\n```\n\nError Message:\n{error_message}\n\nPlease fix this code."

        async def make_call():
            return await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                )
            )

        try:
            async for event in self._call_with_retry(make_call):
                if event["type"] == "status":
                    yield event
                elif event["type"] == "result":
                    code = self._extract_code(event["response"].text)
                    yield {"type": "code", "code": code}
        except GeminiServiceError as e:
            yield {"type": "error", "message": str(e)}

    def _extract_code(self, text: str) -> str:
        if not text:
            return ""
        match = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        clean_text = re.sub(r"^```\w*\n", "", text)
        clean_text = re.sub(r"\n```$", "", clean_text)
        return clean_text.strip()
