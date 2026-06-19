import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Development-only Mock LLM configurations.
# MOCK_LLM_MODE is for frontend and workflow testing.
# Production deployments should disable it.
MOCK_LLM_MODE = os.getenv("MOCK_LLM_MODE", "false").lower() == "true"
MOCK_RENDER_FAILURE = os.getenv("MOCK_RENDER_FAILURE", "false").lower() == "true"

from backend.mock_llm_service import MockLLMService
from backend.llm_service import GeminiManimService

from backend.manim_runner import ManimRunner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ManimServer")

# Initialize directory structures
BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "renders" / "public"
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Manimic - AI-Powered Manim Video Generator")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
class GenerateRequest(BaseModel):
    prompt: str
    quality: Optional[str] = "m"  # 'l', 'm', 'h'

# Load / Save Gallery Database
GALLERY_FILE = BASE_DIR / "renders" / "gallery.json"

def load_gallery():
    if GALLERY_FILE.exists():
        try:
            with open(GALLERY_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
            
            valid_items = []
            stale_detected = False
            
            for item in items:
                video_url = item.get("video_url", "")
                filename = video_url.split("/")[-1] if video_url else ""
                if filename and (PUBLIC_DIR / filename).exists():
                    valid_items.append(item)
                else:
                    stale_detected = True
            
            if stale_detected:
                try:
                    with open(GALLERY_FILE, "w", encoding="utf-8") as f:
                        json.dump(valid_items, f, indent=2, ensure_ascii=False)
                    logger.info("Pruned stale entries from gallery database.")
                except Exception as prune_err:
                    logger.error(f"Failed to prune gallery database: {prune_err}")
            
            return valid_items
        except Exception as e:
            logger.error(f"Error loading gallery: {e}")
            return []
    return []
    return []

def save_to_gallery(item):
    gallery = load_gallery()
    gallery.insert(0, item)  # Insert at the beginning (newest first)
    try:
        with open(GALLERY_FILE, "w", encoding="utf-8") as f:
            json.dump(gallery, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving to gallery: {e}")

# SSE Helper to format events
def format_sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

# Async generator for the rendering pipeline
async def generate_pipeline(prompt: str, quality: str):
    llm_service: Optional[Union[MockLLMService, GeminiManimService]] = None
    runner = ManimRunner(str(BASE_DIR))
    
    # 1. Initialize LLM Service
    try:
        if MOCK_LLM_MODE:
            llm_service = MockLLMService(mock_render_failure=MOCK_RENDER_FAILURE)
        else:
            llm_service = GeminiManimService()
    except Exception as e:
        yield format_sse({"type": "error", "message": f"LLM Service Init Error: {str(e)}. Make sure GEMINI_API_KEY is set."})
        return

    # 2. Code Generation Phase
    msg = "Drafting Manim code using Mock LLM..." if MOCK_LLM_MODE else "Drafting Manim code using Gemini..."
    yield format_sse({"type": "status", "message": msg})
    code = None
    try:
        async for event in llm_service.generate_code(prompt):
            if event["type"] == "status":
                yield format_sse(event)
            elif event["type"] == "code":
                code = event["code"]
            elif event["type"] == "error":
                yield format_sse(event)
                return
        
        if not code:
            yield format_sse({"type": "error", "message": "Generation failed. Please try again."})
            return
        yield format_sse({"type": "code", "code": code})
    except Exception as e:
        logger.error(f"Unexpected generation failure: {e}", exc_info=True)
        yield format_sse({"type": "error", "message": "Generation failed. Please try again."})
        return

    # 3. Compile and Render Phase with Error Recovery Loop
    max_attempts = 3
    attempt = 1
    
    try:
        while attempt <= max_attempts:
            yield format_sse({
                "type": "status", 
                "message": f"Rendering video animation (Attempt {attempt}/{max_attempts})...",
                "attempt": attempt,
                "max_attempts": max_attempts
            })
            
            success = False
            error_msg = ""
            result = None
            yielded_error = False
    
            # Execute Manim runner generator
            try:
                async for update in runner.run_async_generator(code, quality):
                    if update["type"] == "log":
                        # Forward compilation logs to user UI
                        yield format_sse({"type": "log", "line": update["line"]})
                    elif update["type"] == "error":
                        error_msg = update["message"]
                        if attempt < max_attempts:
                            yield format_sse({
                                "type": "status",
                                "message": f"Render failed. Instructing Gemini to patch the code and retry...",
                                "attempt": attempt,
                                "max_attempts": max_attempts
                            })
                            yielded_error = True
                    elif update["type"] == "result":
                        success = True
                        result = update
            except Exception as e:
                error_msg = f"Runner exception: {str(e)}"
    
            if success and result:
                video_path = Path(result["path"])
                class_name = result["class_name"]
                job_id = result["job_id"]
                
                # Move video to public folder
                public_filename = f"{job_id}_{class_name}.mp4"
                dest_path = PUBLIC_DIR / public_filename
                try:
                    # Copy instead of move to preserve temp structures if needed, then we cleanup
                    import shutil
                    shutil.copy2(video_path, dest_path)
                except Exception as e:
                    yield format_sse({"type": "error", "message": f"Failed to save video: {str(e)}"})
                    return
                logger.info(f"Render completed successfully for job {job_id}. Delivering video to frontend.")
                video_url = f"/api/videos/{public_filename}"
                yield format_sse({
                    "type": "video", 
                    "url": video_url, 
                    "code": code,
                    "class_name": class_name
                })
                
                # Save successful generation to gallery
                gallery_item = {
                    "id": job_id,
                    "prompt": prompt,
                    "video_url": video_url,
                    "code": code,
                    "class_name": class_name,
                    "quality": quality,
                    "timestamp": datetime.now().isoformat()
                }
                save_to_gallery(gallery_item)
                
                yield format_sse({"type": "status", "message": "Render completed successfully!"})
                return
            
            else:
                # Attempt error recovery
                if attempt < max_attempts:
                    if not yielded_error:
                        yield format_sse({
                            "type": "status", 
                            "message": f"Render failed. Instructing Gemini to patch the code and retry...",
                            "attempt": attempt,
                            "max_attempts": max_attempts
                        })
                    logger.warning(f"Render failed on attempt {attempt}. Error: {error_msg}")
                    try:
                        fixed_code = None
                        async for event in llm_service.fix_code(code, error_msg):
                            if event["type"] == "status":
                                yield format_sse(event)
                            elif event["type"] == "code":
                                fixed_code = event["code"]
                            elif event["type"] == "error":
                                yield format_sse(event)
                                return
                        if not fixed_code:
                            yield format_sse({"type": "error", "message": "Generation failed. Please try again."})
                            return
                        code = fixed_code
                        yield format_sse({"type": "code", "code": code})
                    except Exception as fix_err:
                        logger.error(f"Unexpected code fixing failure: {fix_err}", exc_info=True)
                        yield format_sse({"type": "error", "message": "Generation failed. Please try again."})
                        return
                    attempt += 1
                else:
                    logger.error(f"Render failed on final attempt {attempt}. Error: {error_msg}")
                    yield format_sse({
                        "type": "error", 
                        "message": f"Render failed after {max_attempts} attempts.\n\nLast Error Details:\n{error_msg}"
                    })
                    return
    finally:
        runner.cleanup_jobs()

# API Endpoints
@app.post("/api/generate")
async def generate_video(request: GenerateRequest):
    return StreamingResponse(
        generate_pipeline(request.prompt, request.quality or "m"),
        media_type="text/event-stream"
    )

@app.get("/api/videos/{filename}")
async def get_video(filename: str):
    file_path = PUBLIC_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found.")
    return FileResponse(file_path, media_type="video/mp4")

@app.get("/api/gallery")
async def get_gallery():
    return load_gallery()

# Serve Frontend static assets
# Mounting static files at the root of FastAPI
# We will do a custom route for `/` to serve index.html, and mount the rest at static endpoints
frontend_dir = BASE_DIR / "frontend"
frontend_dir.mkdir(parents=True, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = frontend_dir / "index.html"
    if not index_path.exists():
        return "<h3>Welcome to Manimic API. Frontend index.html not found yet.</h3>"
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

# Mount style.css, script.js and others as static assets
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend_static")
