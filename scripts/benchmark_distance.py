import cv2
import time
import sys
import os
import math

# Add parent directory to path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.camera import Camera
from src.gesture_detector import GestureDetector
from src.gesture_classifier import GestureClassifier

def main():
    print("========================================")
    print(" SmartGesture Physical Distance Benchmark")
    print("========================================")
    print("This tool estimates how far you are from the camera")
    print("and evaluates gesture recognition stability.")
    print("Press 'q' to quit.")
    
    camera = Camera(index=0, width=640, height=480, fps=30)
    detector = GestureDetector()
    classifier = GestureClassifier()
    
    if not camera.start():
        print("Failed to start camera.")
        return
        
    FOCAL_LENGTH_PX = 600  # Approximated typical webcam focal length
    REAL_WRIST_MCP_CM = 10.0 # Typical adult hand size from wrist to middle finger MCP
    
    # We will log data every 1 second
    last_log_time = time.time()
    
    try:
        while True:
            frame, _ = camera.read()
            if frame is None:
                time.sleep(0.01)
                continue
                
            # Synchronous detection for benchmark to ensure 1:1 frame-result mapping
            results = detector.hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            hands_data = detector._parse_results(results, frame.shape)
            
            distance_cm = -1
            confidence = 0
            gesture = "None"
            
            if hands_data and results and results.hand_landmarks:
                h1 = hands_data[0]
                lms = h1['landmarks']
                
                # Draw
                detector.draw_landmarks(frame, results.hand_landmarks[0])
                
                # Estimate distance
                # Wrist is 0, Middle Finger MCP is 9
                dx = lms[0].pixel_x - lms[9].pixel_x
                dy = lms[0].pixel_y - lms[9].pixel_y
                pixel_size = math.sqrt(dx**2 + dy**2)
                
                if pixel_size > 0:
                    distance_cm = (REAL_WRIST_MCP_CM * FOCAL_LENGTH_PX) / pixel_size
                    
                stable, raw, confidence = classifier.classify(hands_data)
                gesture = raw
                
                cv2.putText(frame, f"Dist: {distance_cm:.1f} cm", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.putText(frame, f"Gesture: {gesture} ({confidence}%)", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                if time.time() - last_log_time >= 0.5:
                    print(f"Distance: {distance_cm:5.1f} cm | Gesture: {gesture:15} | Confidence: {confidence:3}% | PixelSize: {pixel_size:.1f}px")
                    last_log_time = time.time()
            else:
                cv2.putText(frame, "No Hand Detected", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                if time.time() - last_log_time >= 0.5:
                    print(f"Distance:  ---- cm | Gesture: None            | Confidence:   0% | PixelSize: ----px")
                    last_log_time = time.time()
                
            cv2.imshow("Distance Benchmark", frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
