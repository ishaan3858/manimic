import os
import sys
import subprocess
import webbrowser
import time
from dotenv import load_dotenv

load_dotenv()

def check_env():
    """Check if Python virtual environment is set up and key dependencies are present."""
    try:
        import fastapi
        import uvicorn
        import google.genai
    except ImportError:
        print("[!] Missing dependencies. Please run:")
        print("    pip install -r backend/requirements.txt")
        print("    or run inside your virtual environment.")
        return False
    
    # Check for GEMINI_API_KEY
    if not os.environ.get("GEMINI_API_KEY"):
        print("[WARNING] GEMINI_API_KEY environment variable is not set!")
        print("Please set it in your system or environment before rendering animations.")
        print("Example: set GEMINI_API_KEY=your_key_here")
        print()
    return True

def main():
    print("=" * 60)
    print("   __  ___           _      _     ")
    print("  /  |/  /___ _ ___ (_)___ (_)____")
    print(" / /|_/ // _ `// _ \// // _ `// // __/")
    print("/_/  /_/ \_,_//_//_//_/ \_,_//_/ \__/")
    print("    AI-Powered Manim Video Generator")
    print("=" * 60)
    
    check_env()

    # Define command to run uvicorn
    # Use sys.executable to run inside the same environment Python
    # We add --reload-exclude for the renders directory to prevent WatchFiles from restarting the server during compilation
    cmd = [
    sys.executable,
    "-m",
    "uvicorn",
    "backend.main:app",
    "--host", "127.0.0.1",
    "--port", "8000"
]
    
    print("[SYSTEM] Starting FastAPI server at http://127.0.0.1:8000 ...")
    
    # Start the server process
    process = None
    try:
        # Open browser shortly after server starts
        def open_browser():
            time.sleep(1.5)
            print("[SYSTEM] Launching frontend in default browser...")
            webbrowser.open("http://127.0.0.1:8000")

        # Spawn a thread or simple delayed process to open browser
        import threading
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()

        # Run uvicorn (blocks until keyboard interrupt)
        process = subprocess.run(cmd)

    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down Manimic. Bye!")
    except Exception as e:
        print(f"[SYSTEM ERROR] Could not start server: {e}")

if __name__ == "__main__":
    main()
