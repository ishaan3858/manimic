document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const promptInput = document.getElementById('prompt-input');
    const qualitySelect = document.getElementById('quality-select');
    const generateBtn = document.getElementById('generate-btn');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const progressBarContainer = document.getElementById('progress-bar-container');
    const videoPlaceholder = document.getElementById('video-placeholder');
    const videoPlayer = document.getElementById('video-player');
    const videoSource = document.getElementById('video-source');
    const exportControls = document.getElementById('export-controls');
    const downloadLink = document.getElementById('download-link');
    const terminalBody = document.getElementById('terminal-body');
    const galleryGrid = document.getElementById('gallery-grid');
    const suggestionsContainer = document.getElementById('suggestions-container');

    let isProcessing = false;
    let loggedInSession = new Set();

    // Initialize Page
    loadGallery();
    initTerminalMessages();

    // Suggestion Chips Click
    suggestionsContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('chip')) {
            const prompt = e.target.getAttribute('data-prompt');
            promptInput.value = prompt;
            // Add focus animation class or effect
            promptInput.focus();
        }
    });



    // Generate Button Click
    generateBtn.addEventListener('click', async () => {
        const prompt = promptInput.value.trim();
        if (!prompt) {
            alert('Please enter a description or prompt for the animation.');
            promptInput.focus();
            return;
        }

        const quality = qualitySelect.value;
        startGenerationUI();

        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ prompt, quality })
            });

            if (!response.ok) {
                throw new Error(`Server returned HTTP status ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop(); // Keep the last incomplete block

                for (const line of lines) {
                    if (line.trim().startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.trim().slice(6));
                            handleServerEvent(data);
                        } catch (e) {
                            console.error('Error parsing SSE event', e, line);
                        }
                    }
                }
            }

        } catch (error) {
            isProcessing = false;
            translateAndLog(`[CONNECTION ERROR] ${error.message}`, 'error');
            updateStatus('error', 'Service Temporarily Unavailable');
            resetButtonUI();
        }
    });

    // Helper to map backend status messages to simplified status header states
    function mapStatusHeader(message) {
        const msgLower = message.toLowerCase();
        if (msgLower.includes('patch') || msgLower.includes('fix') || msgLower.includes('repairing') || msgLower.includes('instructing')) {
            return { state: 'repairing', text: 'Repairing Animation' };
        } else if (msgLower.includes('drafting') || msgLower.includes('generating') || msgLower.includes('retry') || msgLower.includes('retrying')) {
            return { state: 'generating', text: 'Processing' };
        } else if (msgLower.includes('rendering')) {
            return { state: 'rendering', text: 'Rendering' };
        } else if (msgLower.includes('completed') || msgLower.includes('success')) {
            return { state: 'complete', text: 'Completed' };
        } else if (msgLower.includes('unavailable') || msgLower.includes('outage') || msgLower.includes('timeout') || msgLower.includes('connection')) {
            return { state: 'error', text: 'Service Temporarily Unavailable' };
        } else if (msgLower.includes('failed') || msgLower.includes('error')) {
            return { state: 'failed', text: 'Generation Failed' };
        }
        return { state: 'generating', text: 'Processing' };
    }

    // Handle SSE updates
    function handleServerEvent(event) {
        switch (event.type) {
            case 'status':
                if (event.message.includes("completed successfully") || event.message.includes("Render completed")) {
                    break;
                }
                const mapped = mapStatusHeader(event.message);
                updateStatus(mapped.state, mapped.text);
                
                // If it is a repair status, inject attempt details explicitly
                if (mapped.state === 'repairing' && event.attempt) {
                    translateAndLog(`[STATUS] Repairing animation...`, 'system');
                    translateAndLog(`[STATUS] Attempt ${event.attempt} of ${event.max_attempts}`, 'system');
                } else {
                    translateAndLog(`[STATUS] ${event.message}`, 'system');
                }
                
                // Update button text to match current phase
                if (isProcessing) {
                    if (mapped.state === 'generating') {
                        generateBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> <span>Processing...</span>';
                    } else if (mapped.state === 'rendering') {
                        generateBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> <span>Rendering...</span>';
                    } else if (mapped.state === 'repairing') {
                        generateBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> <span>Repairing...</span>';
                    }
                }
                break;
            case 'code':
                translateAndLog('[SYSTEM] Generated Manim code successfully.', 'system');
                break;
            case 'log':
                translateAndLog(event.line, 'log');
                break;
            case 'video':
                isProcessing = false;
                updateStatus('complete', 'Completed');
                translateAndLog('[SYSTEM] Video rendered and loaded.', 'system');
                translateAndLog('[SYSTEM] Ready for another prompt.', 'system');
                loadVideo(event.url);
                loadGallery(); // Refresh history
                resetButtonUI();
                break;
            case 'error':
                isProcessing = false;
                const errLower = event.message.toLowerCase();
                if (errLower.includes('unavailable') || errLower.includes('outage') || errLower.includes('timeout') || errLower.includes('connection')) {
                    updateStatus('error', 'Service Temporarily Unavailable');
                    translateAndLog('[SYSTEM] Service temporarily unavailable.', 'error');
                } else {
                    updateStatus('failed', 'Generation Failed');
                    translateAndLog('[SYSTEM] Generation failed.', 'error');
                }
                resetButtonUI();
                break;
        }
    }

    // UI Helper Functions
    function startGenerationUI() {
        isProcessing = true;
        loggedInSession.clear();
        generateBtn.disabled = true;
        generateBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> <span>Processing...</span>';
        updateStatus('generating', 'Processing');
        
        // Clear old terminal
        terminalBody.innerHTML = '';
        translateAndLog('[SYSTEM] Starting generation job...', 'system');
        
        // Reset player/source
        videoPlayer.classList.add('hidden');
        videoPlaceholder.classList.remove('hidden');
        exportControls.classList.add('hidden');
    }

    function resetButtonUI() {
        generateBtn.disabled = false;
        generateBtn.innerHTML = '<i class="fa-solid fa-play"></i> <span>Generate Video</span>';
    }

    function updateStatus(state, message) {
        statusDot.className = 'status-dot ' + state;
        statusText.innerText = message;

        if (state === 'generating' || state === 'rendering' || state === 'repairing') {
            progressBarContainer.style.display = 'block';
        } else {
            progressBarContainer.style.display = 'none';
        }
    }

    // Translate technical/raw log events into clean human-friendly progress logs
    function translateAndLog(text, type = 'log') {
        if (!text) return;

        const cleanText = text.trim();
        const textLower = cleanText.toLowerCase();

        // 1. Blacklist / Filter rules - Discard internal, SDK, stack trace, and raw path info
        const isBlacklisted = 
            textLower.includes('gemini') ||
            textLower.includes('google') ||
            textLower.includes('python') ||
            textLower.includes('fastapi') ||
            textLower.includes('sdk') ||
            textLower.includes('traceback') ||
            textLower.includes('file "') ||
            textLower.includes('line ') ||
            textLower.includes('httpx') ||
            textLower.includes('http request') ||
            textLower.includes('get /') ||
            textLower.includes('post /') ||
            textLower.includes('uvicorn') ||
            textLower.includes('exception:') ||
            textLower.includes('calledprocesserror') ||
            // File paths: check for drive letters or directory/file patterns, but allow clean urls
            (/([a-z]:\\|\\\\|\/[a-z]+)/i.test(cleanText) && !cleanText.includes('http://') && !cleanText.includes('https://') && !cleanText.includes('/api/'));

        if (isBlacklisted) {
            // Log to developer console, but do not show in user terminal
            console.log('[Filtered Log]:', cleanText);
            return;
        }

        // 2. Map input strings to clean, premium product logs
        let friendlyMessage = null;
        let lineClass = 'info';

        if (textLower.includes('starting generation job')) {
            friendlyMessage = 'Analyzing prompt...';
            lineClass = 'active';
        } else if (textLower.includes('drafting manim code') || textLower.includes('generating manim code')) {
            friendlyMessage = 'Generating animation...';
            lineClass = 'active';
        } else if (textLower.includes('generated manim code successfully') || textLower.includes('writing manim scene')) {
            friendlyMessage = 'Writing animation scene...';
            lineClass = 'info';
        } else if (textLower.includes('patch') || textLower.includes('fix') || textLower.includes('fixing') || textLower.includes('troubleshooting') || textLower.includes('repairing') || textLower.includes('instructing gemini')) {
            friendlyMessage = 'Repairing animation...';
            lineClass = 'warning';
        } else if (textLower.includes('spawning manim') || textLower.includes('manim community')) {
            friendlyMessage = 'Rendering video...';
            lineClass = 'active';
        } else if (textLower.includes('rendering video') || textLower.includes('rendering...')) {
            friendlyMessage = 'Rendering video...';
            lineClass = 'active';
        } else if (textLower.includes('combining') || textLower.includes('movie file')) {
            friendlyMessage = 'Assembling video chunks...';
            lineClass = 'active';
        } else if (textLower.includes('file ready') || textLower.includes('finalizing')) {
            friendlyMessage = 'Finalizing video...';
            lineClass = 'info';
        } else if (textLower.includes('completed successfully') || textLower.includes('rendering completed') || textLower.includes('rendered and loaded') || textLower.includes('video generated successfully')) {
            friendlyMessage = 'Video generated successfully.';
            lineClass = 'success';
        } else if (textLower.includes('retrying generation')) {
            friendlyMessage = 'Retrying generation...';
            lineClass = 'warning';
        } else if (textLower.includes('service temporarily unavailable')) {
            friendlyMessage = 'AI service temporarily unavailable.';
            lineClass = 'error';
        } else if (textLower.includes('connection failed') || textLower.includes('connection error')) {
            friendlyMessage = 'Connection failed. Please try again.';
            lineClass = 'error';
        } else if (textLower.includes('manimic initialized')) {
            friendlyMessage = 'Manimic initialized.';
            lineClass = 'info';
        } else if (textLower.includes('rendering engine ready')) {
            friendlyMessage = 'Rendering engine ready.';
            lineClass = 'success';
        } else if (textLower.includes('enter a prompt to begin')) {
            friendlyMessage = 'Enter a prompt to begin.';
            lineClass = 'active';
        } else if (textLower.includes('ready for another prompt')) {
            friendlyMessage = 'Ready for another prompt.';
            lineClass = 'active';
        } else if (textLower.includes('loaded prompt from history')) {
            friendlyMessage = 'Loaded prompt from history.';
            lineClass = 'success';
        } else if (textLower.includes('attempt') && (textLower.includes('of') || textLower.includes('/'))) {
            const match = cleanText.match(/Attempt\s+(\d+)\s+of\s+(\d+)/i) || cleanText.match(/Attempt\s+(\d+)\/(\d+)/i);
            if (match) {
                friendlyMessage = `Attempt ${match[1]} of ${match[2]}`;
            } else {
                friendlyMessage = cleanText;
            }
            lineClass = 'warning';
        } else if (type === 'error') {
            friendlyMessage = 'Generation failed. Please try again.';
            lineClass = 'error';
        } else {
            // General translation fallback: if the log line doesn't match above, but is clean, check if we can format it
            // For example, Manim stdout log lines like "Animation 0: Write(Circle)..."
            const animationMatch = cleanText.match(/Animation\s+\d+:\s+(\w+)\(([^)]+)\)/i);
            const simpleAnimMatch = cleanText.match(/Animation\s+\d+:\s+(\w+)/i);
            if (animationMatch) {
                friendlyMessage = `Animating ${animationMatch[1]}...`;
                lineClass = 'active';
            } else if (simpleAnimMatch) {
                friendlyMessage = `Animating ${simpleAnimMatch[1]}...`;
                lineClass = 'active';
            } else if (cleanText.includes('%')) {
                // Progress percent updates from logs (e.g. 50%)
                const pctMatch = cleanText.match(/(\d+)%/);
                if (pctMatch) {
                    friendlyMessage = `Rendering progress: ${pctMatch[1]}%`;
                    lineClass = 'active';
                }
            }
        }

        // 3. If we mapped a friendly message, append it to the terminal
        if (friendlyMessage) {
            // Deduplicate generic status messages that should appear once per session
            const oncePerSessionMessages = [
                'Generating animation...',
                'Writing animation scene...',
                'Rendering video...',
                'Assembling video chunks...',
                'Finalizing video...',
                'Video generated successfully.',
                'Ready for another prompt.'
            ];

            if (oncePerSessionMessages.includes(friendlyMessage)) {
                if (loggedInSession.has(friendlyMessage)) {
                    return; // Skip duplicate message in this session
                }
                loggedInSession.add(friendlyMessage);
            }

            // Prevent exact duplicate consecutive logs to keep it clean (fallback guard)
            const lastLine = terminalBody.lastElementChild;
            if (lastLine) {
                const lastTextSpan = lastLine.querySelector('.terminal-text');
                if (lastTextSpan && lastTextSpan.innerText === friendlyMessage) {
                    // Update timestamp instead of adding a duplicate
                    const lastTimestampSpan = lastLine.querySelector('.terminal-timestamp');
                    if (lastTimestampSpan) {
                        lastTimestampSpan.innerText = `[${getCurrentTimeStr()}]`;
                    }
                    return;
                }
            }

            const timestamp = getCurrentTimeStr();
            const logLine = document.createElement('div');
            logLine.className = `terminal-line ${lineClass}`;
            logLine.innerHTML = `
                <span class="terminal-timestamp">[${timestamp}]</span>
                <span class="terminal-text">${escapeHtml(friendlyMessage)}</span>
            `;
            terminalBody.appendChild(logLine);

            // Auto scroll to bottom
            terminalBody.scrollTop = terminalBody.scrollHeight;
        }
    }

    function getCurrentTimeStr() {
        const now = new Date();
        const hrs = String(now.getHours()).padStart(2, '0');
        const mins = String(now.getMinutes()).padStart(2, '0');
        const secs = String(now.getSeconds()).padStart(2, '0');
        return `${hrs}:${mins}:${secs}`;
    }

    function loadVideo(url) {
        videoPlaceholder.classList.add('hidden');
        videoPlayer.classList.remove('hidden');
        videoSource.src = url;
        videoPlayer.load();
        
        // Auto play
        const playPromise = videoPlayer.play();
        if (playPromise !== undefined) {
            playPromise.catch(error => {
                console.log("Auto-play prevented by browser policy, waiting for user click.");
            });
        }

        // Setup download link
        downloadLink.href = url;
        exportControls.classList.remove('hidden');
    }

    // Load history gallery
    async function loadGallery() {
        try {
            const response = await fetch('/api/gallery');
            if (!response.ok) return;
            const items = await response.json();
            
            if (items.length === 0) {
                return;
            }

            // Clear empty message
            galleryGrid.innerHTML = '';

            items.forEach(item => {
                const card = document.createElement('div');
                card.className = 'gallery-card';
                
                // Format relative or neat date
                const dateStr = new Date(item.timestamp).toLocaleDateString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });

                card.innerHTML = `
                    <div class="gallery-card-preview">
                        <video class="gallery-card-video" controls preload="metadata">
                            <source src="${item.video_url}" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                    </div>
                    <div class="gallery-card-info">
                        <div class="gallery-card-prompt" title="${escapeHtml(item.prompt)}">${escapeHtml(item.prompt)}</div>
                        <div class="gallery-card-meta">
                            <span>Q: ${item.quality.toUpperCase()}</span>
                            <span>${dateStr}</span>
                        </div>
                    </div>
                `;

                card.addEventListener('click', (e) => {
                    // Populate prompt input when clicking the card details, but ignore play control clicks on video
                    if (e.target.closest('video')) {
                        return;
                    }
                    promptInput.value = item.prompt;
                    translateAndLog(`[SYSTEM] Loaded prompt from history job ${item.id}.`, 'system');
                });

                galleryGrid.appendChild(card);
            });
        } catch (error) {
            console.error('Failed to load gallery', error);
        }
    }

    function initTerminalMessages() {
        translateAndLog('[SYSTEM] Manimic initialized.', 'system');
        translateAndLog('[SYSTEM] Rendering engine ready.', 'system');
        translateAndLog('[SYSTEM] Enter a prompt to begin.', 'system');
    }

    function escapeHtml(text) {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
});
