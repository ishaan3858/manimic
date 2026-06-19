# Manimic

**Manimic** is a full-stack AI-assisted animation platform that transforms natural language prompts into educational, mathematical, and technical animation videos using the Manim rendering engine. The application automatically generates animation code, compiles scenes, renders videos, and streams real-time progress updates through a modern web interface.

---

## Features

- Natural language to animation workflow
- Automated Manim code generation using Google Gemini
- Real-time rendering status updates using Server-Sent Events (SSE)
- Automatic error recovery and code regeneration
- Interactive video preview and playback
- Generation history with persistent storage
- Automatic cleanup of intermediate rendering artifacts
- Mock LLM mode for frontend and workflow testing
- Downloadable rendered animations
- Modern responsive user interface with a premium dark theme

---

## System Architecture

### Frontend

The frontend is built as a responsive Single Page Application (SPA) featuring:

- Modern dark-themed interface
- Real-time generation activity console
- Integrated video player
- Generation history gallery
- Live rendering progress tracking

### Backend

The backend is powered by FastAPI and orchestrates the complete animation pipeline:

1. Accepts user prompts from the frontend.
2. Generates Manim Python code using a large language model.
3. Executes Manim rendering jobs asynchronously.
4. Streams rendering logs and status updates to the client using SSE.
5. Detects rendering failures and automatically attempts code correction.
6. Retries failed renders without requiring user intervention.
7. Stores generated videos and render metadata for future access.

---

## Technology Stack

### Frontend

- HTML5
- CSS3
- JavaScript (ES6)
- Server-Sent Events (SSE)

### Backend

- Python
- FastAPI
- Uvicorn
- AsyncIO

### AI & Rendering

- Google Gemini API
- Manim Community Edition
- FFmpeg

### Storage

- JSON-based generation history storage
- Local media asset management

---

## Error Recovery Workflow

```text
Prompt
   ↓
Generate Manim Code
   ↓
Render Animation
   ↓
Success ───────────────► Deliver Video

Failure
   ↓
Analyze Error
   ↓
Regenerate Corrected Code
   ↓
Retry Render
   ↓
Success or Final Failure
```

The system automatically attempts multiple correction cycles before reporting a final rendering failure.

---

## Prerequisites

Before running the application, install:

- Python 3.9 – 3.12
- FFmpeg
- LaTeX distribution (recommended)
  - MiKTeX (Windows)
  - TeX Live (Linux/macOS)
- Google Gemini API Key

---

## Installation

### Clone the Repository

```bash
git clone https://github.com/<your-username>/manimic.git
cd manimic
```

### Create a Virtual Environment

```bash
python -m venv venv
```

### Activate the Environment

**Windows**

```bash
venv\Scripts\activate
```

**Linux/macOS**

```bash
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r backend/requirements.txt
```

---

## Environment Configuration

Create a `.env` file in the project root.

Example:

```env
GEMINI_API_KEY=your_api_key_here

MOCK_LLM_MODE=false
MOCK_RENDER_FAILURE=false
```

### Configuration Options

| Variable | Description |
|-----------|-------------|
| GEMINI_API_KEY | Google Gemini API key |
| MOCK_LLM_MODE | Uses the mock LLM instead of Gemini |
| MOCK_RENDER_FAILURE | Simulates render failures for testing retry workflows |

### Development Modes

Run with Gemini:

```env
MOCK_LLM_MODE=false
```

Run without consuming Gemini API quota:

```env
MOCK_LLM_MODE=true
```

Simulate repair and retry workflows:

```env
MOCK_LLM_MODE=true
MOCK_RENDER_FAILURE=true
```

---

## Running the Application

From the project root directory:

```bash
python run.py
```

The application will start locally and automatically open in your default browser.

By default, the application is available at:

```text
http://127.0.0.1:8000
```

---

## Project Structure

```text
manimic/
├── backend/
│   ├── main.py
│   ├── llm_service.py
│   ├── mock_llm_service.py
│   ├── manim_runner.py
│   └── requirements.txt
│
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js
│
├── renders/
│   ├── jobs/
│   ├── media/
│   ├── public/
│   └── gallery.json
│
├── .env.example
├── run.py
└── README.md
```

---

## Security Considerations

Manimic executes generated Python code for animation rendering. Basic safety validation is performed before execution by detecting and rejecting potentially dangerous imports and runtime operations.

For production deployments, rendering workloads should be isolated inside secure sandbox environments such as:

- Docker containers
- gVisor
- Firecracker microVMs
- Dedicated worker environments

---

## Future Enhancements

- Cloud-based rendering workers
- User authentication
- Export to GIF and WebM formats
- Animation template library
- Multi-scene video generation
- Database-backed generation history
- Advanced render queue management
- Containerized execution sandbox

---

## License

This project is intended for educational and research purposes.