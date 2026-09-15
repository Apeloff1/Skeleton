"""
Jeeves Camera Knowledge - AI Tutor Camera Coding Expertise
Version: 1.0.0 | Teaching Jeeves everything about camera programming
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

router = APIRouter(prefix="/api/jeeves/camera", tags=["jeeves-camera"])

# =============================================================================
# JEEVES CAMERA KNOWLEDGE BASE
# =============================================================================

JEEVES_CAMERA_KNOWLEDGE = {
    "concepts": {
        "image_basics": {
            "topic": "Digital Image Fundamentals",
            "teaching_points": [
                "An image is a 2D array of pixels, where each pixel contains color information",
                "RGB images have 3 channels: Red, Green, Blue, each with values 0-255",
                "Grayscale images have 1 channel with intensity values 0-255",
                "Resolution = Width × Height in pixels (e.g., 1920×1080 = Full HD)",
                "Bit depth determines color precision: 8-bit = 256 levels per channel"
            ],
            "code_examples": {
                "python": '''
import cv2
import numpy as np

# Read an image
img = cv2.imread('photo.jpg')

# Get image properties
height, width, channels = img.shape
print(f"Resolution: {width}x{height}, Channels: {channels}")

# Access a pixel (row, col)
pixel = img[100, 200]  # Returns BGR values
print(f"Pixel BGR: {pixel}")

# Convert to grayscale
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# Create blank image
blank = np.zeros((480, 640, 3), dtype=np.uint8)
''',
                "javascript": '''
// Using Canvas API
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

// Load image
const img = new Image();
img.onload = () => {
    ctx.drawImage(img, 0, 0);
    
    // Get pixel data
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const data = imageData.data;  // RGBA array
    
    // Access pixel at (x, y)
    const x = 100, y = 200;
    const i = (y * canvas.width + x) * 4;
    const r = data[i], g = data[i+1], b = data[i+2], a = data[i+3];
};
img.src = 'photo.jpg';
'''
            },
            "common_mistakes": [
                "OpenCV uses BGR format, not RGB - always convert when needed",
                "Forgetting that img[row, col] is (y, x) not (x, y)",
                "Not checking if image loaded successfully (returns None)",
                "Modifying original image instead of a copy"
            ],
            "quiz_questions": [
                {"q": "What color format does OpenCV use by default?", "a": "BGR (Blue, Green, Red)"},
                {"q": "How do you access pixel at row 50, column 100?", "a": "img[50, 100] or img[50][100]"},
                {"q": "What's the shape of a 1080p color image?", "a": "(1080, 1920, 3)"}
            ]
        },
        "camera_capture": {
            "topic": "Camera Capture & Video",
            "teaching_points": [
                "VideoCapture(0) opens the default camera (webcam)",
                "VideoCapture('file.mp4') opens a video file",
                "read() returns (success, frame) - always check success!",
                "release() must be called to free the camera",
                "FPS can be controlled with waitKey() delay"
            ],
            "code_examples": {
                "python": '''
import cv2

# Open webcam
cap = cv2.VideoCapture(0)

# Check if opened
if not cap.isOpened():
    raise Exception("Cannot open camera")

# Set resolution (if supported)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

while True:
    # Read frame
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame")
        break
    
    # Display
    cv2.imshow('Camera', frame)
    
    # Exit on 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Cleanup
cap.release()
cv2.destroyAllWindows()
''',
                "javascript": '''
// WebRTC camera access
async function startCamera() {
    const video = document.getElementById('video');
    
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 1280 },
                height: { ideal: 720 },
                facingMode: 'user'
            },
            audio: false
        });
        
        video.srcObject = stream;
        await video.play();
        
        // Capture frame to canvas
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0);
        
    } catch (err) {
        console.error('Camera error:', err);
    }
}

// Stop camera
function stopCamera() {
    const video = document.getElementById('video');
    const stream = video.srcObject;
    stream.getTracks().forEach(track => track.stop());
}
'''
            },
            "common_mistakes": [
                "Not checking ret value from cap.read()",
                "Forgetting to release camera (causes 'camera busy' errors)",
                "Using waitKey(0) in video loop (causes freeze)",
                "Not handling camera permissions in web/mobile"
            ]
        },
        "color_spaces": {
            "topic": "Color Spaces",
            "teaching_points": [
                "RGB: Red, Green, Blue - standard for display",
                "BGR: Blue, Green, Red - OpenCV default format",
                "HSV: Hue, Saturation, Value - great for color detection",
                "LAB: Lightness, A (green-red), B (blue-yellow) - perceptually uniform",
                "YUV/YCbCr: Used in video compression, separates luminance"
            ],
            "code_examples": {
                "python": '''
import cv2
import numpy as np

img = cv2.imread('image.jpg')

# Convert between color spaces
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # For matplotlib

# Color detection in HSV (e.g., detect blue)
lower_blue = np.array([100, 50, 50])
upper_blue = np.array([130, 255, 255])
mask = cv2.inRange(hsv, lower_blue, upper_blue)

# Apply mask
result = cv2.bitwise_and(img, img, mask=mask)

# HSV ranges for common colors:
# Red: 0-10 or 170-180 (wraps around)
# Orange: 10-25
# Yellow: 25-35
# Green: 35-85
# Blue: 85-130
# Purple: 130-170
'''
            },
            "common_mistakes": [
                "Forgetting HSV Hue range is 0-180 in OpenCV (not 0-360)",
                "Using RGB thresholds when HSV would work better",
                "Not handling the red color wraparound in HSV"
            ]
        },
        "face_detection": {
            "topic": "Face Detection & Recognition",
            "teaching_points": [
                "Haar Cascades: Fast, works on CPU, good for real-time",
                "DNN Face Detector: More accurate, handles angles better",
                "MediaPipe Face: 468 landmarks, very fast",
                "face_recognition library: Easy face matching",
                "MTCNN: Multi-stage detection, very accurate"
            ],
            "code_examples": {
                "python": '''
import cv2
import mediapipe as mp

# Method 1: Haar Cascade (Classic)
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

img = cv2.imread('photo.jpg')
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

faces = face_cascade.detectMultiScale(
    gray, 
    scaleFactor=1.1, 
    minNeighbors=5,
    minSize=(30, 30)
)

for (x, y, w, h) in faces:
    cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)

# Method 2: MediaPipe Face Detection
mp_face = mp.solutions.face_detection
mp_draw = mp.solutions.drawing_utils

with mp_face.FaceDetection(min_detection_confidence=0.5) as face_detection:
    results = face_detection.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    
    if results.detections:
        for detection in results.detections:
            mp_draw.draw_detection(img, detection)

# Method 3: Face Recognition (matching)
import face_recognition

# Load known face
known_image = face_recognition.load_image_file("known.jpg")
known_encoding = face_recognition.face_encodings(known_image)[0]

# Compare with unknown
unknown_image = face_recognition.load_image_file("unknown.jpg")
unknown_encodings = face_recognition.face_encodings(unknown_image)

for encoding in unknown_encodings:
    match = face_recognition.compare_faces([known_encoding], encoding)
    distance = face_recognition.face_distance([known_encoding], encoding)
    print(f"Match: {match[0]}, Distance: {distance[0]:.2f}")
'''
            },
            "common_mistakes": [
                "Not converting to grayscale for Haar cascades",
                "Using too low minNeighbors (false positives)",
                "Not handling multiple faces in an image",
                "Assuming frontal face for all detectors"
            ]
        },
        "object_tracking": {
            "topic": "Object Tracking",
            "teaching_points": [
                "CSRT: Accurate but slower, good for precise tracking",
                "KCF: Fast, good balance of speed/accuracy",
                "MOSSE: Fastest, less accurate",
                "DeepSORT: Deep learning based, handles occlusions",
                "ByteTrack: State-of-the-art multi-object tracking"
            ],
            "code_examples": {
                "python": '''
import cv2

# Create tracker
tracker = cv2.TrackerCSRT_create()
# Alternatives: TrackerKCF_create(), TrackerMOSSE_create()

cap = cv2.VideoCapture('video.mp4')
ret, frame = cap.read()

# Select ROI (Region of Interest)
bbox = cv2.selectROI("Select Object", frame, False)
tracker.init(frame, bbox)

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # Update tracker
    success, bbox = tracker.update(frame)
    
    if success:
        x, y, w, h = [int(v) for v in bbox]
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.putText(frame, "Tracking", (x, y-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    else:
        cv2.putText(frame, "Lost", (50, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    
    cv2.imshow("Tracking", frame)
    if cv2.waitKey(30) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

# Multi-object tracking with DeepSORT
from deep_sort_realtime.deepsort_tracker import DeepSort

tracker = DeepSort(max_age=30)

# detections format: [[x1, y1, x2, y2, confidence, class_id], ...]
tracks = tracker.update_tracks(detections, frame=frame)

for track in tracks:
    if not track.is_confirmed():
        continue
    track_id = track.track_id
    bbox = track.to_ltrb()  # left, top, right, bottom
'''
            }
        },
        "video_processing": {
            "topic": "Video Processing with FFmpeg",
            "teaching_points": [
                "FFmpeg is the Swiss Army knife of video processing",
                "Can convert, compress, stream, and transform any video",
                "Hardware acceleration: NVENC (NVIDIA), QSV (Intel), VideoToolbox (Mac)",
                "Common codecs: H.264 (compatibility), H.265 (efficiency), VP9/AV1 (web)",
                "Use -crf for quality (lower = better, 18-28 is typical)"
            ],
            "code_examples": {
                "bash": '''
# Basic conversion
ffmpeg -i input.mp4 output.avi

# Convert to web-optimized MP4
ffmpeg -i input.mov -c:v libx264 -preset fast -crf 22 -c:a aac -b:a 128k output.mp4

# Extract frames as images
ffmpeg -i video.mp4 -vf "fps=1" frame_%04d.jpg

# Create video from images
ffmpeg -framerate 30 -i frame_%04d.jpg -c:v libx264 -pix_fmt yuv420p output.mp4

# Trim video (start at 10s, duration 30s)
ffmpeg -i input.mp4 -ss 00:00:10 -t 00:00:30 -c copy output.mp4

# Add watermark
ffmpeg -i input.mp4 -i logo.png -filter_complex "overlay=10:10" output.mp4

# Scale to 720p
ffmpeg -i input.mp4 -vf "scale=1280:720" -c:a copy output.mp4

# Hardware encoding (NVIDIA)
ffmpeg -i input.mp4 -c:v h264_nvenc -preset fast -crf 22 output.mp4

# Stream to RTMP
ffmpeg -i input.mp4 -c:v libx264 -f flv rtmp://server/live/stream_key
''',
                "python": '''
import subprocess
import ffmpeg  # pip install ffmpeg-python

# Using ffmpeg-python library
(
    ffmpeg
    .input('input.mp4')
    .filter('scale', 1280, 720)
    .output('output.mp4', crf=22, preset='fast')
    .overwrite_output()
    .run()
)

# Get video info
probe = ffmpeg.probe('video.mp4')
video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
width = int(video_info['width'])
height = int(video_info['height'])
duration = float(probe['format']['duration'])

# Extract audio
(
    ffmpeg
    .input('video.mp4')
    .output('audio.mp3', acodec='libmp3lame', audio_bitrate='192k')
    .run()
)
'''
            }
        },
        "webrtc": {
            "topic": "WebRTC Real-Time Communication",
            "teaching_points": [
                "WebRTC enables peer-to-peer video/audio in browsers",
                "Signaling server exchanges connection info (not media)",
                "STUN servers help find public IP addresses",
                "TURN servers relay media when P2P fails",
                "ICE candidates are potential connection paths"
            ],
            "code_examples": {
                "javascript": '''
// Complete WebRTC example

// 1. Get user media
const localStream = await navigator.mediaDevices.getUserMedia({
    video: true,
    audio: true
});
localVideo.srcObject = localStream;

// 2. Create peer connection
const config = {
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'turn:your-turn-server.com', username: 'user', credential: 'pass' }
    ]
};
const pc = new RTCPeerConnection(config);

// 3. Add local tracks
localStream.getTracks().forEach(track => {
    pc.addTrack(track, localStream);
});

// 4. Handle remote stream
pc.ontrack = (event) => {
    remoteVideo.srcObject = event.streams[0];
};

// 5. Handle ICE candidates
pc.onicecandidate = (event) => {
    if (event.candidate) {
        // Send to peer via signaling server
        signalingServer.send({ type: 'candidate', candidate: event.candidate });
    }
};

// 6. Create offer (caller)
const offer = await pc.createOffer();
await pc.setLocalDescription(offer);
signalingServer.send({ type: 'offer', sdp: offer });

// 7. Handle answer (callee)
signalingServer.onmessage = async (msg) => {
    if (msg.type === 'offer') {
        await pc.setRemoteDescription(msg.sdp);
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        signalingServer.send({ type: 'answer', sdp: answer });
    } else if (msg.type === 'answer') {
        await pc.setRemoteDescription(msg.sdp);
    } else if (msg.type === 'candidate') {
        await pc.addIceCandidate(msg.candidate);
    }
};
'''
            }
        }
    },
    "projects": [
        {
            "name": "Build a Photo Booth App",
            "difficulty": "beginner",
            "hours": 5,
            "skills": ["Camera capture", "Image filters", "UI"],
            "description": "Create an app that captures photos, applies filters, and saves them"
        },
        {
            "name": "Motion Detection Security Camera",
            "difficulty": "intermediate",
            "hours": 10,
            "skills": ["Background subtraction", "Object detection", "Alerts"],
            "description": "Build a security system that detects motion and sends alerts"
        },
        {
            "name": "Face Recognition Attendance System",
            "difficulty": "intermediate",
            "hours": 15,
            "skills": ["Face detection", "Face recognition", "Database"],
            "description": "Automatic attendance tracking using face recognition"
        },
        {
            "name": "Gesture-Controlled Media Player",
            "difficulty": "intermediate",
            "hours": 12,
            "skills": ["Hand tracking", "Gesture recognition", "System control"],
            "description": "Control video playback with hand gestures"
        },
        {
            "name": "Virtual Background Video Call",
            "difficulty": "advanced",
            "hours": 20,
            "skills": ["Segmentation", "WebRTC", "Real-time processing"],
            "description": "Video calling app with virtual background replacement"
        },
        {
            "name": "License Plate Recognition System",
            "difficulty": "advanced",
            "hours": 25,
            "skills": ["Object detection", "OCR", "Database"],
            "description": "Automatic license plate reading and logging"
        },
        {
            "name": "3D Body Scanner",
            "difficulty": "expert",
            "hours": 40,
            "skills": ["Depth cameras", "Point clouds", "3D reconstruction"],
            "description": "Create 3D body models from camera scans"
        },
    ],
    "teaching_style": {
        "explanation_format": "Start with WHY, then WHAT, then HOW",
        "code_format": "Always show working example first, then explain",
        "error_handling": "Anticipate common errors and explain solutions",
        "encouragement": [
            "Great question! Let me explain...",
            "You're on the right track! Here's a tip...",
            "That's a common confusion. Let me clarify...",
            "Excellent progress! Let's build on that..."
        ]
    }
}

# =============================================================================
# API ROUTES
# =============================================================================

@router.get("/knowledge")
async def get_all_knowledge():
    """Get all Jeeves camera knowledge topics"""
    topics = []
    for key, data in JEEVES_CAMERA_KNOWLEDGE["concepts"].items():
        topics.append({
            "id": key,
            "topic": data["topic"],
            "teaching_points_count": len(data["teaching_points"]),
            "has_code_examples": bool(data.get("code_examples")),
            "has_quiz": bool(data.get("quiz_questions"))
        })
    
    return {
        "topics": topics,
        "total_topics": len(topics),
        "projects": len(JEEVES_CAMERA_KNOWLEDGE["projects"]),
        "teaching_style": JEEVES_CAMERA_KNOWLEDGE["teaching_style"]
    }

@router.get("/knowledge/{topic_id}")
async def get_topic_knowledge(topic_id: str):
    """Get detailed knowledge for a specific topic"""
    if topic_id not in JEEVES_CAMERA_KNOWLEDGE["concepts"]:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    
    return {
        "topic": JEEVES_CAMERA_KNOWLEDGE["concepts"][topic_id],
        "related_projects": [
            p for p in JEEVES_CAMERA_KNOWLEDGE["projects"]
            if any(skill.lower() in topic_id.lower() for skill in p.get("skills", []))
        ]
    }

@router.get("/projects")
async def get_projects():
    """Get all camera coding projects"""
    return {
        "projects": JEEVES_CAMERA_KNOWLEDGE["projects"],
        "total_hours": sum(p["hours"] for p in JEEVES_CAMERA_KNOWLEDGE["projects"]),
        "by_difficulty": {
            "beginner": len([p for p in JEEVES_CAMERA_KNOWLEDGE["projects"] if p["difficulty"] == "beginner"]),
            "intermediate": len([p for p in JEEVES_CAMERA_KNOWLEDGE["projects"] if p["difficulty"] == "intermediate"]),
            "advanced": len([p for p in JEEVES_CAMERA_KNOWLEDGE["projects"] if p["difficulty"] == "advanced"]),
            "expert": len([p for p in JEEVES_CAMERA_KNOWLEDGE["projects"] if p["difficulty"] == "expert"]),
        }
    }

@router.post("/teach")
async def teach_topic(topic: str, student_level: str = "beginner"):
    """Get Jeeves teaching response for a camera topic"""
    style = JEEVES_CAMERA_KNOWLEDGE["teaching_style"]
    
    # Find matching topic
    matched_topic = None
    for key, data in JEEVES_CAMERA_KNOWLEDGE["concepts"].items():
        if topic.lower() in key.lower() or topic.lower() in data["topic"].lower():
            matched_topic = data
            break
    
    if not matched_topic:
        return {
            "response": f"I don't have specific knowledge about '{topic}' yet, but I can help you learn! What aspect of camera coding interests you most?",
            "suggestions": list(JEEVES_CAMERA_KNOWLEDGE["concepts"].keys())
        }
    
    # Build teaching response based on level
    teaching_points = matched_topic["teaching_points"]
    if student_level == "beginner":
        points = teaching_points[:3]
    elif student_level == "intermediate":
        points = teaching_points[:5]
    else:
        points = teaching_points
    
    # Get code example
    code_examples = matched_topic.get("code_examples", {})
    primary_code = code_examples.get("python", code_examples.get("javascript", ""))
    
    return {
        "topic": matched_topic["topic"],
        "greeting": style["encouragement"][0],
        "explanation": {
            "why": f"Understanding {matched_topic['topic']} is essential for camera programming.",
            "what": points,
            "how": primary_code[:500] + "..." if len(primary_code) > 500 else primary_code
        },
        "common_mistakes": matched_topic.get("common_mistakes", []),
        "quiz": matched_topic.get("quiz_questions", [])[:3],
        "next_steps": "Practice with the code example, then try the quiz!"
    }

@router.post("/answer")
async def answer_question(question: str):
    """Jeeves answers a camera coding question"""
    q_lower = question.lower()
    
    # Search knowledge base for relevant info
    relevant_topics = []
    for key, data in JEEVES_CAMERA_KNOWLEDGE["concepts"].items():
        score = 0
        if key in q_lower:
            score += 10
        for point in data["teaching_points"]:
            if any(word in q_lower for word in point.lower().split()[:5]):
                score += 2
        if score > 0:
            relevant_topics.append((score, key, data))
    
    if not relevant_topics:
        return {
            "answer": "That's a great question! While I don't have a specific answer prepared, let me suggest exploring these camera coding topics:",
            "suggestions": list(JEEVES_CAMERA_KNOWLEDGE["concepts"].keys())[:5],
            "tip": "Try asking about: face detection, camera capture, color spaces, object tracking, or video processing"
        }
    
    # Get best match
    relevant_topics.sort(reverse=True)
    best_match = relevant_topics[0][2]
    
    # Build answer
    return {
        "answer": f"Great question about {best_match['topic']}!",
        "key_points": best_match["teaching_points"][:3],
        "code_example": list(best_match.get("code_examples", {}).values())[0][:300] if best_match.get("code_examples") else None,
        "common_mistakes": best_match.get("common_mistakes", [])[:2],
        "follow_up": "Would you like me to explain any of these points in more detail?"
    }
