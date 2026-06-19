import asyncio
import logging

logger = logging.getLogger("MockLLMService")

class MockLLMService:
    """
    Mock LLM Service for development-only testing of the Manimic frontend and workflows.
    Exposes the exact same interface as llm_service.py without making network requests
    or requiring a GEMINI_API_KEY.
    """
    def __init__(self, api_key: str = None, mock_render_failure: bool = False):
        self.api_key = api_key
        self.mock_render_failure = mock_render_failure
        logger.info(f"Initialized MockLLMService (mock_render_failure={mock_render_failure})")

    async def generate_code(self, prompt: str):
        # MOCK_LLM_MODE is for frontend and workflow testing.
        # Production deployments should disable it.
        yield {"type": "status", "message": "Drafting Manim code (Mock Mode)..."}
        await asyncio.sleep(1.0)
        
        if self.mock_render_failure:
            code = self._get_broken_code()
            logger.info("Mock LLM generating intentionally broken Manim code")
        else:
            code = self._get_working_code()
            logger.info("Mock LLM generating working Manim code")
            
        yield {"type": "code", "code": code}

    async def fix_code(self, original_code: str, error_message: str):
        # MOCK_LLM_MODE is for frontend and workflow testing.
        # Production deployments should disable it.
        yield {"type": "status", "message": "Instructing Mock LLM to patch the code..."}
        await asyncio.sleep(1.0)
        
        if self.mock_render_failure:
            code = self._get_broken_code()
            logger.info("Mock LLM returning another broken code attempt")
        else:
            code = self._get_working_code()
            logger.info("Mock LLM returning repaired working code")
            
        yield {"type": "code", "code": code}

    def _get_working_code(self) -> str:
        return (
            "from manim import *\n\n"
            "class CircleToSquare(Scene):\n"
            "    def construct(self):\n"
            "        # Render a simple circle transforming into a square\n"
            "        circle = Circle(color=BLUE)\n"
            "        square = Square(color=RED)\n"
            "        \n"
            "        self.play(Create(circle))\n"
            "        self.wait(1)\n"
            "        self.play(Transform(circle, square))\n"
            "        self.wait(1)\n"
        )

    def _get_broken_code(self) -> str:
        return (
            "from manim import *\n\n"
            "class CircleToSquare(Scene):\n"
            "    def construct(self):\n"
            "        circle = Circle(color=BLUE)\n"
            "        # Intentionally invalid method call to trigger compile failure\n"
            "        self.play(circle.invalid_manim_method_that_fails())\n"
        )
