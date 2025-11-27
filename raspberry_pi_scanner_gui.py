#!/usr/bin/env python3
"""
Raspberry Pi QR Code Attendance Scanner - WITH GUI Display
For SMKN 1 Tunjung Teja - PresenSiku System

This version shows a live camera preview window with visual feedback.
"""

import sys
import time
import json
import argparse
import requests
from datetime import datetime
from pyzbar import pyzbar
from typing import Optional, Dict, Tuple
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

# Visual Configuration
WINDOW_NAME = "PresenSiku - QR Scanner"
FONT = 0  # cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.7
FONT_THICKNESS = 2
SUCCESS_COLOR = (0, 255, 0)
ERROR_COLOR = (0, 0, 255)
PENDING_COLOR = (255, 165, 0)
TEXT_COLOR = (255, 255, 255)


class CameraInterface:
    """Abstract camera interface"""
    
    def start(self):
        raise NotImplementedError
    
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        raise NotImplementedError
    
    def release(self):
        raise NotImplementedError


class PiCamera(CameraInterface):
    """Raspberry Pi Camera Module using picamera2"""
    
    def __init__(self):
        logger.info("Initializing Raspberry Pi Camera Module")
        self.picam2 = None
        self.cv2 = None
    
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
        if self.cv2 is not None:
            self.cv2.destroyAllWindows()


