# Microsoft Store listing draft

Store status: **NOT STARTED**. This is prepared copy, not an existing Partner
Center submission. Product identity, package validation, screenshots, and the
account questionnaire are pending.

## Application name

SmartGestureOS

## Short description

Control Windows with webcam hand gestures for mouse movement, media, and drawing.

## Full description

SmartGestureOS is a Windows desktop utility that turns hand gestures captured by
a normal webcam into computer actions. It runs on top of Windows and adds a
touchless way to interact alongside your mouse and keyboard.

See your camera preview and 21 tracked hand landmarks, the raw and stable
gesture, the active mode, and recent actions. GENERAL mode controls the cursor,
clicks, drag and drop, scrolling, volume, supported display brightness, Windows
shortcuts, and app launchers. MEDIA mode controls play/pause, track changes, and
mute. DRAW mode provides an air-drawing canvas with undo, redo, colors, eraser,
and PNG saving.

Press Ctrl+Alt+G or use the Pause button to stop desktop actions while keeping
the preview visible. Gesture Coach explains the built-in poses. A normal
Windows installation bundles the runtime and hand-tracking model; Python and
developer tools are not required.

Camera frames are processed on your device. The app does not require an account.
Settings, custom gesture samples, screenshots, drawings, and diagnostic logs
may be saved locally. MediaPipe states that its Tasks APIs send performance and
usage metrics to Google, while images and video remain on the device. Read the
privacy policy for the dependency behavior and local file locations.

SmartGestureOS is an open-source computer-vision and human-computer interaction
project. It is not a replacement operating system or a certified medical or
accessibility solution. Recognition depends on lighting, hand visibility,
camera quality, and your PC. Display brightness control depends on hardware;
Chrome and VS Code launch gestures require those applications to be installed.
The custom gesture Trainer is experimental.

## Feature list

- Live webcam preview, 21 hand landmarks, and gesture feedback
- Cursor, click, double-click, drag/drop, scroll, and right-click
- GENERAL, MEDIA, and DRAW modes
- Volume, supported display brightness, screenshots, and Windows shortcuts
- Air drawing with undo/redo, colors, eraser, and PNG export
- Pause button and Ctrl+Alt+G emergency pause
- Gesture Coach, settings profiles, and experimental custom gesture training

## Links and requirements

| Field | Value |
| --- | --- |
| Website | https://sarvagyabirla.github.io/SmartGestureOS/ — deployment pending |
| Privacy URL | https://github.com/Sarvagyabirla/SmartGestureOS/blob/main/PRIVACY.md |
| Support URL | https://github.com/Sarvagyabirla/SmartGestureOS/issues |
| Source and license | https://github.com/Sarvagyabirla/SmartGestureOS — MIT |
| Platform | Windows 10/11 x64; MSIX manifest minimum Windows 10 version 1809 |
| Hardware | Webcam with desktop camera access; one clearly visible hand |
| Runtime | Included; no Python installation required |
| Application icon | `Assets/Square310x310Logo.png`; desktop icon in `../SmartGestureOS.ico` |
| Package | Build with `scripts/build_msix.ps1` after real identity is supplied |

## Release notes draft for the first validated release

Initial SmartGestureOS release with webcam hand tracking, Windows mouse control,
GENERAL/MEDIA/DRAW modes, Gesture Coach, settings, emergency pause, and local
drawing/screenshot saving. Final notes must reflect the hardware validation
report and any remaining limitations before submission.

## Screenshots to capture from the validated application

No fabricated application screenshots are supplied. Capture these from the
installed release using an empty, non-sensitive desktop:

1. Dashboard with a real hand, landmarks, mode, and gesture feedback.
2. GENERAL mode demonstrating cursor control and the recent action list.
3. MEDIA mode showing the available playback gestures.
4. DRAW canvas containing a saved sample drawing.
5. Gesture Coach and the visible pause state.

Review current Partner Center screenshot size requirements while uploading.

## Account fields still required

- Exact Package Identity Name, Publisher, and Publisher Display Name.
- Reserved product name, markets, pricing/availability, and contact information.
- Age-rating questionnaire completed by the account holder using the actual
  product behavior; do not preselect or invent a rating.
- Explain `runFullTrust`: the desktop application uses Windows input and system
  APIs to execute user-directed gesture actions. Explain `webcam`: frames are
  required to locate hands and recognize gestures.
- Final screenshots, package upload, certification answers, and actual status.

After submission, record one of SUBMISSION DRAFT, SUBMITTED, IN CERTIFICATION,
PUBLISHED, or REJECTED / ACTION REQUIRED, with the date and Partner Center
evidence. A locally built MSIX alone does not establish a Store submission.
