"""
Camera Coding Academy - Complete Video & Camera Programming Curriculum
Version: 1.0.0 | 500+ Hours of Camera/Video Development
Covers: OpenCV, WebRTC, MediaPipe, FFmpeg, Computer Vision, AR/VR, Streaming
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

router = APIRouter(prefix="/api/academy/camera", tags=["camera-academy"])

# =============================================================================
# DATA MODELS
# =============================================================================

class Lesson(BaseModel):
    id: str
    title: str
    description: str
    duration_minutes: int
    difficulty: str
    video_url: Optional[str] = None
    code_examples: List[str] = []
    exercises: List[Dict[str, Any]] = []
    quiz_questions: int = 0
    prerequisites: List[str] = []

class Module(BaseModel):
    id: str
    name: str
    description: str
    total_hours: float
    lessons: List[Lesson]
    projects: List[Dict[str, Any]] = []
    certification_points: int = 0

class Track(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    color: str
    total_hours: int
    modules: List[Module]
    career_paths: List[str] = []

# =============================================================================
# COMPREHENSIVE CAMERA CODING CURRICULUM
# =============================================================================

CAMERA_CURRICULUM = {
    "fundamentals": Track(
        id="camera_fundamentals",
        name="Camera Fundamentals",
        description="Core concepts of digital imaging and camera systems",
        icon="camera",
        color="#3B82F6",
        total_hours=80,
        career_paths=["Computer Vision Engineer", "Video Software Developer"],
        modules=[
            Module(
                id="digital_imaging_basics",
                name="Digital Imaging Basics",
                description="Understanding pixels, color spaces, and image formats",
                total_hours=15,
                certification_points=100,
                lessons=[
                    Lesson(
                        id="di_001",
                        title="How Digital Cameras Work",
                        description="Sensors, lenses, and the image capture pipeline",
                        duration_minutes=45,
                        difficulty="beginner",
                        code_examples=["camera_sensor_simulation.py", "pixel_array_basics.py"],
                        exercises=[
                            {"type": "quiz", "questions": 10},
                            {"type": "code", "task": "Simulate a basic camera sensor"}
                        ],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="di_002",
                        title="Color Spaces Deep Dive",
                        description="RGB, HSV, YUV, LAB - when to use each",
                        duration_minutes=60,
                        difficulty="beginner",
                        code_examples=["color_space_converter.py", "hsv_color_picker.py"],
                        exercises=[
                            {"type": "code", "task": "Build a color space converter"},
                            {"type": "project", "task": "Create a color picker tool"}
                        ],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="di_003",
                        title="Image File Formats",
                        description="JPEG, PNG, RAW, TIFF - compression and quality",
                        duration_minutes=45,
                        difficulty="beginner",
                        code_examples=["format_converter.py", "compression_analyzer.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="di_004",
                        title="Resolution and Aspect Ratios",
                        description="4K, 8K, 16:9, 4:3 - understanding display standards",
                        duration_minutes=30,
                        difficulty="beginner",
                        code_examples=["resolution_calculator.py", "aspect_ratio_cropper.py"],
                        quiz_questions=8
                    ),
                    Lesson(
                        id="di_005",
                        title="Frame Rates and Motion",
                        description="24fps, 30fps, 60fps, 120fps - temporal resolution",
                        duration_minutes=40,
                        difficulty="beginner",
                        code_examples=["frame_rate_converter.py", "slow_motion_simulator.py"],
                        quiz_questions=10
                    ),
                ],
                projects=[
                    {"name": "Build a Digital Camera Simulator", "hours": 5},
                    {"name": "Create an Image Format Analyzer", "hours": 3}
                ]
            ),
            Module(
                id="camera_hardware",
                name="Camera Hardware Programming",
                description="Interfacing with camera hardware and drivers",
                total_hours=20,
                certification_points=150,
                lessons=[
                    Lesson(
                        id="ch_001",
                        title="USB Camera Interfaces",
                        description="UVC protocol, USB video class, device enumeration",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["usb_camera_enum.py", "uvc_control.py"],
                        prerequisites=["di_001", "di_002"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="ch_002",
                        title="Camera Control Parameters",
                        description="Exposure, ISO, white balance, focus control",
                        duration_minutes=75,
                        difficulty="intermediate",
                        code_examples=["camera_controls.py", "auto_exposure.py", "manual_focus.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="ch_003",
                        title="Multi-Camera Systems",
                        description="Synchronizing multiple cameras, stereo vision setup",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["multi_cam_sync.py", "stereo_calibration.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="ch_004",
                        title="Industrial Cameras & GigE Vision",
                        description="High-speed cameras, machine vision protocols",
                        duration_minutes=60,
                        difficulty="advanced",
                        code_examples=["gige_camera.py", "high_speed_capture.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="ch_005",
                        title="Mobile Camera APIs",
                        description="iOS AVFoundation, Android Camera2 API",
                        duration_minutes=90,
                        difficulty="intermediate",
                        code_examples=["ios_camera.swift", "android_camera2.kt"],
                        quiz_questions=15
                    ),
                ],
                projects=[
                    {"name": "Build a Camera Control Panel", "hours": 8},
                    {"name": "Multi-Camera Sync System", "hours": 10}
                ]
            ),
            Module(
                id="video_fundamentals",
                name="Video Fundamentals",
                description="Video codecs, containers, and streaming basics",
                total_hours=25,
                certification_points=150,
                lessons=[
                    Lesson(
                        id="vf_001",
                        title="Video Codecs Explained",
                        description="H.264, H.265, VP9, AV1 - how video compression works",
                        duration_minutes=90,
                        difficulty="intermediate",
                        code_examples=["codec_comparison.py", "bitrate_analyzer.py"],
                        quiz_questions=20
                    ),
                    Lesson(
                        id="vf_002",
                        title="Video Containers",
                        description="MP4, MKV, WebM, MOV - container formats explained",
                        duration_minutes=45,
                        difficulty="beginner",
                        code_examples=["container_parser.py", "metadata_reader.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="vf_003",
                        title="Audio in Video",
                        description="AAC, Opus, audio sync, multichannel audio",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["audio_sync.py", "audio_extractor.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="vf_004",
                        title="Keyframes and GOP",
                        description="I-frames, P-frames, B-frames, seeking in video",
                        duration_minutes=75,
                        difficulty="intermediate",
                        code_examples=["keyframe_analyzer.py", "gop_structure.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="vf_005",
                        title="Hardware Encoding/Decoding",
                        description="NVENC, QuickSync, VideoToolbox acceleration",
                        duration_minutes=60,
                        difficulty="advanced",
                        code_examples=["hw_encode.py", "gpu_decode.py"],
                        quiz_questions=10
                    ),
                ],
                projects=[
                    {"name": "Build a Video Analyzer Tool", "hours": 6},
                    {"name": "Create a Codec Benchmark Suite", "hours": 8}
                ]
            ),
        ]
    ),
    "opencv": Track(
        id="opencv_mastery",
        name="OpenCV Mastery",
        description="Complete OpenCV for computer vision and image processing",
        icon="eye",
        color="#8B5CF6",
        total_hours=120,
        career_paths=["Computer Vision Engineer", "AI/ML Engineer", "Robotics Developer"],
        modules=[
            Module(
                id="opencv_basics",
                name="OpenCV Basics",
                description="Getting started with OpenCV in Python and C++",
                total_hours=20,
                certification_points=100,
                lessons=[
                    Lesson(
                        id="ocv_001",
                        title="OpenCV Installation & Setup",
                        description="Installing OpenCV on Windows, Mac, Linux, Raspberry Pi",
                        duration_minutes=45,
                        difficulty="beginner",
                        code_examples=["install_opencv.sh", "verify_install.py"],
                        quiz_questions=5
                    ),
                    Lesson(
                        id="ocv_002",
                        title="Reading & Displaying Images",
                        description="imread, imshow, imwrite - basic I/O operations",
                        duration_minutes=30,
                        difficulty="beginner",
                        code_examples=["image_io.py", "window_management.py"],
                        quiz_questions=8
                    ),
                    Lesson(
                        id="ocv_003",
                        title="Video Capture & Recording",
                        description="VideoCapture, VideoWriter, webcam access",
                        duration_minutes=45,
                        difficulty="beginner",
                        code_examples=["webcam_capture.py", "video_recorder.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="ocv_004",
                        title="Drawing Functions",
                        description="Lines, rectangles, circles, text overlay",
                        duration_minutes=40,
                        difficulty="beginner",
                        code_examples=["drawing_shapes.py", "text_overlay.py"],
                        quiz_questions=8
                    ),
                    Lesson(
                        id="ocv_005",
                        title="Mouse & Keyboard Events",
                        description="Interactive applications with user input",
                        duration_minutes=45,
                        difficulty="beginner",
                        code_examples=["mouse_events.py", "keyboard_control.py"],
                        quiz_questions=10
                    ),
                ],
                projects=[
                    {"name": "Interactive Drawing App", "hours": 4},
                    {"name": "Webcam Photo Booth", "hours": 3}
                ]
            ),
            Module(
                id="image_processing",
                name="Image Processing",
                description="Filters, transformations, and image enhancement",
                total_hours=30,
                certification_points=200,
                lessons=[
                    Lesson(
                        id="ip_001",
                        title="Color Space Conversions",
                        description="cvtColor, BGR to RGB, grayscale, HSV",
                        duration_minutes=45,
                        difficulty="beginner",
                        code_examples=["color_convert.py", "grayscale_effects.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="ip_002",
                        title="Image Filtering",
                        description="Blur, sharpen, Gaussian, bilateral filters",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["blur_filters.py", "sharpen_kernel.py", "bilateral.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="ip_003",
                        title="Edge Detection",
                        description="Canny, Sobel, Laplacian edge detectors",
                        duration_minutes=75,
                        difficulty="intermediate",
                        code_examples=["canny_edge.py", "sobel_gradient.py", "laplacian.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="ip_004",
                        title="Morphological Operations",
                        description="Erosion, dilation, opening, closing",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["morphology.py", "noise_removal.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="ip_005",
                        title="Histogram Operations",
                        description="Histogram calculation, equalization, CLAHE",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["histogram.py", "equalization.py", "clahe.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="ip_006",
                        title="Thresholding Techniques",
                        description="Binary, Otsu, adaptive thresholding",
                        duration_minutes=45,
                        difficulty="intermediate",
                        code_examples=["thresholding.py", "otsu.py", "adaptive_thresh.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="ip_007",
                        title="Geometric Transformations",
                        description="Resize, rotate, warp, perspective transform",
                        duration_minutes=75,
                        difficulty="intermediate",
                        code_examples=["transforms.py", "perspective_warp.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="ip_008",
                        title="Image Blending & Compositing",
                        description="Alpha blending, masks, seamless cloning",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["blending.py", "seamless_clone.py"],
                        quiz_questions=12
                    ),
                ],
                projects=[
                    {"name": "Photo Editor with Filters", "hours": 10},
                    {"name": "Document Scanner App", "hours": 8},
                    {"name": "Instagram-style Filter App", "hours": 6}
                ]
            ),
            Module(
                id="object_detection",
                name="Object Detection",
                description="Finding and tracking objects in images and video",
                total_hours=35,
                certification_points=250,
                lessons=[
                    Lesson(
                        id="od_001",
                        title="Contour Detection",
                        description="findContours, contour properties, hierarchy",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["contours.py", "contour_properties.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="od_002",
                        title="Shape Detection",
                        description="Detecting circles, lines, polygons",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["hough_circles.py", "hough_lines.py", "polygon_detect.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="od_003",
                        title="Template Matching",
                        description="Finding objects using template images",
                        duration_minutes=45,
                        difficulty="intermediate",
                        code_examples=["template_match.py", "multi_scale_match.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="od_004",
                        title="Feature Detection",
                        description="SIFT, SURF, ORB, FAST feature detectors",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["sift_features.py", "orb_features.py", "feature_match.py"],
                        quiz_questions=20
                    ),
                    Lesson(
                        id="od_005",
                        title="Haar Cascade Classifiers",
                        description="Face detection, eye detection, custom cascades",
                        duration_minutes=75,
                        difficulty="intermediate",
                        code_examples=["face_detect.py", "eye_detect.py", "train_cascade.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="od_006",
                        title="HOG Descriptors",
                        description="Histogram of Oriented Gradients for detection",
                        duration_minutes=60,
                        difficulty="advanced",
                        code_examples=["hog_descriptor.py", "pedestrian_detect.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="od_007",
                        title="Background Subtraction",
                        description="MOG2, KNN background subtractors",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["bg_subtraction.py", "motion_detection.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="od_008",
                        title="Object Tracking",
                        description="KCF, CSRT, MOSSE trackers",
                        duration_minutes=75,
                        difficulty="advanced",
                        code_examples=["object_tracker.py", "multi_tracker.py"],
                        quiz_questions=15
                    ),
                ],
                projects=[
                    {"name": "Face Detection System", "hours": 8},
                    {"name": "Motion Detection Security Cam", "hours": 10},
                    {"name": "Object Counting System", "hours": 8}
                ]
            ),
            Module(
                id="camera_calibration",
                name="Camera Calibration & 3D Vision",
                description="Calibration, stereo vision, and 3D reconstruction",
                total_hours=25,
                certification_points=200,
                lessons=[
                    Lesson(
                        id="cc_001",
                        title="Camera Calibration Theory",
                        description="Intrinsic/extrinsic parameters, distortion models",
                        duration_minutes=75,
                        difficulty="advanced",
                        code_examples=["calibration_theory.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="cc_002",
                        title="Chessboard Calibration",
                        description="Practical camera calibration with chessboard",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["chessboard_calib.py", "undistort.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="cc_003",
                        title="Stereo Camera Setup",
                        description="Stereo calibration, rectification",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["stereo_calib.py", "rectification.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="cc_004",
                        title="Depth Estimation",
                        description="Disparity maps, depth from stereo",
                        duration_minutes=75,
                        difficulty="advanced",
                        code_examples=["disparity.py", "depth_map.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="cc_005",
                        title="3D Reconstruction",
                        description="Point clouds, structure from motion",
                        duration_minutes=90,
                        difficulty="expert",
                        code_examples=["point_cloud.py", "sfm.py"],
                        quiz_questions=15
                    ),
                ],
                projects=[
                    {"name": "Stereo Vision Depth Camera", "hours": 12},
                    {"name": "3D Scanner from Photos", "hours": 15}
                ]
            ),
        ]
    ),
    "mediapipe": Track(
        id="mediapipe_ai",
        name="MediaPipe AI Vision",
        description="Google's MediaPipe for face, hand, and pose detection",
        icon="body",
        color="#10B981",
        total_hours=60,
        career_paths=["AR/VR Developer", "Gesture Recognition Engineer"],
        modules=[
            Module(
                id="mp_basics",
                name="MediaPipe Fundamentals",
                description="Getting started with MediaPipe solutions",
                total_hours=15,
                certification_points=100,
                lessons=[
                    Lesson(
                        id="mp_001",
                        title="MediaPipe Setup",
                        description="Installation, basic structure, solution types",
                        duration_minutes=30,
                        difficulty="beginner",
                        code_examples=["mp_install.py", "mp_hello.py"],
                        quiz_questions=5
                    ),
                    Lesson(
                        id="mp_002",
                        title="Face Detection",
                        description="Real-time face detection with landmarks",
                        duration_minutes=45,
                        difficulty="beginner",
                        code_examples=["face_detect.py", "face_landmarks.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="mp_003",
                        title="Face Mesh",
                        description="468 3D face landmarks for AR effects",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["face_mesh.py", "face_filters.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="mp_004",
                        title="Hand Tracking",
                        description="21-point hand landmark detection",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["hand_track.py", "gesture_basic.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="mp_005",
                        title="Pose Estimation",
                        description="33-point body pose landmarks",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["pose_detect.py", "pose_angles.py"],
                        quiz_questions=12
                    ),
                ],
                projects=[
                    {"name": "Virtual Try-On App", "hours": 8},
                    {"name": "Sign Language Detector", "hours": 10}
                ]
            ),
            Module(
                id="mp_advanced",
                name="Advanced MediaPipe",
                description="Complex applications and custom solutions",
                total_hours=25,
                certification_points=200,
                lessons=[
                    Lesson(
                        id="mpa_001",
                        title="Gesture Recognition",
                        description="Building custom gesture classifiers",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["gesture_classifier.py", "custom_gestures.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="mpa_002",
                        title="Holistic Tracking",
                        description="Combined face, hand, and pose tracking",
                        duration_minutes=75,
                        difficulty="advanced",
                        code_examples=["holistic.py", "full_body_track.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="mpa_003",
                        title="Object Detection with MediaPipe",
                        description="Using MediaPipe's object detection",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["mp_object_detect.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="mpa_004",
                        title="Selfie Segmentation",
                        description="Background removal and replacement",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["selfie_segment.py", "bg_replace.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="mpa_005",
                        title="Hair Segmentation",
                        description="Virtual hair color and style",
                        duration_minutes=45,
                        difficulty="intermediate",
                        code_examples=["hair_segment.py", "hair_color.py"],
                        quiz_questions=8
                    ),
                ],
                projects=[
                    {"name": "Fitness Pose Analyzer", "hours": 12},
                    {"name": "Virtual Background App", "hours": 8}
                ]
            ),
        ]
    ),
    "ffmpeg": Track(
        id="ffmpeg_mastery",
        name="FFmpeg Mastery",
        description="Complete video processing with FFmpeg",
        icon="film",
        color="#EF4444",
        total_hours=50,
        career_paths=["Video Engineer", "Streaming Platform Developer"],
        modules=[
            Module(
                id="ffmpeg_basics",
                name="FFmpeg Fundamentals",
                description="Core FFmpeg commands and concepts",
                total_hours=15,
                certification_points=100,
                lessons=[
                    Lesson(
                        id="ff_001",
                        title="FFmpeg Installation & Basics",
                        description="Installing FFmpeg, basic command structure",
                        duration_minutes=30,
                        difficulty="beginner",
                        code_examples=["ffmpeg_install.sh", "basic_commands.sh"],
                        quiz_questions=8
                    ),
                    Lesson(
                        id="ff_002",
                        title="Video Conversion",
                        description="Converting between formats, codecs",
                        duration_minutes=45,
                        difficulty="beginner",
                        code_examples=["convert.sh", "transcode.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="ff_003",
                        title="Video Cutting & Trimming",
                        description="Extracting clips, splitting videos",
                        duration_minutes=40,
                        difficulty="beginner",
                        code_examples=["trim_video.sh", "split_video.py"],
                        quiz_questions=8
                    ),
                    Lesson(
                        id="ff_004",
                        title="Audio Processing",
                        description="Extract, replace, mix audio tracks",
                        duration_minutes=45,
                        difficulty="beginner",
                        code_examples=["audio_extract.sh", "audio_mix.py"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="ff_005",
                        title="Video Scaling & Cropping",
                        description="Resize, crop, pad videos",
                        duration_minutes=40,
                        difficulty="beginner",
                        code_examples=["scale.sh", "crop.sh", "pad.sh"],
                        quiz_questions=8
                    ),
                ],
                projects=[
                    {"name": "Video Processing Pipeline", "hours": 6},
                    {"name": "Batch Converter Tool", "hours": 4}
                ]
            ),
            Module(
                id="ffmpeg_advanced",
                name="Advanced FFmpeg",
                description="Complex filters, streaming, and automation",
                total_hours=25,
                certification_points=200,
                lessons=[
                    Lesson(
                        id="ffa_001",
                        title="Filter Graphs",
                        description="Complex filter chains, multiple inputs/outputs",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["filter_complex.sh", "multi_input.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="ffa_002",
                        title="Video Overlays",
                        description="Picture-in-picture, watermarks, text",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["overlay.sh", "watermark.py", "text_overlay.sh"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="ffa_003",
                        title="Video Effects",
                        description="Color correction, blur, transitions",
                        duration_minutes=75,
                        difficulty="intermediate",
                        code_examples=["color_correct.sh", "transitions.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="ffa_004",
                        title="Live Streaming",
                        description="RTMP, HLS, DASH streaming",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["rtmp_stream.sh", "hls_output.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="ffa_005",
                        title="FFmpeg + Python",
                        description="Automating FFmpeg with Python",
                        duration_minutes=75,
                        difficulty="intermediate",
                        code_examples=["ffmpeg_python.py", "batch_process.py"],
                        quiz_questions=12
                    ),
                    Lesson(
                        id="ffa_006",
                        title="Hardware Acceleration",
                        description="NVIDIA, AMD, Intel hardware encoding",
                        duration_minutes=60,
                        difficulty="advanced",
                        code_examples=["nvenc.sh", "vaapi.sh", "qsv.sh"],
                        quiz_questions=10
                    ),
                ],
                projects=[
                    {"name": "YouTube Video Processor", "hours": 10},
                    {"name": "Live Streaming Server", "hours": 12}
                ]
            ),
        ]
    ),
    "webrtc": Track(
        id="webrtc_realtime",
        name="WebRTC Real-Time",
        description="Real-time video communication and streaming",
        icon="videocam",
        color="#F59E0B",
        total_hours=70,
        career_paths=["Video Conferencing Engineer", "WebRTC Specialist"],
        modules=[
            Module(
                id="webrtc_basics",
                name="WebRTC Fundamentals",
                description="Core WebRTC concepts and APIs",
                total_hours=20,
                certification_points=150,
                lessons=[
                    Lesson(
                        id="wrtc_001",
                        title="WebRTC Architecture",
                        description="Signaling, STUN, TURN, ICE",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["webrtc_overview.js"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="wrtc_002",
                        title="getUserMedia API",
                        description="Accessing camera and microphone",
                        duration_minutes=45,
                        difficulty="beginner",
                        code_examples=["get_user_media.js", "media_constraints.js"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="wrtc_003",
                        title="RTCPeerConnection",
                        description="Creating peer-to-peer connections",
                        duration_minutes=75,
                        difficulty="intermediate",
                        code_examples=["peer_connection.js", "offer_answer.js"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="wrtc_004",
                        title="Signaling Servers",
                        description="WebSocket signaling implementation",
                        duration_minutes=90,
                        difficulty="intermediate",
                        code_examples=["signaling_server.js", "socket_signaling.js"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="wrtc_005",
                        title="Data Channels",
                        description="RTCDataChannel for data transfer",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["data_channel.js", "file_transfer.js"],
                        quiz_questions=12
                    ),
                ],
                projects=[
                    {"name": "Simple Video Chat App", "hours": 15},
                    {"name": "P2P File Sharing App", "hours": 10}
                ]
            ),
            Module(
                id="webrtc_advanced",
                name="Advanced WebRTC",
                description="Scalable video conferencing and media servers",
                total_hours=30,
                certification_points=250,
                lessons=[
                    Lesson(
                        id="wrtca_001",
                        title="SFU Architecture",
                        description="Selective Forwarding Units for scaling",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["sfu_concept.js", "mediasoup_basic.js"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="wrtca_002",
                        title="MediaSoup Integration",
                        description="Building with MediaSoup SFU",
                        duration_minutes=120,
                        difficulty="advanced",
                        code_examples=["mediasoup_server.js", "mediasoup_client.js"],
                        quiz_questions=20
                    ),
                    Lesson(
                        id="wrtca_003",
                        title="Janus WebRTC Server",
                        description="Using Janus for advanced features",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["janus_setup.sh", "janus_client.js"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="wrtca_004",
                        title="Screen Sharing",
                        description="getDisplayMedia, screen recording",
                        duration_minutes=60,
                        difficulty="intermediate",
                        code_examples=["screen_share.js", "screen_record.js"],
                        quiz_questions=10
                    ),
                    Lesson(
                        id="wrtca_005",
                        title="Video Quality Optimization",
                        description="Bandwidth estimation, simulcast, SVC",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["simulcast.js", "bandwidth_adapt.js"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="wrtca_006",
                        title="Recording WebRTC Streams",
                        description="Server-side and client-side recording",
                        duration_minutes=75,
                        difficulty="advanced",
                        code_examples=["media_recorder.js", "server_record.js"],
                        quiz_questions=12
                    ),
                ],
                projects=[
                    {"name": "Multi-User Video Conference", "hours": 20},
                    {"name": "Live Streaming Platform", "hours": 18}
                ]
            ),
        ]
    ),
    "deep_learning": Track(
        id="dl_vision",
        name="Deep Learning for Video",
        description="Neural networks for video understanding",
        icon="hardware-chip",
        color="#EC4899",
        total_hours=80,
        career_paths=["Computer Vision Researcher", "ML Engineer"],
        modules=[
            Module(
                id="dl_basics",
                name="Deep Learning Vision Basics",
                description="CNNs and transfer learning for images",
                total_hours=25,
                certification_points=200,
                lessons=[
                    Lesson(
                        id="dlv_001",
                        title="CNNs for Image Classification",
                        description="VGG, ResNet, EfficientNet",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["cnn_classify.py", "transfer_learn.py"],
                        quiz_questions=20
                    ),
                    Lesson(
                        id="dlv_002",
                        title="Object Detection Networks",
                        description="YOLO, SSD, Faster R-CNN",
                        duration_minutes=120,
                        difficulty="advanced",
                        code_examples=["yolo_detect.py", "ssd.py", "faster_rcnn.py"],
                        quiz_questions=25
                    ),
                    Lesson(
                        id="dlv_003",
                        title="Semantic Segmentation",
                        description="U-Net, DeepLab, Mask R-CNN",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["unet.py", "deeplab.py", "mask_rcnn.py"],
                        quiz_questions=20
                    ),
                    Lesson(
                        id="dlv_004",
                        title="Face Recognition",
                        description="FaceNet, ArcFace, face embeddings",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["facenet.py", "face_embed.py", "face_compare.py"],
                        quiz_questions=18
                    ),
                    Lesson(
                        id="dlv_005",
                        title="Pose Estimation Networks",
                        description="OpenPose, HRNet, BlazePose",
                        duration_minutes=75,
                        difficulty="advanced",
                        code_examples=["openpose.py", "hrnet.py"],
                        quiz_questions=15
                    ),
                ],
                projects=[
                    {"name": "Custom Object Detector", "hours": 15},
                    {"name": "Face Recognition System", "hours": 12}
                ]
            ),
            Module(
                id="video_understanding",
                name="Video Understanding",
                description="Temporal models for video analysis",
                total_hours=30,
                certification_points=250,
                lessons=[
                    Lesson(
                        id="vu_001",
                        title="Action Recognition",
                        description="I3D, SlowFast, X3D architectures",
                        duration_minutes=120,
                        difficulty="expert",
                        code_examples=["i3d.py", "slowfast.py", "x3d.py"],
                        quiz_questions=25
                    ),
                    Lesson(
                        id="vu_002",
                        title="Video Object Tracking",
                        description="DeepSORT, ByteTrack, tracking-by-detection",
                        duration_minutes=90,
                        difficulty="advanced",
                        code_examples=["deepsort.py", "bytetrack.py"],
                        quiz_questions=20
                    ),
                    Lesson(
                        id="vu_003",
                        title="Video Captioning",
                        description="Describing videos with natural language",
                        duration_minutes=90,
                        difficulty="expert",
                        code_examples=["video_caption.py", "dense_caption.py"],
                        quiz_questions=18
                    ),
                    Lesson(
                        id="vu_004",
                        title="Optical Flow",
                        description="RAFT, FlowNet, motion estimation",
                        duration_minutes=75,
                        difficulty="advanced",
                        code_examples=["raft_flow.py", "flownet.py"],
                        quiz_questions=15
                    ),
                    Lesson(
                        id="vu_005",
                        title="Video Generation",
                        description="Video GANs, diffusion models",
                        duration_minutes=90,
                        difficulty="expert",
                        code_examples=["video_gan.py", "video_diffusion.py"],
                        quiz_questions=18
                    ),
                ],
                projects=[
                    {"name": "Action Recognition System", "hours": 18},
                    {"name": "Video Analytics Platform", "hours": 20}
                ]
            ),
        ]
    ),
}

# =============================================================================
# API ROUTES
# =============================================================================

@router.get("/tracks")
async def get_all_tracks():
    """Get all camera coding tracks"""
    tracks = []
    total_hours = 0
    for key, track in CAMERA_CURRICULUM.items():
        total_hours += track.total_hours
        tracks.append({
            "id": track.id,
            "name": track.name,
            "description": track.description,
            "icon": track.icon,
            "color": track.color,
            "total_hours": track.total_hours,
            "module_count": len(track.modules),
            "career_paths": track.career_paths
        })
    
    return {
        "tracks": tracks,
        "total_tracks": len(tracks),
        "total_hours": total_hours,
        "curriculum_name": "Camera Coding Academy",
        "version": "1.0.0"
    }

@router.get("/track/{track_id}")
async def get_track_details(track_id: str):
    """Get detailed track information"""
    track = CAMERA_CURRICULUM.get(track_id)
    if not track:
        raise HTTPException(status_code=404, detail=f"Track '{track_id}' not found")
    
    total_lessons = sum(len(m.lessons) for m in track.modules)
    total_projects = sum(len(m.projects) for m in track.modules)
    
    return {
        "track": track.dict(),
        "stats": {
            "total_lessons": total_lessons,
            "total_projects": total_projects,
            "total_hours": track.total_hours,
            "certification_points": sum(m.certification_points for m in track.modules)
        }
    }

@router.get("/track/{track_id}/module/{module_id}")
async def get_module_content(track_id: str, module_id: str):
    """Get module lessons and projects"""
    track = CAMERA_CURRICULUM.get(track_id)
    if not track:
        raise HTTPException(status_code=404, detail=f"Track '{track_id}' not found")
    
    module = next((m for m in track.modules if m.id == module_id), None)
    if not module:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")
    
    return {
        "module": module.dict(),
        "track_name": track.name
    }

@router.get("/lesson/{lesson_id}")
async def get_lesson_content(lesson_id: str):
    """Get detailed lesson content"""
    for track in CAMERA_CURRICULUM.values():
        for module in track.modules:
            for lesson in module.lessons:
                if lesson.id == lesson_id:
                    return {
                        "lesson": lesson.dict(),
                        "module_name": module.name,
                        "track_name": track.name
                    }
    
    raise HTTPException(status_code=404, detail=f"Lesson '{lesson_id}' not found")

@router.get("/search")
async def search_curriculum(q: str, limit: int = 20):
    """Search across all camera coding content"""
    results = []
    q_lower = q.lower()
    
    for track in CAMERA_CURRICULUM.values():
        for module in track.modules:
            for lesson in module.lessons:
                score = 0
                if q_lower in lesson.title.lower():
                    score += 10
                if q_lower in lesson.description.lower():
                    score += 5
                if any(q_lower in ex.lower() for ex in lesson.code_examples):
                    score += 3
                
                if score > 0:
                    results.append({
                        "type": "lesson",
                        "id": lesson.id,
                        "title": lesson.title,
                        "description": lesson.description,
                        "track": track.name,
                        "module": module.name,
                        "score": score
                    })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return {
        "query": q,
        "results": results[:limit],
        "total_found": len(results)
    }

@router.get("/stats")
async def get_curriculum_stats():
    """Get overall curriculum statistics"""
    total_lessons = 0
    total_projects = 0
    total_hours = 0
    total_quiz_questions = 0
    total_code_examples = 0
    
    for track in CAMERA_CURRICULUM.values():
        total_hours += track.total_hours
        for module in track.modules:
            total_projects += len(module.projects)
            for lesson in module.lessons:
                total_lessons += 1
                total_quiz_questions += lesson.quiz_questions
                total_code_examples += len(lesson.code_examples)
    
    return {
        "total_tracks": len(CAMERA_CURRICULUM),
        "total_modules": sum(len(t.modules) for t in CAMERA_CURRICULUM.values()),
        "total_lessons": total_lessons,
        "total_projects": total_projects,
        "total_hours": total_hours,
        "total_quiz_questions": total_quiz_questions,
        "total_code_examples": total_code_examples,
        "career_paths": list(set(
            path 
            for track in CAMERA_CURRICULUM.values() 
            for path in track.career_paths
        ))
    }
