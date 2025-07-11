
#!/usr/bin/env python3
"""
Optimized Mobile Sensor Server - Live Camera & Gyroscope
Mobile interface with live preview and capture, PC for data saving
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
DATA_DIR = "gyro_logic_photos"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Global sensor data
gyro_logic_photos = {
    'camera': None,
    'gyroscope': {'x': 0, 'y': 0, 'z': 0},
    'timestamp': datetime.now().isoformat()
}

# Gyroscope range based on provided data
GYRO_RANGES = {
    'x': {'mean': -0.4533333333, 'std_dev': 0.2270247341},
    'y': {'mean': 5.246666667, 'std_dev': 2.060253304},
    'z': {'mean': 7.68, 'std_dev': 1.55501915}
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

# Mobile phone interface with live preview and capture
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
        .gyro-display { margin: 10px 0; padding: 10px; background: rgba(255,255,255,0.1); border-radius: 5px; }
        video { max-width: 100%; border-radius: 5px; }
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
        <button id="startBtn" onclick="toggleSensors()">📷🔄 Start Sensors</button>
        <div id="status" class="status">🚀 Ready to stream to PC</div>
        <div class="gyro-display" id="gyroDisplay">🔄 Gyro: X: 0.00, Y: 0.00, Z: 0.00</div>
        <video id="videoPreview" autoplay playsinline></video>
        <button id="captureBtn" onclick="captureImage()" disabled>📸 Capture</button>
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

        async function toggleSensors() {
            if (cameraActive && gyroActive) {
                stopCamera();
                stopGyroscope();
            } else if (!cameraActive && !gyroActive) {
                await startCamera();
                await startGyroscope();
            }
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
                document.getElementById('startBtn').textContent = '⏹️ Stop Sensors';
                updateStatus('✅ Camera streaming', 'success');
                
                video = document.getElementById('videoPreview');
                video.srcObject = currentStream;
                video.play();
            } catch (e) { 
                updateStatus('❌ Camera error: ' + e.message, 'error'); 
                cameraActive = false; 
                document.getElementById('startBtn').textContent = '📷🔄 Start Sensors'; 
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
            document.getElementById('startBtn').textContent = '📷🔄 Start Sensors';
            updateStatus('⏹️ Camera stopped', 'info'); 
        }

        async function startGyroscope() {
            try {
                if (typeof DeviceOrientationEvent.requestPermission === 'function') {
                    const permission = await DeviceOrientationEvent.requestPermission();
                    if (permission !== 'granted') { 
                        updateStatus('❌ Gyro permission denied', 'error'); 
                        return; 
                    }
                }
                
                gyroActive = true; 
                updateStatus('✅ Gyro streaming', 'success');
                
                if (gyroInterval) clearInterval(gyroInterval);
                
                let counter = 0;
                let dataType = 'none';
                
                gyroInterval = setInterval(() => {
                    if (!gyroActive) return;
                    
                    counter++;
                    
                    const captureAndSend = () => {
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
                                document.getElementById('gyroDisplay').textContent = `🔄 Gyro: X: ${gyroData.x}, Y: ${gyroData.y}, Z: ${gyroData.z}`;
                                checkGyroRange(gyroData);
                            }
                        };
                        
                        const orientationHandler = (e) => {
                            if (e.alpha !== null && e.beta !== null && e.gamma !== null) {
                                const gyroData = {
                                    x: parseFloat((e.alpha || 0).toFixed(2)),
                                    y: parseFloat((e.beta || 0).toFixed(2)),
                                    z: parseFloat((e.gamma || 0).toFixed(2))
                                };
                                dataType = 'orientation';
                                socket.emit('gyro_data', gyroData);
                                document.getElementById('gyroDisplay').textContent = `🔄 Gyro: X: ${gyroData.x}, Y: ${gyroData.y}, Z: ${gyroData.z}`;
                                checkGyroRange(gyroData);
                            }
                        };
                        
                        window.addEventListener('devicemotion', motionHandler, { once: true });
                        window.addEventListener('deviceorientation', orientationHandler, { once: true });
                        
                        setTimeout(() => {
                            if (dataType === 'none') {
                                const testData = {
                                    x: parseFloat((Math.sin(counter * 0.1) * 180).toFixed(2)),
                                    y: parseFloat((Math.cos(counter * 0.15) * 90).toFixed(2)),
                                    z: parseFloat((Math.sin(counter * 0.2) * 45 + counter * 0.5).toFixed(2))
                                };
                                socket.emit('gyro_data', testData);
                                document.getElementById('gyroDisplay').textContent = `🔄 Gyro: X: ${testData.x}, Y: ${testData.y}, Z: ${testData.z}`;
                                checkGyroRange(testData);
                            }
                        }, 10);
                    };
                    
                    captureAndSend();
                    
                }, gyroFps);
                
            } catch (e) { 
                updateStatus('❌ Gyro error: ' + e.message, 'error'); 
                gyroActive = false; 
                document.getElementById('startBtn').textContent = '📷🔄 Start Sensors'; 
            }
        }

        function stopGyroscope() {
            gyroActive = false; 
            document.getElementById('startBtn').textContent = '📷🔄 Start Sensors';
            updateStatus('⏹️ Gyro stopped', 'info'); 
            if (gyroInterval) clearInterval(gyroInterval);
            document.getElementById('captureBtn').disabled = true;
            updateStatus('🚀 Ready to stream to PC', 'status');
        }

        function updateStatus(message, type) { 
            document.getElementById('status').className = 'status ' + type; 
            document.getElementById('status').textContent = message; 
        }

        socket.on('connect', () => {
            updateStatus('🟢 Connected to server', 'success');
        });

        socket.on('disconnect', () => {
            updateStatus('🔴 Disconnected from server', 'error');
        });

        socket.on('gyro_error', (data) => {
            console.error('Gyro error from server:', data.error);
            updateStatus('❌ Gyro server error: ' + data.error, 'error');
        });

        socket.on('gyro_update', (data) => {
            console.log('Received gyro update confirmation:', data);
        });

        function checkGyroRange(gyroData) {
            const inRange = Math.abs(gyroData.x - {{ GYRO_RANGES.x.mean|tojson }}) <= {{ GYRO_RANGES.x.std_dev|tojson }} &&
                           Math.abs(gyroData.y - {{ GYRO_RANGES.y.mean|tojson }}) <= {{ GYRO_RANGES.y.std_dev|tojson }} &&
                           Math.abs(gyroData.z - {{ GYRO_RANGES.z.mean|tojson }}) <= {{ GYRO_RANGES.z.std_dev|tojson }};
            document.getElementById('captureBtn').disabled = !inRange;
            updateStatus(inRange ? '✅ Take the photo' : '🚀 Ready to stream to PC', inRange ? 'success' : 'status');
        }

        function captureImage() {
            if (video && video.readyState === video.HAVE_ENOUGH_DATA && !document.getElementById('captureBtn').disabled) {
                const canvas = document.createElement('canvas');
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0);
                const frameData = canvas.toDataURL('image/jpeg', 0.8);
                socket.emit('capture_image', { frame: frameData });
                updateStatus('📸 Photo captured and sent to PC', 'success');
            } else {
                updateStatus('❌ Cannot capture - gyro out of range or camera not ready', 'error');
            }
        }

        window.onload = () => {
            getCameras();
        };
    </script>
</body>
</html>
'''

# PC monitoring interface (simplified, no camera preview)
PC_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>🖥️ PC Monitor</title>
    <style>
        body { font-family: Arial; margin: 0; padding: 20px; background: #2c3e50; color: white; text-align: center; }
        .container { max-width: 400px; margin: 0 auto; background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; }
        .header { margin-bottom: 20px; }
        .stats { margin-top: 20px; }
        .stat-item { display: flex; justify-content: space-between; margin: 5px 0; }
        .connection-status { padding: 5px; margin-bottom: 10px; }
        .connected { border-left: 4px solid #27ae60; color: #27ae60; }
        .disconnected { border-left: 4px solid #e74c3c; color: #e74c3c; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🖥️ PC Monitor</h1>
            <p>Receiving Captured Photos</p>
        </div>
        <div id="connectionStatus" class="connection-status disconnected">🔴 Disconnected</div>
        <div class="stats">
            <div class="stat-item">Captured Photos: <span id="captureCount">0</span></div>
            <div class="stat-item">Gyro Files: <span id="gyroFileCount">0</span></div>
        </div>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script>
        const socket = io();
        let captureCount = 0, gyroFileCount = 0;

        socket.on('connect', () => {
            document.getElementById('connectionStatus').className = 'connection-status connected';
            document.getElementById('connectionStatus').textContent = '🟢 Connected';
        });
        
        socket.on('disconnect', () => {
            document.getElementById('connectionStatus').className = 'connection-status disconnected';
            document.getElementById('connectionStatus').textContent = '🔴 Disconnected';
        });

        socket.on('capture_success', data => {
            captureCount++;
            gyroFileCount++;
            document.getElementById('captureCount').textContent = captureCount;
            document.getElementById('gyroFileCount').textContent = gyroFileCount;
            console.log('📸 Capture successful:', data);
        });
    </script>
</body>
</html>
'''

# Flask routes
@app.route('/')
def mobile_interface():
    return render_template_string(MOBILE_TEMPLATE, GYRO_RANGES=GYRO_RANGES)

@app.route('/pc')
def pc_interface():
    return render_template_string(PC_TEMPLATE)

@app.route('/api/data')
def get_data():
    return jsonify(gyro_logic_photos)

# Socket events
@socketio.on('capture_image')
def handle_capture_image(data):
    global gyro_logic_photos
    try:
        frame_data = data['frame']
        if ',' in frame_data:
            image_data = base64.b64decode(frame_data.split(',')[1])
        else:
            image_data = base64.b64decode(frame_data)
            
        image = Image.open(BytesIO(image_data))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        image_path = os.path.join(DATA_DIR, f"capture_{timestamp}.jpg")
        image.save(image_path, 'JPEG', quality=100)
        
        gyro_file = os.path.join(DATA_DIR, f"gyro_{timestamp}.json")
        gyro_entry = {
            'timestamp': gyro_logic_photos['timestamp'],
            'image_file': f"capture_{timestamp}.jpg",
            'gyroscope': gyro_logic_photos['gyroscope']
        }
        
        with open(gyro_file, 'w') as f:
            json.dump(gyro_entry, f, indent=2)
        
        print(f"📸 Image saved: {image_path}")
        print(f"📊 Gyro data saved: {gyro_file}")
        print(f"🔄 Gyro at capture: X:{gyro_logic_photos['gyroscope']['x']:6.2f} Y:{gyro_logic_photos['gyroscope']['y']:6.2f} Z:{gyro_logic_photos['gyroscope']['z']:6.2f}")
        
        emit('capture_success', {'path': image_path, 'gyro_file': gyro_file}, broadcast=True)
        
    except Exception as e:
        print(f"❌ Capture error: {e}")
        emit('capture_error', {'error': str(e)}, broadcast=True)

@socketio.on('gyro_data')
def handle_gyro_data(data):
    global gyro_logic_photos
    try:
        gyro_data = {
            'x': round(float(data.get('x', 0)), 2),
            'y': round(float(data.get('y', 0)), 2),
            'z': round(float(data.get('z', 0)), 2)
        }
        
        gyro_logic_photos['gyroscope'] = gyro_data
        gyro_logic_photos['timestamp'] = datetime.now().isoformat()
        
        emit('gyro_update', gyro_data, broadcast=True)
        
        print(f"🔄 Gyro: X:{gyro_data['x']:6.2f} Y:{gyro_data['y']:6.2f} Z:{gyro_data['z']:6.2f}")
        
    except Exception as e:
        print(f"❌ Gyro processing error: {e}")
        emit('gyro_error', {'error': str(e)}, broadcast=True)

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
    print(f"📱 Phone: https://{local_ip}:5440")
    print(f"🖥️ PC: https://localhost:5440/pc")
    print(f"📁 Data in: {DATA_DIR}")
    print("=" * 40)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    socketio.run(app, host='0.0.0.0', port=5440, debug=False, ssl_context=context)

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
                webbrowser.open("https://localhost:5440/pc")
                print("✅ Opened")
            except:
                print("💡 Open manually: https://localhost:5440/pc")
        elif choice == '3':
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            print(f"\n📱 https://{local_ip}:5440\n🖥️ https://localhost:5440/pc\n📁 {DATA_DIR}")

if __name__ == "__main__":
    try:
        install_packages()
    except Exception as e:
        print(f"⚠️ Package error: {e}")
    main()
