import os
import sys
import re
import asyncio
import uuid
import logging
import traceback
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ManimRunner")

class ManimRunner:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.jobs_dir = self.base_dir / "renders" / "jobs"
        self.media_dir = self.base_dir / "renders" / "media"
        self.job_ids = []
        
        # Ensure directories exist
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)

    def check_safety(self, code: str) -> tuple[bool, str]:
        # Block obvious remote code execution vectors
        forbidden = [
            "import os", "import sys", "import subprocess", "import shutil",
            "import socket", "import urllib", "import requests", "import builtins",
            "eval(", "exec(", "__builtins__", "getattr(", "setattr(", "open(", 
            "subprocess.", "os.", "sys.", "shutil.", "socket.", "importlib"
        ]
        for pattern in forbidden:
            if pattern in code:
                return False, f"Code safety violation: forbidden pattern '{pattern}' is not allowed."
        return True, ""

    def extract_scene_class(self, code: str) -> str:
        # Find classes inheriting from Scene (or containing Scene in base classes)
        # e.g., class MyScene(Scene): or class MyScene(MovingCameraScene):
        matches = re.findall(r"class\s+(\w+)\s*\(([^)]*Scene[^)]*)\)", code)
        if matches:
            return matches[0][0]
        # Fallback to the first class declaration of any kind
        match = re.search(r"class\s+(\w+)\s*\(", code)
        if match:
            return match.group(1)
        return "GenScene"

    async def run_async_generator(self, code: str, quality: str = "m"):
        """
        Runs Manim asynchronously, yielding logs line by line, and then yielding the final file path or error.
        quality options: 'l' (low), 'm' (medium), 'h' (high)
        """
        # 1. Safety Check
        is_safe, safety_msg = self.check_safety(code)
        if not is_safe:
            yield {"type": "error", "message": safety_msg}
            return

        # 2. Extract scene class
        class_name = self.extract_scene_class(code)
        
        # 3. Create job file
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        self.job_ids.append(job_id)
        script_path = self.jobs_dir / f"{job_id}.py"
        
        try:
            # Write code to file using a thread-safe executor or simple write
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            # Map quality string to manim flag
            quality_flag = f"-q{quality}"
            
            # Command to run
            # Note: We execute sys.executable to run inside the same environment Python
            cmd = [
                sys.executable, "-m", "manim",
                quality_flag,
                "--media_dir", str(self.media_dir),
                str(script_path),
                class_name
            ]
            
            logger.info(f"Running command: {' '.join(cmd)}")
            yield {"type": "log", "line": "Spawning Manim render process..."}

            # Start the subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Queue-based concurrent line reader
            queue = asyncio.Queue()
            stderr_lines = []

            async def read_stream(stream, is_stderr):
                try:
                    while True:
                        line_bytes = await stream.readline()
                        if not line_bytes:
                            break
                        line = line_bytes.decode(errors="replace").strip()
                        if line:
                            clean_line = re.sub(r'\x1b\[[0-9;]*[mGKH]', '', line)
                            if clean_line:
                                if is_stderr:
                                    stderr_lines.append(clean_line)
                                await queue.put(clean_line)
                except Exception as e:
                    logger.error(f"Error reading stream: {e}")
                finally:
                    await queue.put(None)

            # Start reading tasks
            stderr_task = asyncio.create_task(read_stream(process.stderr, True))
            stdout_task = asyncio.create_task(read_stream(process.stdout, False))

            active_readers = 2
            while active_readers > 0:
                line = await queue.get()
                if line is None:
                    active_readers -= 1
                else:
                    yield {"type": "log", "line": line}

            # Wait for process to exit
            return_code = await process.wait()

            if return_code != 0:
                # Render failed
                error_msg = "\n".join(stderr_lines) if stderr_lines else "Manim compilation failed."
                clean_error = re.sub(r'\x1b\[[0-9;]*[mGKH]', '', error_msg)
                # Obfuscate temp file name
                clean_error = clean_error.replace(str(script_path), "scene.py")
                yield {"type": "error", "message": clean_error}
                return

            # Find the rendered video
            search_path = self.media_dir / "videos" / job_id
            mp4_files = list(search_path.glob("**/*.mp4"))
            
            if mp4_files:
                yield {
                    "type": "result", 
                    "success": True, 
                    "path": str(mp4_files[0]), 
                    "class_name": class_name,
                    "job_id": job_id
                }
            else:
                # Fallback search by class name
                fallback_files = list((self.media_dir / "videos").glob(f"**/{class_name}.mp4"))
                if fallback_files:
                    fallback_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    yield {
                        "type": "result", 
                        "success": True, 
                        "path": str(fallback_files[0]), 
                        "class_name": class_name,
                        "job_id": job_id
                    }
                else:
                    yield {"type": "error", "message": "Render completed but could not find the output video file."}

        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Unexpected runner error:\n{tb_str}")
            yield {"type": "error", "message": f"Unexpected runner error: {str(e)}\n\nTraceback:\n{tb_str}"}
        finally:
            # Clean up temp script files
            if script_path.exists():
                try:
                    os.remove(script_path)
                except Exception:
                    pass

    def cleanup_jobs(self):
        import shutil
        for job_id in self.job_ids:
            # Clean up videos directory
            job_dir = self.media_dir / "videos" / job_id
            if job_dir.exists():
                try:
                    shutil.rmtree(job_dir)
                    logger.info(f"Cleaned up intermediate artifacts for job: {job_id}")
                except Exception as e:
                    logger.error(f"Failed to cleanup job dir {job_dir}: {e}")
            
            # Clean up images directory
            img_dir = self.media_dir / "images" / job_id
            if img_dir.exists():
                try:
                    shutil.rmtree(img_dir)
                    logger.info(f"Cleaned up intermediate image artifacts for job: {job_id}")
                except Exception as e:
                    logger.error(f"Failed to cleanup image job dir {img_dir}: {e}")
