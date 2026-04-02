"""
LADA v7.0 - Face Recognition Security Module
Unlock app with your face - Supports both OpenCV popup and PyQt5 embedded modes

SECURITY: Uses numpy npz format instead of pickle to prevent code execution vulnerabilities.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Tuple, Callable
import time

logger = logging.getLogger(__name__)

# OpenCV imports
try:
    import cv2
    import numpy as np
    CV_AVAILABLE = True
except ImportError:
    CV_AVAILABLE = False
    logger.warning("OpenCV not available - pip install opencv-python")


class FaceRecognition:
    """
    Face recognition for LADA security
    
    First run: Captures and saves your face
    Subsequent runs: Verifies it's you before unlocking
    """
    
    def __init__(self, data_dir: str = 'config'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.face_data_file = self.data_dir / 'face_data.npz'
        self.face_cascade_file = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml' if CV_AVAILABLE else None
        
        self.face_cascade = None
        self.known_face = None
        self.is_enrolled = False
        
        if CV_AVAILABLE:
            self._initialize()
    
    def _initialize(self):
        """Initialize face detector and load known face"""
        try:
            self.face_cascade = cv2.CascadeClassifier(self.face_cascade_file)
            
            # Load saved face data from numpy npz format
            if self.face_data_file.exists():
                with np.load(self.face_data_file, allow_pickle=False) as data:
                    # Load individual fields (not a dict wrapped in 0-d array)
                    self.known_face = {
                        'samples': data['samples'],
                        'average': data['average'],
                        'enrolled_at': str(data['enrolled_at']) if 'enrolled_at' in data else ''
                    }
                self.is_enrolled = True
                logger.info("✅ Face data loaded - recognition ready")
            else:
                logger.info("👤 No face enrolled - will capture on first unlock")
                
        except Exception as e:
            logger.error(f"Face recognition init failed: {e}")
    
    def capture_face(self, timeout: int = 30) -> Tuple[bool, str]:
        """
        Capture and save user's face for enrollment
        
        Args:
            timeout: Max seconds to wait for face
            
        Returns:
            (success, message)
        """
        if not CV_AVAILABLE:
            return False, "OpenCV not installed"
        
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return False, "Cannot access camera"
        
        start_time = time.time()
        captured_faces = []
        
        try:
            cv2.namedWindow('LADA - Face Enrollment', cv2.WINDOW_NORMAL)
            cv2.resizeWindow('LADA - Face Enrollment', 640, 480)
            
            while time.time() - start_time < timeout:
                ret, frame = cap.read()
                if not ret:
                    continue
                
                # Convert to grayscale for detection
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Detect faces
                faces = self.face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100)
                )
                
                # Draw rectangles and instructions
                display = frame.copy()
                cv2.putText(display, "Look at the camera - Capturing your face...", 
                           (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(display, f"Captured: {len(captured_faces)}/5 - Press Q to cancel",
                           (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                
                for (x, y, w, h) in faces:
                    cv2.rectangle(display, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    
                    # Capture face region
                    if len(faces) == 1 and len(captured_faces) < 5:
                        face_roi = gray[y:y+h, x:x+w]
                        face_roi = cv2.resize(face_roi, (100, 100))
                        captured_faces.append(face_roi)
                        time.sleep(0.5)  # Wait between captures
                
                cv2.imshow('LADA - Face Enrollment', display)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    cap.release()
                    cv2.destroyAllWindows()
                    return False, "Enrollment cancelled"
                
                # Got enough samples
                if len(captured_faces) >= 5:
                    break
            
            cap.release()
            cv2.destroyAllWindows()
            
            if len(captured_faces) < 3:
                return False, "Could not capture enough face samples"
            
            # Save face data (average of captured faces)
            self.known_face = {
                'samples': captured_faces,
                'average': np.mean(captured_faces, axis=0),
                'enrolled_at': time.time()
            }
            
            # Save using numpy npz format with explicit fields (secure, no pickle)
            np.savez(
                self.face_data_file,
                samples=self.known_face['samples'],
                average=self.known_face['average'],
                enrolled_at=np.array([self.known_face['enrolled_at']])
            )
            
            self.is_enrolled = True
            logger.info("✅ Face enrolled successfully")
            return True, "Face enrolled! LADA will now recognize you."
            
        except Exception as e:
            cap.release()
            cv2.destroyAllWindows()
            logger.error(f"Face capture failed: {e}")
            return False, f"Error: {e}"
    
    def verify_face(self, timeout: int = 15) -> Tuple[bool, str]:
        """
        Verify user's face matches enrolled face
        
        Args:
            timeout: Max seconds to wait for match
            
        Returns:
            (success, message)
        """
        if not CV_AVAILABLE:
            return True, "OpenCV not installed - skipping verification"
        
        if not self.is_enrolled:
            # First time - enroll instead
            return self.capture_face()
        
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return False, "Cannot access camera"
        
        start_time = time.time()
        match_count = 0
        required_matches = 3
        
        try:
            cv2.namedWindow('LADA - Face Verification', cv2.WINDOW_NORMAL)
            cv2.resizeWindow('LADA - Face Verification', 640, 480)
            
            while time.time() - start_time < timeout:
                ret, frame = cap.read()
                if not ret:
                    continue
                
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100)
                )
                
                display = frame.copy()
                cv2.putText(display, "Verifying face... Look at the camera",
                           (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                for (x, y, w, h) in faces:
                    face_roi = gray[y:y+h, x:x+w]
                    face_roi = cv2.resize(face_roi, (100, 100))
                    
                    # Compare with known face
                    similarity = self._compare_faces(face_roi)
                    
                    color = (0, 255, 0) if similarity > 0.7 else (0, 0, 255)
                    cv2.rectangle(display, (x, y), (x+w, y+h), color, 2)
                    cv2.putText(display, f"{similarity*100:.0f}%",
                               (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    
                    if similarity > 0.7:
                        match_count += 1
                        if match_count >= required_matches:
                            cap.release()
                            cv2.destroyAllWindows()
                            logger.info("✅ Face verified - welcome!")
                            return True, "Welcome back!"
                
                cv2.imshow('LADA - Face Verification', display)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
            
            cap.release()
            cv2.destroyAllWindows()
            return False, "Face not recognized"
            
        except Exception as e:
            cap.release()
            cv2.destroyAllWindows()
            logger.error(f"Face verification failed: {e}")
            return False, f"Error: {e}"
    
    def _compare_faces(self, face: np.ndarray) -> float:
        """Compare a face with known face, return similarity 0-1"""
        if self.known_face is None:
            return 0.0
        
        try:
            # Compare with average known face
            known = self.known_face['average'].astype(np.float32)
            face = face.astype(np.float32)
            
            # Normalized correlation
            correlation = cv2.matchTemplate(face, known, cv2.TM_CCOEFF_NORMED)
            similarity = float(correlation[0][0])
            
            # Also compare with individual samples
            max_sample_sim = 0
            for sample in self.known_face['samples']:
                sample = sample.astype(np.float32)
                corr = cv2.matchTemplate(face, sample, cv2.TM_CCOEFF_NORMED)
                max_sample_sim = max(max_sample_sim, float(corr[0][0]))
            
            # Take the best match
            return max(similarity, max_sample_sim)
            
        except Exception as e:
            logger.error(f"Face comparison error: {e}")
            return 0.0
    
    def reset_enrollment(self) -> bool:
        """Delete enrolled face data"""
        try:
            if self.face_data_file.exists():
                self.face_data_file.unlink()
            self.known_face = None
            self.is_enrolled = False
            logger.info("Face data deleted")
            return True
        except Exception as e:
            logger.error(f"Could not reset: {e}")
            return False

    # ============ In-App Mode (No Popups) ============
    
    def start_camera(self) -> bool:
        """Start camera capture for in-app mode"""
        if not CV_AVAILABLE:
            return False
        try:
            self._cap = cv2.VideoCapture(0)
            return self._cap.isOpened()
        except:
            return False
    
    def stop_camera(self):
        """Stop camera capture"""
        if hasattr(self, '_cap') and self._cap:
            self._cap.release()
            self._cap = None
    
    def get_frame_with_detection(self) -> Tuple[Optional[np.ndarray], Optional[dict]]:
        """
        Get camera frame with face detection overlay (for PyQt5 embedding)
        
        Returns:
            (frame_rgb, detection_info) where detection_info has:
            - 'has_face': bool
            - 'similarity': float (0-1) if enrolled
            - 'faces': list of (x, y, w, h) tuples
        """
        if not hasattr(self, '_cap') or not self._cap:
            return None, None
        
        ret, frame = self._cap.read()
        if not ret:
            return None, None
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100)
        )
        
        detection_info = {
            'has_face': len(faces) > 0,
            'similarity': 0.0,
            'faces': []
        }
        
        for (x, y, w, h) in faces:
            detection_info['faces'].append((x, y, w, h))
            
            # Calculate similarity if enrolled
            if self.is_enrolled:
                face_roi = gray[y:y+h, x:x+w]
                face_roi = cv2.resize(face_roi, (100, 100))
                similarity = self._compare_faces(face_roi)
                detection_info['similarity'] = max(detection_info['similarity'], similarity)
                
                # Draw rectangle with color based on match
                color = (0, 255, 0) if similarity > 0.7 else (0, 165, 255)
                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                cv2.putText(frame, f"{similarity*100:.0f}%",
                           (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            else:
                # Enrollment mode - green rectangle
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        
        # Convert BGR to RGB for PyQt5
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return frame_rgb, detection_info
    
    def capture_face_sample(self) -> Optional[np.ndarray]:
        """Capture single face sample for enrollment (in-app mode)"""
        if not hasattr(self, '_cap') or not self._cap:
            return None
        
        ret, frame = self._cap.read()
        if not ret:
            return None
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100)
        )
        
        if len(faces) == 1:
            x, y, w, h = faces[0]
            face_roi = gray[y:y+h, x:x+w]
            face_roi = cv2.resize(face_roi, (100, 100))
            return face_roi
        return None
    
    def enroll_from_samples(self, samples: list) -> Tuple[bool, str]:
        """Save enrollment from collected samples"""
        if len(samples) < 3:
            return False, "Need at least 3 face samples"
        
        try:
            self.known_face = {
                'samples': samples,
                'average': np.mean(samples, axis=0),
                'enrolled_at': time.time()
            }
            
            # Save using numpy npz format with explicit fields (secure, no pickle)
            np.savez(
                self.face_data_file,
                samples=self.known_face['samples'],
                average=self.known_face['average'],
                enrolled_at=np.array([self.known_face['enrolled_at']])
            )
            
            self.is_enrolled = True
            logger.info("✅ Face enrolled successfully (in-app mode)")
            return True, "Face enrolled! LADA will now recognize you."
        except Exception as e:
            return False, f"Error: {e}"


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    face = FaceRecognition()
    
    print("LADA Face Recognition Test")
    print("=" * 40)
    
    if not face.is_enrolled:
        print("No face enrolled. Starting enrollment...")
        success, msg = face.capture_face()
        print(f"Enrollment: {msg}")
    else:
        print("Face already enrolled. Verifying...")
        success, msg = face.verify_face()
        print(f"Verification: {msg}")
