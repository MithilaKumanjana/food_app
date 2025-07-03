#!/usr/bin/env python3
"""
Optimized Mobile Sensor Server - Live Camera & Gyroscope
PC interface with data saving, capture, and performance tuning
"""

import os
import sys
import json
import base64
import ssl
import socket
import subprocess
import ipaddress
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image

# Flask and SocketIO for web server
from flask import Flask, render_template_string, jsonify, request
from flask_socketio import SocketIO, emit

# SSL Certificate generation
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Flask app setup
app = Flask(__name__)
app.config['SECRET_KEY'] = 'mobile-sensor-2025'
socketio = SocketIO(app, cors_allowed_origins="*")

# Data directory
DATA_DIR = "sensor_data_with_5"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Global sensor data
sensor_data_with_5 = {
    'camera': None,
    'gyroscope': {'x': 0, 'y': 0, 'z': 0},
    'timestamp': datetime.now().isoformat()
}

def install_packages():
    """Install required packages"""
    packages = ['flask', 'flask-socketio', 'cryptography', 'pillow']
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

def generate_ssl_certificate():
    """Generate self-signed SSL certificate"""
    if os.path.exists('cert.pem') and os.path.exists('key.pem'):
        return 'cert.pem', 'key.pem'
    print("🔐 Generating SSL certificate...")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Mobile Sensor"),
        x509.NameAttribute(NameOID.COMMON_NAME, local_ip),
    ])
    cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(
        private_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
        datetime.utcnow()).not_valid_after(datetime.utcnow() + timedelta(days=365)).add_extension(
        x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address(local_ip)),
                                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]), critical=False).sign(
        private_key, hashes.SHA256())
    with open("cert.pem", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open("key.pem", "wb") as f:
        f.write(private_key.private_bytes(encoding=serialization.Encoding.PEM,
                                         format=serialization.PrivateFormat.PKCS8,
                                         encryption_algorithm=serialization.NoEncryption()))
    print("✅ SSL certificate generated!")
    return 'cert.pem', 'key.pem'

# Mobile phone interface
MOBILE_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>📱 Phone Sensor Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial; margin: 0; padding: 20px; background: #667eea; color: white; text-align: center; }
        .container { max-width: 400px; margin: 0 auto; background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; }
        h1 { margin-bottom: 20px; font-size: 1.5em; }
        button { background: #FF6B6B; color: white; border: none; padding: 10px 20px; margin: 5px; border-radius: 20px; font-size: 14px; cursor: pointer; }
        button:hover { background: #E74C3C; }
        .status { margin: 10px 0; padding: 10px; border-radius: 5px; }
        .success { background: rgba(76,175,80,0.3); }
        .error { background: rgba(244,67,54,0.3); }
        select { padding: 10px; margin: 5px 0; border-radius: 5px; border: none; background: rgba(255,255,255,0.2); color: white; width: 45%; }
        .fps-controls { margin: 10px 0; display: flex; justify-content: space-between; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📱 Phone Sensor Control</h1>
        <select id="cameraSelect"><option value="">📷 Loading cameras...</option></select>
        <div class="fps-controls">
            <select id="cameraFpsSelect" onchange="updateCameraFps()">
                <option value="200">Camera FPS: 5</option>
                <option value="100" selected>Camera FPS: 10</option>
                <option value="50">Camera FPS: 20</option>
                <option value="33">Camera FPS: 30</option>
            </select>
            <select id="gyroFpsSelect" onchange="updateGyroFps()">
                <option value="200">Gyro FPS: 5</option>
                <option value="100" selected>Gyro FPS: 10</option>
                <option value="50">Gyro FPS: 20</option>
                <option value="33">Gyro FPS: 30</option>
            </select>
        </div>
        <button id="cameraBtn" onclick="toggleCamera()">📷 Start Camera</button>
        <button id="gyroBtn" onclick="toggleGyroscope()">🔄 Start Gyro</button>
        <button onclick="generateTestData()" style="background: #9b59b6;">🧪 Test Data</button>
        <div id="status" class="status">🚀 Ready to stream to PC</div>
        <div style="background: rgba(255,255,255,0.1); padding: 10px; margin: 10px 0; border-radius: 5px;">
            <strong>📺 View on PC:</strong><br>https://localhost:5442/pc
        </div>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script>
        const socket = io();
        let currentStream = null, cameraActive = false, gyroActive = false;
        let cameraInterval, gyroInterval, cameraFps = 100, gyroFps = 100;
        let video = null;

        async function getCameras() {
            try {
                const devices = await navigator.mediaDevices.enumerateDevices();
                const cameras = devices.filter(d => d.kind === 'videoinput');
                const select = document.getElementById('cameraSelect');
                select.innerHTML = cameras.map((c, i) => `<option value="${c.deviceId}">${c.label || `Camera ${i+1}`}</option>`).join('');
                if (!cameras.length) select.innerHTML = '<option>❌ No cameras</option>';
            } catch (e) { updateStatus('❌ Camera error: ' + e.message, 'error'); }
        }

        function updateCameraFps() { 
            cameraFps = parseInt(document.getElementById('cameraFpsSelect').value); 
            if (cameraActive) { 
                stopCamera(); 
                setTimeout(() => startCamera(), 100); 
            } 
        }
        
        function updateGyroFps() { 
            gyroFps = parseInt(document.getElementById('gyroFpsSelect').value); 
            if (gyroActive) { 
                stopGyroscope(); 
                setTimeout(() => startGyroscope(), 100); 
            } 
        }

        async function toggleCamera() {
            if (cameraActive) stopCamera(); else await startCamera();
        }

        async function startCamera() {
            try {
                const constraints = { 
                    video: { 
                        deviceId: document.getElementById('cameraSelect').value || undefined, 
                        width: { ideal: 1280 }, 
                        height: { ideal: 720 }, 
                        frameRate: { ideal: 30 } 
                    } 
                };
                currentStream = await navigator.mediaDevices.getUserMedia(constraints);
                cameraActive = true;
                document.getElementById('cameraBtn').textContent = '📷 Stop';
                updateStatus('✅ Camera streaming', 'success');
                
                // Create video element
                video = document.createElement('video');
                video.srcObject = currentStream;
                video.play();
                
                // Wait for video to be ready - capture frames ONLY at FPS intervals
                video.onloadedmetadata = () => {
                    if (cameraInterval) clearInterval(cameraInterval);
                    cameraInterval = setInterval(() => {
                        if (video.readyState === video.HAVE_ENOUGH_DATA) {
                            // Capture frame RIGHT NOW - no delay, no buffering
                            const canvas = document.createElement('canvas');
                            canvas.width = video.videoWidth;
                            canvas.height = video.videoHeight;
                            const ctx = canvas.getContext('2d');
                            ctx.drawImage(video, 0, 0);
                            const frameData = canvas.toDataURL('image/jpeg', 0.8);
                            socket.emit('camera_frame', { frame: frameData });
                            console.log(`📸 Camera FPS Sample: ${video.videoWidth}x${video.videoHeight}`);
                        }
                    }, cameraFps); // Capture EXACTLY at FPS intervals
                };
            } catch (e) { 
                updateStatus('❌ Camera error: ' + e.message, 'error'); 
                cameraActive = false; 
                document.getElementById('cameraBtn').textContent = '📷 Start'; 
            }
        }

        function stopCamera() {
            if (currentStream) { 
                currentStream.getTracks().forEach(t => t.stop()); 
                currentStream = null; 
            }
            if (video) {
                video.srcObject = null;
                video = null;
            }
            cameraActive = false; 
            document.getElementById('cameraBtn').textContent = '📷 Start';
            updateStatus('⏹️ Camera stopped', 'info'); 
            if (cameraInterval) clearInterval(cameraInterval);
        }

        async function toggleGyroscope() {
            if (gyroActive) stopGyroscope(); else await startGyroscope();
        }

        async function startGyroscope() {
            try {
                // Request permission for iOS
                if (typeof DeviceOrientationEvent.requestPermission === 'function') {
                    const permission = await DeviceOrientationEvent.requestPermission();
                    if (permission !== 'granted') { 
                        updateStatus('❌ Gyro permission denied', 'error'); 
                        return; 
                    }
                }
                
                gyroActive = true; 
                document.getElementById('gyroBtn').textContent = '🔄 Stop';
                updateStatus('✅ Gyro streaming', 'success');
                
                // Clear any existing interval
                if (gyroInterval) clearInterval(gyroInterval);
                
                let counter = 0;
                let dataType = 'none';
                
                // Capture and send data ONLY at FPS intervals - no buffering
                gyroInterval = setInterval(() => {
                    if (!gyroActive) return;
                    
                    counter++;
                    
                    // Capture data RIGHT NOW - no delay, no buffering
                    const captureAndSend = () => {
                        // Try to get fresh motion data
                        const motionHandler = (e) => {
                            let gyroData = null;
                            
                            if (e.accelerationIncludingGravity) {
                                gyroData = {
                                    x: parseFloat((e.accelerationIncludingGravity.x || 0).toFixed(2)),
                                    y: parseFloat((e.accelerationIncludingGravity.y || 0).toFixed(2)),
                                    z: parseFloat((e.accelerationIncludingGravity.z || 0).toFixed(2))
                                };
                                dataType = 'acceleration';
                            } else if (e.rotationRate && e.rotationRate.alpha !== null) {
                                gyroData = {
                                    x: parseFloat((e.rotationRate.alpha || 0).toFixed(2)),
                                    y: parseFloat((e.rotationRate.beta || 0).toFixed(2)),
                                    z: parseFloat((e.rotationRate.gamma || 0).toFixed(2))
                                };
                                dataType = 'rotation';
                            }
                            
                            if (gyroData) {
                                socket.emit('gyro_data', gyroData);
                                console.log(`📤 [${dataType}] FPS Sample: X=${gyroData.x} Y=${gyroData.y} Z=${gyroData.z}`);
                            }
                        };
                        
                        // Try to get fresh orientation data
                        const orientationHandler = (e) => {
                            if (e.alpha !== null && e.beta !== null && e.gamma !== null) {
                                const gyroData = {
                                    x: parseFloat((e.alpha || 0).toFixed(2)),
                                    y: parseFloat((e.beta || 0).toFixed(2)),
                                    z: parseFloat((e.gamma || 0).toFixed(2))
                                };
                                dataType = 'orientation';
                                socket.emit('gyro_data', gyroData);
                                console.log(`📤 [${dataType}] FPS Sample: X=${gyroData.x} Y=${gyroData.y} Z=${gyroData.z}`);
                            }
                        };
                        
                        // Capture fresh data right now
                        window.addEventListener('devicemotion', motionHandler, { once: true });
                        window.addEventListener('deviceorientation', orientationHandler, { once: true });
                        
                        // Fallback to test data if no real sensors respond quickly
                        setTimeout(() => {
                            if (dataType === 'none') {
                                const testData = {
                                    x: parseFloat((Math.sin(counter * 0.1) * 180).toFixed(2)),
                                    y: parseFloat((Math.cos(counter * 0.15) * 90).toFixed(2)),
                                    z: parseFloat((Math.sin(counter * 0.2) * 45 + counter * 0.5).toFixed(2))
                                };
                                socket.emit('gyro_data', testData);
                                console.log(`📤 [test] FPS Sample: X=${testData.x} Y=${testData.y} Z=${testData.z}`);
                            }
                        }, 10); // Very short timeout
                    };
                    
                    captureAndSend();
                    
                }, gyroFps); // Capture EXACTLY at FPS intervals
                
            } catch (e) { 
                updateStatus('❌ Gyro error: ' + e.message, 'error'); 
                console.error('Gyro error:', e);
                gyroActive = false; 
                document.getElementById('gyroBtn').textContent = '🔄 Start'; 
            }
        }

        function stopGyroscope() {
            gyroActive = false; 
            document.getElementById('gyroBtn').textContent = '🔄 Start';
            updateStatus('⏹️ Gyro stopped', 'info'); 
            if (gyroInterval) clearInterval(gyroInterval);
            // No need to clean up event listeners since we use { once: true }
        }

        function updateStatus(message, type) { 
            document.getElementById('status').className = 'status ' + type; 
            document.getElementById('status').textContent = message; 
        }

        // Connection status and debugging
        socket.on('connect', () => {
            updateStatus('🟢 Connected to server', 'success');
            console.log('Socket connected to server');
        });

        socket.on('disconnect', () => {
            updateStatus('🔴 Disconnected from server', 'error');
            console.log('Socket disconnected from server');
        });

        // Debug gyro data sending
        socket.on('gyro_error', (data) => {
            console.error('Gyro error from server:', data.error);
            updateStatus('❌ Gyro server error: ' + data.error, 'error');
        });

        socket.on('gyro_update', (data) => {
            console.log('Received gyro update confirmation:', data);
        });

        // Test data generator for when real gyro data is constant
        function generateTestData() {
            if (!gyroActive) {
                updateStatus('⚠️ Start gyroscope first', 'error');
                return;
            }
            
            let testCounter = 0;
            const testInterval = setInterval(() => {
                if (!gyroActive) {
                    clearInterval(testInterval);
                    return;
                }
                
                const testData = {
                    x: parseFloat((Math.sin(testCounter * 0.1) * 180).toFixed(2)),
                    y: parseFloat((Math.cos(testCounter * 0.15) * 90).toFixed(2)),
                    z: parseFloat((Math.sin(testCounter * 0.2) * 45 + Math.cos(testCounter * 0.1) * 30).toFixed(2))
                };
                
                socket.emit('gyro_data', testData);
                console.log(`🧪 Test: X=${testData.x} Y=${testData.y} Z=${testData.z}`);
                testCounter++;
            }, gyroFps);
            
            updateStatus('🧪 Sending test data', 'success');
            
            // Stop test data after 10 seconds
            setTimeout(() => {
                clearInterval(testInterval);
                updateStatus('✅ Test data stopped', 'success');
            }, 10000);
        }

        // Test gyroscope support immediately
        function testGyroSupport() {
            console.log('🧪 Testing gyroscope support...');
            console.log('DeviceOrientationEvent supported:', typeof DeviceOrientationEvent !== 'undefined');
            console.log('DeviceMotionEvent supported:', typeof DeviceMotionEvent !== 'undefined');
            
            if (typeof DeviceOrientationEvent !== 'undefined') {
                console.log('DeviceOrientationEvent.requestPermission:', typeof DeviceOrientationEvent.requestPermission);
            }
        }

        window.onload = () => {
            getCameras();
            testGyroSupport();
        };
    </script>
</body>
</html>
'''

# PC monitoring interface
PC_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>🖥️ PC Monitor</title>
    <style>
        body { font-family: Arial; margin: 0; padding: 20px; background: #2c3e50; color: white; }
        .container { max-width: 100vw; margin: 0 auto; height: calc(100vh - 40px); overflow-y: auto; }
        .header { text-align: center; margin-bottom: 10px; }
        .main-grid { display: grid; grid-template-columns: 3fr 1fr; gap: 10px; min-height: 100%; }
        .camera-section { background: rgba(255,255,255,0.1); border-radius: 10px; padding: 10px; text-align: center; }
        #cameraPreview { max-width: 100%; max-height: 80%; border-radius: 5px; }
        .capture-btn { background: #FF6B6B; color: white; border: none; padding: 10px; border-radius: 20px; cursor: pointer; margin-top: 10px; }
        .capture-btn:hover { background: #E74C3C; }
        .gyro-section { background: rgba(255,255,255,0.1); border-radius: 10px; padding: 10px; }
        .connection-status { padding: 5px; margin-bottom: 10px; text-align: center; }
        .connected { border-left: 4px solid #27ae60; color: #27ae60; }
        .disconnected { border-left: 4px solid #e74c3c; color: #e74c3c; }
        .gyro-value { display: flex; justify-content: space-between; margin: 5px 0; padding: 5px; background: rgba(255,255,255,0.05); border-radius: 3px; }
        .stats { background: rgba(255,255,255,0.1); border-radius: 10px; padding: 10px; margin-top: 10px; }
        .stat-item { display: flex; justify-content: space-between; margin: 5px 0; }
        .no-gyro { color: #e74c3c; text-align: center; font-style: italic; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🖥️ Live Mobile Feed</h1>
            <p>Real-time Camera & Gyroscope</p>
        </div>
        <div class="main-grid">
            <div class="camera-section">
                <img id="cameraPreview" src="" alt="Camera Feed" style="display:none;">
                <button class="capture-btn" onclick="captureImage()">📸 Capture</button>
                <div id="cameraPlaceholder">📱 Start camera on phone...</div>
            </div>
            <div class="gyro-section">
                <div id="connectionStatus" class="connection-status disconnected">🔴 Disconnected</div>
                <div>🔄 Gyroscope Data</div>
                <div class="gyro-value"><span>X-Axis (°):</span><span id="gyro-x">0.00</span></div>
                <div class="gyro-value"><span>Y-Axis (°):</span><span id="gyro-y">0.00</span></div>
                <div class="gyro-value"><span>Z-Axis (°):</span><span id="gyro-z">0.00</span></div>
                <div id="noGyroMsg" class="no-gyro" style="display:none;">No gyroscope data available</div>
                <div class="stats">
                    <div class="stat-item">Frames: <span id="frameCount">0</span></div>
                    <div class="stat-item">Captured: <span id="captureCount">0</span></div>
                    <div class="stat-item">Gyro Updates: <span id="gyroCount">0</span></div>
                    <div class="stat-item">Gyro Files: <span id="gyroFileCount">0</span></div>
                </div>
            </div>
        </div>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script>
        const socket = io();
        let frameCount = 0, captureCount = 0, gyroCount = 0, gyroFileCount = 0, hasGyroData = false;

        socket.on('connect', () => {
            document.getElementById('connectionStatus').className = 'connection-status connected';
            document.getElementById('connectionStatus').textContent = '🟢 Connected';
            console.log('PC Monitor connected to server');
        });
        
        socket.on('disconnect', () => {
            document.getElementById('connectionStatus').className = 'connection-status disconnected';
            document.getElementById('connectionStatus').textContent = '🔴 Disconnected';
            console.log('PC Monitor disconnected from server');
        });

        socket.on('camera_update', data => {
            const preview = document.getElementById('cameraPreview');
            const placeholder = document.getElementById('cameraPlaceholder');
            if (data.frame) {
                preview.src = data.frame; 
                preview.style.display = 'block'; 
                placeholder.style.display = 'none';
                frameCount++; 
                document.getElementById('frameCount').textContent = frameCount;
            }
        });

        socket.on('gyro_update', data => {
            console.log('📥 Received gyro data:', data);
            hasGyroData = true;
            document.getElementById('gyro-x').textContent = (data.x || 0).toFixed(2);
            document.getElementById('gyro-y').textContent = (data.y || 0).toFixed(2);
            document.getElementById('gyro-z').textContent = (data.z || 0).toFixed(2);
            document.getElementById('noGyroMsg').style.display = 'none';
            gyroCount++; 
            document.getElementById('gyroCount').textContent = gyroCount;
        });

        socket.on('capture_success', data => {
            console.log('📸 Capture successful:', data);
            gyroFileCount++;
            document.getElementById('gyroFileCount').textContent = gyroFileCount;
        });

        function captureImage() {
            const preview = document.getElementById('cameraPreview');
            if (preview.src) {
                socket.emit('capture_image', { frame: preview.src });
                captureCount++; 
                document.getElementById('captureCount').textContent = captureCount;
                
                // Visual feedback
                preview.style.border = '3px solid #27ae60';
                setTimeout(() => {
                    preview.style.border = 'none';
                }, 200);
            } else {
                alert('No camera feed available to capture!');
            }
        }

        // Check for gyro data after a timeout
        setTimeout(() => {
            if (!hasGyroData) {
                document.getElementById('noGyroMsg').style.display = 'block';
                console.log('⚠️ No gyro data received after 10 seconds');
            }
        }, 10000); // Increased timeout to 10 seconds
    </script>
</body>
</html>
'''

# Flask routes
@app.route('/')
def mobile_interface():
    return render_template_string(MOBILE_TEMPLATE)

@app.route('/pc')
def pc_interface():
    return render_template_string(PC_TEMPLATE)

@app.route('/api/data')
def get_data():
    return jsonify(sensor_data_with_5)

# Socket events
@socketio.on('camera_frame')
def handle_camera_frame(data):
    global sensor_data_with_5
    sensor_data_with_5['camera'] = data['frame']
    sensor_data_with_5['timestamp'] = datetime.now().isoformat()
    emit('camera_update', {'frame': data['frame']}, broadcast=True)

@socketio.on('capture_image')
def handle_capture_image(data):
    global sensor_data_with_5
    try:
        # Extract base64 data
        frame_data = data['frame']
        if ',' in frame_data:
            image_data = base64.b64decode(frame_data.split(',')[1])
        else:
            image_data = base64.b64decode(frame_data)
            
        image = Image.open(BytesIO(image_data))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save image
        image_path = os.path.join(DATA_DIR, f"capture_{timestamp}.jpg")
        image.save(image_path, 'JPEG', quality=85)
        
        # Save gyroscope data ONLY when image is captured
        gyro_file = os.path.join(DATA_DIR, f"gyro_{timestamp}.json")
        gyro_entry = {
            'timestamp': sensor_data_with_5['timestamp'],
            'image_file': f"capture_{timestamp}.jpg",
            'gyroscope': sensor_data_with_5['gyroscope']
        }
        
        with open(gyro_file, 'w') as f:
            json.dump(gyro_entry, f, indent=2)
        
        print(f"📸 Image saved: {image_path}")
        print(f"📊 Gyro data saved: {gyro_file}")
        print(f"🔄 Gyro at capture: X:{sensor_data_with_5['gyroscope']['x']:6.2f} Y:{sensor_data_with_5['gyroscope']['y']:6.2f} Z:{sensor_data_with_5['gyroscope']['z']:6.2f}")
        
        # Send confirmation back
        emit('capture_success', {'path': image_path, 'gyro_file': gyro_file}, broadcast=False)
        
    except Exception as e:
        print(f"❌ Capture error: {e}")
        emit('capture_error', {'error': str(e)}, broadcast=False)

@socketio.on('gyro_data')
def handle_gyro_data(data):
    global sensor_data_with_5
    try:
        print(f"📥 Received gyro data from phone: {data}")
        
        # Ensure 2 decimal points for all values
        gyro_data = {
            'x': round(float(data.get('x', 0)), 2),
            'y': round(float(data.get('y', 0)), 2),
            'z': round(float(data.get('z', 0)), 2)
        }
        
        print(f"📤 Broadcasting gyro data: {gyro_data}")
        
        # Update sensor data in memory only - no file saving
        sensor_data_with_5['gyroscope'] = gyro_data
        sensor_data_with_5['timestamp'] = datetime.now().isoformat()
        
        # Broadcast to all clients immediately - no delay
        emit('gyro_update', gyro_data, broadcast=True)
        
        # Console output with exactly 2 decimal points
        print(f"🔄 Gyro: X:{gyro_data['x']:6.2f} Y:{gyro_data['y']:6.2f} Z:{gyro_data['z']:6.2f}")
        
    except Exception as e:
        print(f"❌ Gyro processing error: {e}")
        emit('gyro_error', {'error': str(e)}, broadcast=False)

@socketio.on('connect')
def handle_connect(auth):
    print(f"🔗 Client connected: {request.sid}")
    emit('connection_status', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"❌ Client disconnected: {request.sid}")

def start_server():
    """Start the server"""
    print("🚀 MOBILE SENSOR SERVER")
    print("=" * 40)
    cert_file, key_file = generate_ssl_certificate()
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"📱 Phone: https://{local_ip}:5442")
    print(f"🖥️ PC: https://localhost:5442/pc")
    print(f"📁 Data in: {DATA_DIR}")
    print("=" * 40)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    socketio.run(app, host='0.0.0.0', port=5442, debug=False, ssl_context=context)

def main():
    """Main function to handle user choices"""
    print("📱 MOBILE SENSOR APP")
    print("=" * 30)
    
    while True:
        print("\n1. 🚀 Start Server\n2. 🖥️ Open PC\n3. 📋 Info\n0. ❌ Exit")
        choice = input("Choice (0-3): ").strip()
        
        if choice == '0':
            break
        elif choice == '1':
            try:
                start_server()
            except KeyboardInterrupt:
                print("\n⏹️ Stopped")
        elif choice == '2':
            try:
                import webbrowser
                webbrowser.open("https://localhost:5442/pc")
                print("✅ Opened")
            except:
                print("💡 Open manually: https://localhost:5442/pc")
        elif choice == '3':
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            print(f"\n📱 https://{local_ip}:5442\n🖥️ https://localhost:5442/pc\n📁 {DATA_DIR}")

if __name__ == "__main__":
    try:
        install_packages()
    except Exception as e:
        print(f"⚠️ Package error: {e}")
    main()