#!/usr/bin/env python3
"""
Raspberry Pi QR Code Attendance Scanner (Updated for libcamera)
For SMKN 1 Tunjung Teja - PresenSiku System

This version supports both USB webcams and Raspberry Pi Camera Module
with the new libcamera stack.

Hardware Requirements:
- Raspberry Pi 3/4/5
- Camera Module or USB Webcam
- Internet connection (WiFi/Ethernet)

Software Requirements:
- Python 3.7+
- opencv-python
- pyzbar
- requests
- picamera2 (for Pi Camera Module)

Installation:
    # For USB Webcam only:
    pip3 install opencv-python pyzbar requests numpy pillow
    
    # For Raspberry Pi Camera Module (additional):
    sudo apt-get install -y python3-picamera2

Usage:
    # Auto-detect camera type
    python3 raspberry_pi_scanner_v2.py --api-url http://192.168.1.100:3000/api
    
    # Force USB webcam
    python3 raspberry_pi_scanner_v2.py --camera-type usb
    
    # Force Pi Camera
    python3 raspberry_pi_scanner_v2.py --camera-type picamera
    
    # Specify session ID
    python3 raspberry_pi_scanner_v2.py --session-id 45
"""

import sys
import time
import json
import argparse
import requests
from datetime import datetime
from pyzbar import pyzbar
from typing import Optional, Dict, Tuple, Any
import logging
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scanner.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_API_URL = "http://localhost:3000/api"
VALIDATE_ENDPOINT = "/students/qr/validate"
SCAN_COOLDOWN = 3  # seconds between scans of the same QR

# Visual Configuration (for display if available)
WINDOW_NAME = "PresenSiku - QR Scanner"


