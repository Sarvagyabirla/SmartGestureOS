# SmartGestureOS - Gestures and Actions (Strict 1-to-1 Mapping)

This document outlines the strictly unique gesture mappings. Every single task in a given mode is tied to its own distinct gesture, preventing overlap or accidental triggers.

## Core Gestures (General Mode)

### Mouse & Navigation (Immediate & Continuous)
| Gesture | Action | Description |
| :--- | :--- | :--- |
| ☝️ **Pointing (Index Finger)** | Move Mouse | Moves the cursor around the screen smoothly. |
| 👌 **Pinch** | Left Click | Pinch index and thumb together to click. |
| 👌👌 **Double Pinch** | Double Click | Pinch twice quickly. |
| 🤏 **Pinch and Hold** | Drag | Hold the pinch gesture to drag items or windows. |
| ✌️ **Two Fingers (Held together)** | Scroll | Hold index and middle fingers close together and move up/down to scroll continuously. |
| 🖕 **Middle Finger** | Adjust Brightness | Hold only your middle finger up and move your hand up/down to seamlessly increase/decrease brightness. |
| 🖐️ **Three Fingers** | Right Click | Spreading three fingers triggers a right click. |

### Shortcuts & Actions (Hold to execute)
| Gesture | Action | Description |
| :--- | :--- | :--- |
| ✌️ **Victory (V-Shape)** | Open VS Code | Spread index and middle fingers apart into a 'V'. |
| 🤟 **Rock On (Thumb + Index + Pinky)** | Open Chrome | Opens Google Chrome. |
| 🖖 **Four Fingers** | Screenshot | Takes a screenshot of the current screen. |
| 👍 **Thumb Up** | Volume Up | Increases system volume. |
| 👎 **Thumb Down** | Volume Down | Decreases system volume. |
| ✋ **Open Palm** | Task View | Opens Windows Task View. |
| ✊ **Closed Fist** | Show Desktop | Minimizes all windows to show the desktop. |
| 🤞 **Crossed Fingers** | Lock PC | Cross your index and middle fingers to lock your computer. |
| 🤙 **Call Me** | Cycle Modes | Cycles between GENERAL, MEDIA, and DRAW modes. |


## Media Mode

| Gesture | Action |
| :--- | :--- |
| 👌 **Pinch** | Play / Pause |
| ✌️ **Victory (V-Shape)** | Next Track |
| 🖐️ **Three Fingers** | Previous Track |
| ✊ **Closed Fist** | Mute System |
| 🤙 **Call Me** | Cycle Modes | Cycles between GENERAL, MEDIA, and DRAW modes. |

---

## Draw Mode

| Gesture | Action | Description |
| :--- | :--- | :--- |
| ☝️ **Pointing (Index Finger)** | Draw | Draw on the screen smoothly at 60 FPS. |
| ✋ **Open Palm** | Hover | Move the brush cursor without drawing. |
| ✊ **Closed Fist** | Clear Canvas | Erases everything on the canvas. |
| ✌️ **Victory (V-Shape)** | Undo | Undo the last drawing stroke. |
| 🖐️ **Three Fingers** | Redo | Redo the last undone stroke. |
| 🖖 **Four Fingers** | Save Drawing | Saves the current canvas to a file. |
| 👍 **Thumb Up** | Cycle Color | Change the drawing color. |
| 👎 **Thumb Down** | Toggle Eraser | Switch between the drawing brush and the eraser. |
| 🤙 **Call Me** | Cycle Modes | Cycles between GENERAL, MEDIA, and DRAW modes. |

## Custom Gestures
You can also train your own custom gestures using the Trainer Window in the application's UI. Once trained, custom gestures will be recognized automatically and can be mapped to any action in your profile (e.g. `profiles/default.json`).

## Tips for Best Performance
- Action gestures (like Opening Chrome, Changing Volume, etc.) require you to hold the pose steadily to execute.
- Mouse movements like pointing, clicking, dragging, scrolling, and adjusting brightness execute **immediately and continuously**.
- Make sure to spread your fingers for **Victory**, and keep them tight for **Two Fingers (Scroll)**!
