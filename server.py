import os
import uuid
import subprocess
import time
import threading
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, send_file, jsonify, redirect, url_for, Response, request, stream_with_context
import re
import mimetypes

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Global state for queue and file management
queue = []
processing = None
completed_tasks = {}
task_lock = threading.Lock()
cleanup_interval = 300  # 5 minutes in seconds

# HTML template with JavaScript for live updates
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>IPA Signing Service</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .container { background: #f5f5f5; padding: 20px; border-radius: 8px; }
        .form-group { margin-bottom: 15px; }
        .progress-container { margin: 20px 0; }
        .progress-bar { height: 20px; background: #e0e0e0; border-radius: 10px; overflow: hidden; }
        .progress { height: 100%; background: #4caf50; width: 0%; transition: width 0.3s; }
        .hidden { display: none; }
        .queue-info { margin: 15px 0; }
        .download-section { margin-top: 20px; }
        .countdown { font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>IPA Signing Service</h1>
        
        <div id="upload-section">
            <form id="signing-form" enctype="multipart/form-data">
                <div class="form-group">
                    <label>IPA File:</label>
                    <input type="file" name="ipa" required>
                </div>
                <div class="form-group">
                    <label>Mobile Provision:</label>
                    <input type="file" name="mobileprovision" required>
                </div>
                <div class="form-group">
                    <label>P12 Certificate:</label>
                    <input type="file" name="p12" required>
                </div>
                <div class="form-group">
                    <label>P12 Password:</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit">Sign IPA</button>
            </form>
            
            <div id="queue-info" class="queue-info hidden">
                <h3>Queue Status</h3>
                <p>Your position in queue: <span id="queue-position">0</span></p>
            </div>
        </div>
        
        <div id="processing-section" class="hidden">
            <div class="progress-container">
                <h3>Uploading Files</h3>
                <div class="progress-bar">
                    <div class="progress" id="upload-progress"></div>
                </div>
            </div>
            
            <div id="processing-status">
                <h3>Processing...</h3>
                <p>This may take several seconds</p>
            </div>
        </div>
        
        <div id="download-section" class="download-section hidden">
            <h3>Signing Complete!</h3>
            <a id="download-link" class="button">Download Signed IPA</a>
            <p>Link expires in: <span id="countdown" class="countdown">5:00</span> minutes</p>
        </div>
    </div>

    <script>
        const form = document.getElementById('signing-form');
        const uploadSection = document.getElementById('upload-section');
        const queueInfo = document.getElementById('queue-info');
        const processingSection = document.getElementById('processing-section');
        const downloadSection = document.getElementById('download-section');
        const queuePosition = document.getElementById('queue-position');
        const uploadProgress = document.getElementById('upload-progress');
        const downloadLink = document.getElementById('download-link');
        const countdownElement = document.getElementById('countdown');
        
        let taskId = null;
        let countdownInterval = null;
        
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(form);
            const response = await fetch('/api/sign', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            taskId = data.task_id;
            
            // Show queue position
            queueInfo.classList.remove('hidden');
            updateQueuePosition(data.position);
            
            // Start checking queue status
            monitorQueueStatus();
        });
        
        function updateQueuePosition(position) {
            queuePosition.textContent = position;
            if (position === 0) {
                queueInfo.classList.add('hidden');
                uploadSection.classList.add('hidden');
                processingSection.classList.remove('hidden');
                simulateUploadProgress();
            }
        }
        
        function simulateUploadProgress() {
            let width = 0;
            const interval = setInterval(() => {
                width += 5;
                uploadProgress.style.width = `${width}%`;
                if (width >= 100) {
                    clearInterval(interval);
                    checkProcessingStatus();
                }
            }, 100);
        }
        
        async function monitorQueueStatus() {
            const response = await fetch(`/api/queue_position?task_id=${taskId}`);
            const data = await response.json();
            
            updateQueuePosition(data.position);
            
            if (data.position > 0) {
                setTimeout(monitorQueueStatus, 2000);
            }
        }
        
        async function checkProcessingStatus() {
            try {
                const response = await fetch(`/api/status?task_id=${taskId}`);
                const data = await response.json();
        
                if (!response.ok) throw new Error(data.status || 'Unknown error');
        
                if (data.status === 'processing' || data.status === 'queued') {
                    setTimeout(checkProcessingStatus, 2000);
                } else if (data.status === 'completed') {
                    showDownloadSection(data.filename);
                } else if (data.status === 'not_found') {
                    alert('Task not found. Please try again.');
                    location.reload();
                } else if (data.status.includes('error')) {
                    alert(`Error: ${data.status}`);
                    location.reload();
                }
            } catch (error) {
                console.error('Error checking status:', error);
                alert('Failed to check status. Please try again.');
                location.reload();
            }
        }
        
        function showDownloadSection(filename) {
            processingSection.classList.add('hidden');
            downloadSection.classList.remove('hidden');
            downloadLink.href = `/download?task_id=${taskId}&filename=${filename}`;
            
            // Start countdown timer
            let timeLeft = 300;
            updateCountdown(timeLeft);
            
            countdownInterval = setInterval(() => {
                timeLeft -= 1;
                if (timeLeft <= 0) {
                    clearInterval(countdownInterval);
                    downloadSection.innerHTML = '<p class="expired">Download link has expired</p>';
                } else {
                    updateCountdown(timeLeft);
                }
            }, 1000);
        }
        
        function updateCountdown(seconds) {
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            countdownElement.textContent = `${mins}:${secs < 10 ? '0' : ''}${secs}`;
        }
    </script>
</body>
</html>
"""

def cleanup_expired_files():
    """Remove expired files and task entries"""
    now = datetime.now()
    expired = []
    
    with task_lock:
        for task_id, task_data in list(completed_tasks.items()):
            # Only check tasks that have 'completed_time'
            if 'completed_time' in task_data and now - task_data['completed_time'] > timedelta(seconds=cleanup_interval):
                expired.append(task_id)
                try:
                    os.remove(task_data['signed_ipa'])
                    print(f"Removed expired file: {task_data['signed_ipa']}")
                except Exception as e:
                    print(f"Error removing file: {e}")
        
        for task_id in expired:
            del completed_tasks[task_id]

def process_queue():
    """Process tasks from the queue"""
    global processing
    
    while True:
        time.sleep(1)
        with task_lock:
            if queue and not processing:
                processing = queue.pop(0)
                task_id = processing
                
                try:
                    task_dir = os.path.join(UPLOAD_FOLDER, task_id)
                    ipa_path = os.path.join(task_dir, 'app.ipa')
                    mobile_prov_path = os.path.join(task_dir, 'app.mobileprovision')
                    p12_path = os.path.join(task_dir, 'cert.p12')
                    signed_ipa = os.path.join(task_dir, 'signed.ipa')
                    
                    # Unzip IPA temporarily if needed (zsign may require extracted payload)
                    payload_path = os.path.join(task_dir, 'Payload', 'LiveContainer.app')
                    
                    # Ensure _CodeSignature folders exist for all frameworks and plugins
                    frameworks_to_sign = []
                    for root, dirs, files in os.walk(payload_path):
                        for d in dirs:
                            if d.endswith('.framework') or d.endswith('.appex'):
                                frameworks_to_sign.append(os.path.join(root, d))
                    
                    for fw_path in frameworks_to_sign:
                        codesig_path = os.path.join(fw_path, '_CodeSignature')
                        os.makedirs(codesig_path, exist_ok=True)
                    
                    # Sign the IPA
                    subprocess.run([
                        'zsign',
                        '-k', p12_path,
                        '-p', completed_tasks[task_id]['password'],
                        '-m', mobile_prov_path,
                        '-o', signed_ipa,
                        ipa_path
                    ], check=True)
                    
                    # Cleanup intermediate files
                    for f in [ipa_path, mobile_prov_path, p12_path]:
                        os.remove(f)
                    
                    # Update task status
                    completed_tasks[task_id].update({
                        'status': 'completed',
                        'signed_ipa': signed_ipa,
                        'filename': 'signed.ipa',
                        'completed_time': datetime.now()
                    })
                    
                except Exception as e:
                    completed_tasks[task_id]['status'] = f'error: {str(e)}'
                finally:
                    processing = None

# Start the queue processing thread
threading.Thread(target=process_queue, daemon=True).start()

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/sign', methods=['POST'])
def sign_api():
    """Handle file upload and add to processing queue"""
    task_id = str(uuid.uuid4())
    task_dir = os.path.join(UPLOAD_FOLDER, task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    # Save uploaded files
    request.files['ipa'].save(os.path.join(task_dir, 'app.ipa'))
    request.files['mobileprovision'].save(os.path.join(task_dir, 'app.mobileprovision'))
    request.files['p12'].save(os.path.join(task_dir, 'cert.p12'))
    
    # Add to queue
    with task_lock:
        queue_position = len(queue)
        queue.append(task_id)
        
        completed_tasks[task_id] = {
            'status': 'queued',
            'password': request.form['password'],
            'created_time': datetime.now(),
            'filename': None,
            'signed_ipa': None
        }
    
    return jsonify({
        'task_id': task_id,
        'position': queue_position
    })

@app.route('/api/queue_position')
def queue_position():
    """Get current queue position for a task"""
    task_id = request.args.get('task_id')
    with task_lock:
        if task_id in queue:
            return jsonify({'position': queue.index(task_id)})
        elif task_id in completed_tasks:
            return jsonify({'position': 0})
        return jsonify({'position': -1})  # -1 indicates task not found

@app.route('/api/status')
def task_status():
    """Check status of a processing task"""
    task_id = request.args.get('task_id')
    with task_lock:
        if task_id not in completed_tasks:
            return jsonify({
                'status': 'not_found',
                'filename': None
            })
            
        return jsonify({
            'status': completed_tasks[task_id]['status'],
            'filename': completed_tasks[task_id].get('filename')
        })

@app.route('/download', methods=['GET', 'HEAD'])
def download():
    task_id = request.args.get('task_id')
    filename = request.args.get('filename', 'signed.ipa')

    # Cleanup expired stuff (optional but good)
    cleanup_expired_files()

    with task_lock:
        if task_id not in completed_tasks or completed_tasks[task_id]['status'] != 'completed':
            return "Invalid or expired download link", 404
        path = completed_tasks[task_id]['signed_ipa']

    if not os.path.exists(path):
        return "File not found", 404

    size = os.path.getsize(path)
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = 'application/octet-stream'

    # Helper to stream a byte range
    def stream_range(start, end, chunk_size=8192):
        with open(path, 'rb') as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                read_len = min(chunk_size, remaining)
                chunk = f.read(read_len)
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    # If client requested a range
    range_header = request.headers.get('Range', None)
    if range_header:
        m = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if not m:
            return Response(status=416)
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
        if start >= size or start > end:
            return Response(status=416)

        end = min(end, size - 1)
        length = end - start + 1

        headers = {
            'Content-Range': f'bytes {start}-{end}/{size}',
            'Accept-Ranges': 'bytes',
            'Content-Length': str(length),
            'Content-Disposition': f'attachment; filename="{filename}"'
        }

        # HEAD should not return body
        if request.method == 'HEAD':
            return Response(status=206, headers=headers)

        return Response(
            stream_with_context(stream_range(start, end)),
            status=206,
            mimetype=mime_type,
            headers=headers
        )

    # No Range header — normal full download (but still advertise Accept-Ranges)
    headers = {
        'Accept-Ranges': 'bytes',
        'Content-Length': str(size),
        'Content-Disposition': f'attachment; filename="{filename}"'
    }

    if request.method == 'HEAD':
        return Response(status=200, headers=headers)

    # stream entire file in chunks
    return Response(
        stream_with_context(stream_range(0, size - 1)),
        status=200,
        mimetype=mime_type,
        headers=headers
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
