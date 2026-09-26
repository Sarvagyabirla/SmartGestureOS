# Gesture Reference

SmartGestureOS recognizes 14 static hand poses. Pinch click, double-click, and
drag are temporal actions built around the Pinch pose. Discrete actions execute
after the configured hold time (300 ms by default); adjust it in Settings.

## Gestures used in every mode

| Gesture | GENERAL | MEDIA | DRAW |
|---|---|---|---|
| Call Me (thumb and pinky extended) | Cycle to next mode | Cycle to next mode | Cycle to next mode |
| Pointing (index finger extended) | Move cursor | — | Draw on the in-app canvas |
| Pinch (thumb and index touch) | Click; pinch twice for double-click; hold to drag | Play or pause | Hover the canvas pointer |

## GENERAL mode

| Gesture | Action |
|---|---|
| Two Fingers (index and middle together) | Scroll up/down with hand movement |
| Three Fingers | Right-click |
| Middle Finger | Adjust screen brightness by moving the hand up/down |
| Victory (index and middle spread into a V) | Open VS Code |
| Rock On (thumb, index, and pinky extended) | Open Chrome |
| Four Fingers | Take a screenshot |
| Thumb Up / Thumb Down | Increase / decrease system volume |
| Open Palm | Open Windows Task View |
| Closed Fist | Show the desktop |
| Crossed Fingers (index and middle crossed) | Lock the PC |

## MEDIA mode

| Gesture | Action |
|---|---|
| Pinch | Play or pause media |
| Victory | Next track |
| Three Fingers | Previous track |
| Closed Fist | Mute media volume |

## DRAW mode

| Gesture | Action |
|---|---|
| Pointing | Draw on the canvas in the app window |
| Open Palm | Move the brush cursor without drawing |
| Closed Fist | Clear the canvas |
| Victory | Undo the last stroke |
| Three Fingers | Redo the last undone stroke |
| Four Fingers | Save the drawing |
| Thumb Up | Cycle drawing color |
| Thumb Down | Toggle the eraser |

Drawing is limited to the in-app canvas; it does not draw over arbitrary Windows
applications. User-trained poses can be created in the Trainer window and
mapped through the active profile.

## Recognition tips

- Keep the hand in view with even lighting and the palm facing the camera.
- Spread index and middle fingers for Victory; keep them close and parallel for
  Two Fingers scrolling.
- Call Me uses thumb and pinky only. Rock On uses thumb, index, and pinky.
- If the pointer feels slow, set **Pointer Smoothing** closer to 1 in Settings.
  Higher values trade response speed for steadier movement.
