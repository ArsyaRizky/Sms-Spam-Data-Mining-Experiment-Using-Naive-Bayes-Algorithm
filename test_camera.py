#!/usr/bin/env python3
"""
Quick camera diagnostic script for Raspberry Pi
Tests all possible camera configurations
"""

import sys
import time

print("=" * 60)
print("Raspberry Pi Camera Diagnostic Tool")
print("=" * 60)
print()

# Test 1: Check system camera devices
print("1. Checking for camera devices...")
import os
video_devices = []
for i in range(10):
    device = f"/dev/video{i}"
    if os.path.exists(device):
        video_devices.append(device)
        print(f"   ✅ Found: {device}")

if not video_devices:
    print("   ❌ No /dev/video* devices found")
    print("   Run: ls -l /dev/video* to verify")
else:
    print(f"   Total devices: {len(video_devices)}")
print()

# Test 2: Check OpenCV
print("2. Testing OpenCV...")
try:
    import cv2
    print(f"   ✅ OpenCV version: {cv2.__version__}")
    
    # List available backends
    print("   Available backends:")
    backends = [
        ("CAP_V4L2", cv2.CAP_V4L2),
        ("CAP_ANY", cv2.CAP_ANY),
    ]
    
    for name, backend in backends:
        try:
            cap = cv2.VideoCapture(0, backend)
            if cap.isOpened():
                print(f"      ✅ {name}")
                cap.release()
            else:
                print(f"      ❌ {name}")
        except:
            print(f"      ❌ {name} (exception)")
    
except ImportError:
    print("   ❌ OpenCV not installed")
    print("   Install: pip3 install opencv-python")
    sys.exit(1)
print()

# Test 3: Try each video device
print("3. Testing each camera device...")
for i in range(len(video_devices)):
    print(f"\n   Testing /dev/video{i}:")
    
    # Try V4L2 backend
    print(f"      Trying V4L2 backend...")
    try:
        cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
        if cap.isOpened():
            print(f"         ✅ Opened successfully")
            
            # Try to read a frame
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"         ✅ Can read frames! Shape: {frame.shape}")
                print(f"         ✅ THIS CAMERA WORKS! Use --camera-index {i}")
                
                # Save test image
                test_file = f"test_camera_{i}.jpg"
                cv2.imwrite(test_file, frame)
                print(f"         ✅ Test image saved: {test_file}")
            else:
                print(f"         ❌ Cannot read frames")
            
            cap.release()
        else:
            print(f"         ❌ Failed to open")
    except Exception as e:
        print(f"         ❌ Error: {e}")
    
    # Try ANY backend
    print(f"      Trying ANY backend...")
    try:
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            print(f"         ✅ Opened successfully")
            
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"         ✅ Can read frames! Shape: {frame.shape}")
            else:
                print(f"         ❌ Cannot read frames")
            
            cap.release()
        else:
            print(f"         ❌ Failed to open")
    except Exception as e:
        print(f"         ❌ Error: {e}")

print()

# Test 4: Check Pi Camera
print("4. Testing Raspberry Pi Camera Module...")
try:
    from picamera2 import Picamera2
    print("   ✅ picamera2 installed")
    
    try:
        picam2 = Picamera2()
        print("   ✅ Pi Camera detected")
        
        config = picam2.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        picam2.configure(config)
        picam2.start()
        time.sleep(2)
        
        frame = picam2.capture_array()
        print(f"   ✅ Can capture frames! Shape: {frame.shape}")
        
        # Save test image
        import numpy as np
        from PIL import Image
        img = Image.fromarray(frame)
        img.save("test_picamera.jpg")
        print("   ✅ Test image saved: test_picamera.jpg")
        
        picam2.stop()
        picam2.close()
        print("   ✅ Pi Camera works! Use --camera-type picamera")
        
    except Exception as e:
        print(f"   ❌ Pi Camera error: {e}")
        
except ImportError:
    print("   ⚠️  picamera2 not installed")
    print("   Install: sudo apt-get install -y python3-picamera2")
print()

# Test 5: Check v4l2 info
print("5. Additional camera information...")
try:
    import subprocess
    result = subprocess.run(['v4l2-ctl', '--list-devices'], 
                          capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print("   v4l2-ctl output:")
        for line in result.stdout.split('\n'):
            if line.strip():
                print(f"      {line}")
    else:
        print("   ⚠️  v4l2-ctl not available")
        print("   Install: sudo apt-get install v4l-utils")
except Exception as e:
    print(f"   ⚠️  Could not run v4l2-ctl: {e}")
print()

# Summary
print("=" * 60)
print("DIAGNOSTIC SUMMARY")
print("=" * 60)
print()
print("If you see '✅ THIS CAMERA WORKS!' above, use that camera index.")
print()
print("To run the scanner with a specific camera:")
print("  python3 raspberry_pi_scanner_v2.py --camera-type usb --camera-index X --api-url http://localhost:3000/api")
print()
print("If Pi Camera works:")
print("  python3 raspberry_pi_scanner_v2.py --camera-type picamera --api-url http://localhost:3000/api")
print()
print("If nothing works, try:")
print("  1. Reconnect the camera")
print("  2. Reboot the Raspberry Pi")
print("  3. Check dmesg | tail for errors")
print("  4. Check camera permissions: groups | grep video")
print("=" * 60)