class GUIScanner:
    """Scanner with GUI display"""
    
    def __init__(self, camera: CameraInterface, api_url: str, session_id: Optional[int] = None):
        self.camera = camera
        self.api_url = api_url.rstrip('/')
        self.session_id = session_id
        self.validate_url = f"{self.api_url}{VALIDATE_ENDPOINT}"
        self.last_scanned = {}
        self.scan_history = []
        self.running = False
        self.cv2 = None
        
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
    
    def draw_qr_overlay(self, frame, qr_code, success: Optional[bool] = None, message: str = ""):
        """Draw overlay on detected QR code"""
        points = qr_code.polygon
        
        if len(points) == 4:
            pts = [(point.x, point.y) for point in points]
            
            # Determine color
            if success is True:
                color = SUCCESS_COLOR
            elif success is False:
                color = ERROR_COLOR
            else:
                color = PENDING_COLOR
            
            # Draw polygon around QR code
            for i in range(4):
                self.cv2.line(frame, pts[i], pts[(i + 1) % 4], color, 3)
            
            # Draw message
            if message:
                x = min(pt[0] for pt in pts)
                y = min(pt[1] for pt in pts) - 40
                
                (text_width, text_height), _ = self.cv2.getTextSize(
                    message, FONT, FONT_SCALE, FONT_THICKNESS
                )
                
                # Background rectangle
                self.cv2.rectangle(
                    frame,
                    (x - 10, y - text_height - 10),
                    (x + text_width + 10, y + 10),
                    color,
                    -1
                )
                
                # Text
                self.cv2.putText(
                    frame, message, (x, y),
                    FONT, FONT_SCALE, (255, 255, 255), FONT_THICKNESS
                )
    
    def draw_info_panel(self, frame, width: int, height: int):
        """Draw information panel"""
        # Top panel background
        overlay = frame.copy()
        self.cv2.rectangle(overlay, (0, 0), (width, 80), (0, 0, 0), -1)
        self.cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # Title
        title = "PRESENSIKU - SCANNER ABSENSI"
        self.cv2.putText(frame, title, (20, 30), FONT, 0.8, TEXT_COLOR, 2)
        
        # Timestamp
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.cv2.putText(frame, timestamp, (20, 60), FONT, 0.6, TEXT_COLOR, 1)
        
        # Session info
        if self.session_id:
            session_text = f"Session ID: {self.session_id}"
            self.cv2.putText(frame, session_text, (width - 200, 30), FONT, 0.6, TEXT_COLOR, 1)
        
        # Instructions at bottom
        instructions = "Arahkan QR Code ke kamera | Tekan 'q' untuk keluar"
        (text_width, _), _ = self.cv2.getTextSize(instructions, FONT, 0.6, 1)
        self.cv2.putText(
            frame, instructions,
            ((width - text_width) // 2, height - 20),
            FONT, 0.6, (255, 255, 0), 1
        )
    
    def run(self):
        """Main scanner loop with GUI"""
        import cv2
        self.cv2 = cv2
        
        logger.info("=" * 60)
        logger.info("Starting PresenSiku QR Scanner (GUI Mode)")
        logger.info("=" * 60)
        
        # Start camera
        try:
            self.camera.start()
        except Exception as e:
            logger.error(f"❌ Failed to start camera: {e}")
            sys.exit(1)
        
        logger.info("Scanner running with GUI display")
        logger.info("Press 'q' to quit, 's' to show scan history")
        logger.info("=" * 60)
        
        self.running = True
        frame_count = 0
        
        try:
            while self.running:
                ret, frame = self.camera.read()
                
                if not ret or frame is None:
                    logger.error("Failed to grab frame")
                    time.sleep(0.1)
                    continue
                
                frame_count += 1
                height, width = frame.shape[:2]
                
                # Decode QR codes
                try:
                    qr_codes = pyzbar.decode(frame)
                except Exception as e:
                    logger.error(f"Error decoding frame: {e}")
                    qr_codes = []
                
                # Process each QR code
                for qr_code in qr_codes:
                    try:
                        token = qr_code.data.decode('utf-8')
                        
                        if self.can_scan_token(token):
                            # Show pending state
                            self.draw_qr_overlay(frame, qr_code, None, "Scanning...")
                            self.draw_info_panel(frame, width, height)
                            cv2.imshow(WINDOW_NAME, frame)
                            cv2.waitKey(100)
                            
                            # Validate token
                            success, data, message = self.validate_qr_token(token)
                            
                            # Show result
                            ret, frame = self.camera.read()
                            if ret:
                                if success and data:
                                    display_msg = f"{data.get('student_name')} - {data.get('status')}"
                                    self.draw_qr_overlay(frame, qr_code, True, display_msg)
                                else:
                                    self.draw_qr_overlay(frame, qr_code, False, message)
                                
                                self.draw_info_panel(frame, width, height)
                                cv2.imshow(WINDOW_NAME, frame)
                                cv2.waitKey(2000)  # Show result for 2 seconds
                        else:
                            # Still in cooldown
                            self.draw_qr_overlay(frame, qr_code, None, "Cooldown...")
                    
                    except Exception as e:
                        logger.error(f"Error processing QR code: {e}")
                
                # Draw info panel
                self.draw_info_panel(frame, width, height)
                
                # Display frame
                cv2.imshow(WINDOW_NAME, frame)
                
                # Handle key press
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q'):
                    logger.info("Quit signal received")
                    break
                elif key == ord('s'):
                    logger.info("=" * 60)
                    logger.info("SCAN HISTORY (Last 10)")
                    logger.info("=" * 60)
                    for entry in self.scan_history[-10:]:
                        logger.info(json.dumps(entry, indent=2))
                    logger.info("=" * 60)
        
        except KeyboardInterrupt:
            logger.info("\n⚠️  Interrupted by user")
        
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            logger.info("Cleaning up...")
            self.running = False
            self.camera.release()
            logger.info("Scanner stopped")
            
            if self.scan_history:
                history_file = f"scan_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(history_file, 'w') as f:
                    json.dump(self.scan_history, f, indent=2)
                logger.info(f"Scan history saved to {history_file}")


def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(
        description='PresenSiku QR Code Attendance Scanner with GUI'
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
    
    args = parser.parse_args()
    
    # Initialize Pi Camera
    camera = PiCamera()
    
    # Create and run scanner
    scanner = GUIScanner(camera, args.api_url, args.session_id)
    scanner.run()


if __name__ == "__main__":
    main()