class CameraInterface:
    """Abstract camera interface"""
    
    def start(self):
        """Start the camera"""
        raise NotImplementedError
    
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a frame from the camera"""
        raise NotImplementedError
    
    def release(self):
        """Release the camera"""
        raise NotImplementedError


class USBCamera(CameraInterface):
    """USB Webcam using OpenCV"""
    
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap = None
        logger.info(f"Initializing USB camera (index: {camera_index})")
    
    def start(self):
        import cv2
        self.cv2 = cv2
        
        # Try different backends for better Raspberry Pi compatibility
        backends = [
            (cv2.CAP_V4L2, "V4L2"),
            (cv2.CAP_ANY, "ANY"),
            (cv2.CAP_GSTREAMER, "GSTREAMER"),
        ]
        
        for backend, name in backends:
            logger.info(f"Trying {name} backend...")
            self.cap = cv2.VideoCapture(self.camera_index, backend)
            
            if self.cap.isOpened():
                # Test if we can actually read a frame
                ret, test_frame = self.cap.read()
                if ret and test_frame is not None:
                    logger.info(f"✅ {name} backend works!")
                    break
                else:
                    logger.warning(f"{name} backend opened but can't read frames")
                    self.cap.release()
            else:
                logger.warning(f"{name} backend failed to open")
        
        if not self.cap.isOpened():
            raise Exception("Failed to open USB camera with any backend")
        
        # Set camera properties (some may not work on all cameras)
        try:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception as e:
            logger.warning(f"Could not set some camera properties: {e}")
        
        # Warm up camera
        logger.info("Warming up camera...")
        for _ in range(5):
            self.cap.read()
            time.sleep(0.1)
        
        logger.info("✅ USB camera initialized")
    
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.cap is None:
            return False, None
        return self.cap.read()
    
    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cv2.destroyAllWindows()


class PiCamera(CameraInterface):
    """Raspberry Pi Camera Module using picamera2"""
    
    def __init__(self):
        logger.info("Initializing Raspberry Pi Camera Module")
        self.picam2 = None
    
    def start(self):
        try:
            from picamera2 import Picamera2
            import cv2
            self.cv2 = cv2
            
            self.picam2 = Picamera2()
            
            # Configure camera
            config = self.picam2.create_preview_configuration(
                main={"size": (1280, 720), "format": "RGB888"}
            )
            self.picam2.configure(config)
            self.picam2.start()
            
            # Wait for camera to warm up
            time.sleep(2)
            
            logger.info("✅ Pi Camera initialized")
            
        except ImportError:
            raise Exception(
                "picamera2 not installed. Install with: "
                "sudo apt-get install -y python3-picamera2"
            )
    
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.picam2 is None:
            return False, None
        
        try:
            frame = self.picam2.capture_array()
            return True, frame
        except Exception as e:
            logger.error(f"Failed to capture frame: {e}")
            return False, None
    
    def release(self):
        if self.picam2 is not None:
            self.picam2.stop()
            self.picam2.close()


class HeadlessScanner:
    """Headless scanner without GUI (better for Raspberry Pi)"""
    
    def __init__(self, camera: CameraInterface, api_url: str, session_id: Optional[int] = None):
        self.camera = camera
        self.api_url = api_url.rstrip('/')
        self.session_id = session_id
        self.validate_url = f"{self.api_url}{VALIDATE_ENDPOINT}"
        self.last_scanned = {}
        self.scan_history = []
        self.running = False
        
        logger.info(f"Scanner initialized with API: {self.api_url}")
        if session_id:
            logger.info(f"Using session ID: {session_id}")
    
    def validate_qr_token(self, token: str) -> Tuple[bool, Optional[Dict], str]:
        """Send token to backend for validation"""
        try:
            payload = {"token": token}
            if self.session_id:
                payload["session_id"] = self.session_id
            
            logger.info(f"Validating token: {token[:20]}...")
            
            response = requests.post(
                self.validate_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            data = response.json()
            
            if response.status_code == 200:
                result = data.get('data', {})
                logger.info(f"✅ SUCCESS: {result.get('student_name')} - {result.get('status')}")
                
                self.scan_history.append({
                    'timestamp': datetime.now().isoformat(),
                    'token': token,
                    'student': result.get('student_name'),
                    'status': result.get('status'),
                    'success': True
                })
                
                return True, result, "Absensi berhasil dicatat"
            else:
                error_msg = data.get('message', 'Unknown error')
                logger.error(f"❌ ERROR: {error_msg}")
                
                self.scan_history.append({
                    'timestamp': datetime.now().isoformat(),
                    'token': token,
                    'error': error_msg,
                    'success': False
                })
                
                return False, None, error_msg
                
        except requests.exceptions.ConnectionError:
            error_msg = "Tidak dapat terhubung ke server"
            logger.error(f"❌ Connection Error: {self.api_url}")
            return False, None, error_msg
        except requests.exceptions.Timeout:
            error_msg = "Server timeout"
            logger.error(f"❌ Timeout Error")
            return False, None, error_msg
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logger.error(f"❌ Unexpected Error: {str(e)}")
            return False, None, error_msg
    
    def can_scan_token(self, token: str) -> bool:
        """Check if token can be scanned (cooldown check)"""
        current_time = time.time()
        last_time = self.last_scanned.get(token, 0)
        
        if current_time - last_time >= SCAN_COOLDOWN:
            self.last_scanned[token] = current_time
            return True
        return False
    
    def run(self):
        """Main scanner loop (headless mode)"""
        logger.info("=" * 60)
        logger.info("Starting PresenSiku QR Scanner (Headless Mode)")
        logger.info("=" * 60)
        
        # Start camera
        try:
            self.camera.start()
        except Exception as e:
            logger.error(f"❌ Failed to start camera: {e}")
            sys.exit(1)
        
        logger.info("Scanner running. Press Ctrl+C to stop")
        logger.info("=" * 60)
        
        self.running = True
        frame_count = 0
        failed_frames = 0
        max_consecutive_failures = 10
        
        try:
            while self.running:
                # Capture frame
                ret, frame = self.camera.read()
                
                if not ret or frame is None:
                    failed_frames += 1
                    if failed_frames >= max_consecutive_failures:
                        logger.error(f"Failed to grab {max_consecutive_failures} consecutive frames. Camera may be disconnected.")
                        break
                    logger.warning(f"Failed to grab frame ({failed_frames}/{max_consecutive_failures})")
                    time.sleep(0.5)
                    continue
                
                # Reset failure counter on successful frame
                failed_frames = 0
                frame_count += 1
                
                # Only log every 100 frames to reduce noise
                if frame_count % 100 == 0:
                    logger.debug(f"Processed {frame_count} frames")
                
                # Decode QR codes
                try:
                    qr_codes = pyzbar.decode(frame)
                except Exception as e:
                    logger.error(f"Error decoding frame: {e}")
                    continue
                
                # Process each QR code
                for qr_code in qr_codes:
                    try:
                        token = qr_code.data.decode('utf-8')
                        
                        # Check cooldown
                        if self.can_scan_token(token):
                            logger.info(f"🔍 QR Code detected: {token[:20]}...")
                            
                            # Validate token
                            success, data, message = self.validate_qr_token(token)
                            
                            if success and data:
                                print("\n" + "=" * 60)
                                print("✅ ATTENDANCE RECORDED")
                                print("=" * 60)
                                print(f"Student: {data.get('student_name')}")
                                print(f"Status: {data.get('status')}")
                                print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
                                print("=" * 60 + "\n")
                            else:
                                print("\n" + "=" * 60)
                                print("❌ SCAN FAILED")
                                print("=" * 60)
                                print(f"Error: {message}")
                                print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
                                print("=" * 60 + "\n")
                    
                    except Exception as e:
                        logger.error(f"Error processing QR code: {e}")
                
                # Small delay to prevent CPU overload
                time.sleep(0.01)
        
        except KeyboardInterrupt:
            logger.info("\n⚠️  Interrupted by user")
        
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Cleanup
            logger.info("Cleaning up...")
            self.running = False
            self.camera.release()
            logger.info("Scanner stopped")
            
            # Save scan history
            if self.scan_history:
                history_file = f"scan_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(history_file, 'w') as f:
                    json.dump(self.scan_history, f, indent=2)
                logger.info(f"Scan history saved to {history_file}")


def detect_camera_type() -> str:
    """Auto-detect available camera type"""
    
    # Try USB camera first (more common issue)
    try:
        import cv2
        logger.info("Testing USB camera...")
        
        # Try different indices
        for idx in range(3):
            logger.info(f"  Trying /dev/video{idx}...")
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    logger.info(f"🎥 Detected: USB Webcam at index {idx}")
                    return "usb"
                else:
                    logger.warning(f"  Camera at index {idx} opened but can't read frames")
            else:
                logger.debug(f"  No camera at index {idx}")
    except Exception as e:
        logger.debug(f"USB camera detection error: {e}")
    
    # Try Pi Camera
    try:
        from picamera2 import Picamera2
        logger.info("Testing Pi Camera Module...")
        # Try to initialize
        cam = Picamera2()
        cam.close()
        logger.info("🎥 Detected: Raspberry Pi Camera Module")
        return "picamera"
    except Exception as e:
        logger.debug(f"Pi Camera detection error: {e}")
    
    logger.error("❌ No camera detected!")
    logger.error("Troubleshooting steps:")
    logger.error("  1. Check camera connection: ls -l /dev/video*")
    logger.error("  2. Check USB devices: lsusb")
    logger.error("  3. For Pi Camera: vcgencmd get_camera")
    logger.error("  4. Try manual selection: --camera-type usb or --camera-type picamera")
    return None


def check_dependencies():
    """Check if required dependencies are installed"""
    missing = []
    
    try:
        import cv2
        logger.info(f"✅ opencv-python: {cv2.__version__}")
    except ImportError:
        missing.append("opencv-python")
    
    try:
        from pyzbar import pyzbar
        logger.info("✅ pyzbar: installed")
    except ImportError:
        missing.append("pyzbar")
    
    try:
        import requests
        logger.info(f"✅ requests: {requests.__version__}")
    except ImportError:
        missing.append("requests")
    
    try:
        import numpy
        logger.info(f"✅ numpy: {numpy.__version__}")
    except ImportError:
        missing.append("numpy")
    
    # Check picamera2 (optional)
    try:
        from picamera2 import Picamera2
        logger.info("✅ picamera2: installed (Pi Camera support)")
    except ImportError:
        logger.warning("⚠️  picamera2: not installed (Pi Camera won't work)")
        logger.info("   Install with: sudo apt-get install -y python3-picamera2")
    
    if missing:
        logger.error("❌ Missing required packages:")
        for pkg in missing:
            logger.error(f"   - {pkg}")
        print("\nInstall them with:")
        print(f"   pip3 install {' '.join(missing)}")
        sys.exit(1)
    
    logger.info("\n✅ All required dependencies are installed")


def main():
    """Main entry point"""
    
    # Parse arguments
    parser = argparse.ArgumentParser(
        description='PresenSiku QR Code Attendance Scanner for Raspberry Pi'
    )
    parser.add_argument(
        '--api-url',
        type=str,
        default=DEFAULT_API_URL,
        help='Backend API URL (default: http://localhost:3000/api)'
    )
    parser.add_argument(
        '--session-id',
        type=int,
        help='Specific attendance session ID (optional)'
    )
    parser.add_argument(
        '--camera-type',
        type=str,
        choices=['auto', 'usb', 'picamera'],
        default='auto',
        help='Camera type: auto (detect), usb (webcam), or picamera (Pi Camera Module)'
    )
    parser.add_argument(
        '--camera-index',
        type=int,
        default=0,
        help='USB camera index (default: 0)'
    )
    parser.add_argument(
        '--check-deps',
        action='store_true',
        help='Check if dependencies are installed'
    )
    parser.add_argument(
        '--test-camera',
        action='store_true',
        help='Test camera without connecting to API'
    )
    
    args = parser.parse_args()
    
    # Check dependencies
    if args.check_deps:
        check_dependencies()
        sys.exit(0)
    
    # Detect camera type
    if args.camera_type == 'auto':
        camera_type = detect_camera_type()
        if camera_type is None:
            logger.error("Please specify camera type manually with --camera-type")
            sys.exit(1)
    else:
        camera_type = args.camera_type
    
    # Initialize camera
    try:
        if camera_type == 'picamera':
            camera = PiCamera()
        else:
            camera = USBCamera(args.camera_index)
    except Exception as e:
        logger.error(f"Failed to initialize camera: {e}")
        sys.exit(1)
    
    # Test camera mode
    if args.test_camera:
        logger.info("Testing camera...")
        try:
            camera.start()
            logger.info("Camera started successfully")
            
            for i in range(10):
                ret, frame = camera.read()
                if ret:
                    logger.info(f"✅ Frame {i+1}/10 captured: {frame.shape}")
                else:
                    logger.error(f"❌ Failed to capture frame {i+1}/10")
                time.sleep(0.5)
            
            camera.release()
            logger.info("✅ Camera test completed")
        except Exception as e:
            logger.error(f"❌ Camera test failed: {e}")
            import traceback
            traceback.print_exc()
        sys.exit(0)
    
    # Create and run scanner
    scanner = HeadlessScanner(camera, args.api_url, args.session_id)
    scanner.run()


if __name__ == "__main__":
    main()
