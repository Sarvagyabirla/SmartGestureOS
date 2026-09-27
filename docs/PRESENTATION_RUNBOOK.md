# SmartGestureOS presentation and acceptance runbook

Presentation: **REAL-TIME HAND GESTURE CONTROL SYSTEM FOR DESKTOP AUTOMATION**  
Deadline: **30 September 2026**  
Team: Sarvagya Birla, Uday Dangi, Shantanu Yadav  
Guide: Ms. Ankita Dubey

The [product specification](PRODUCT_SPECIFICATION.md) controls the demo scope.
SmartGestureOS is a Windows 10/11 x64 webcam utility that supplements mouse and
keyboard input. It is not an operating system or a certified accessibility or
medical product.

This is a rehearsal and recording template, **not a completed acceptance report**.
Real presentation screenshots and a backup demo recording have not yet been
captured. The [hardware report](HARDWARE_VALIDATION_REPORT.md) retains earlier
hand-tracking and cursor observations; those do not establish acceptance of
every interaction on the final installed candidate.

## Before the presentation

- Identify the exact candidate: version, source commit, installer filename and
  SHA256. Use the same installed build for acceptance, recording and rehearsal.
- Check the webcam, classroom lighting, power, screen resolution and projector.
  Close other applications using the webcam. Keep the physical mouse and keyboard
  available, and use a disposable document/window for input demonstrations.
- Confirm the Pause button is reachable. Check whether Ctrl+Alt+G registered;
  the dashboard reports a missing shortcut. After Resume, lower the hand briefly
  before showing an action gesture.
- Open the browser, VS Code and a media player for the actions that will be shown.
  Use a short local media file to avoid depending on classroom internet access.
- Review [GESTURES.md](../GESTURES.md), the [privacy policy](../PRIVACY.md) and
  the current [release readiness](../RELEASE_READINESS.md). Record any limitations
  in the speaking notes before rehearsing.
- Recheck public links on the day. The 27 September audit recorded no public
  release and unavailable Pages. A local installer or website preview is not
  evidence of a public release or deployment.
- Read the actual Store status from the submission evidence. **NOT STARTED** is
  the recorded baseline; package artwork and a listing draft do not establish a
  submission or publication.

## Exact 23-step live demo

Follow the specification's sequence. For unavailable distribution milestones,
show their actual status and the prepared local material; do not fabricate a
download, listing or successful submission.

| Step | Demonstration | What to show or explain |
|---|---|---|
| 1 | Open GitHub Pages website. | Open the verified [product URL](https://sarvagyabirla.github.io/SmartGestureOS/). If it is unavailable, explicitly identify a local `site/` preview as an undeployed preview. |
| 2 | Explain the problem. | Ask whether an ordinary webcam can translate natural hand movements into reliable Windows commands without specialized hardware. |
| 3 | Explain SmartGestureOS solution. | A touchless input layer runs on Windows alongside the physical mouse and keyboard. |
| 4 | Show GitHub repository. | Show the [repository](https://github.com/Sarvagyabirla/SmartGestureOS), architecture and tested source commit. |
| 5 | Show downloadable release. | Show the actual installer and checksum in [GitHub Releases](https://github.com/Sarvagyabirla/SmartGestureOS/releases) only if published. Otherwise state that publication is pending and identify any local candidate accurately. |
| 6 | Launch installed SmartGestureOS. | Launch from the Start Menu. If only a source or portable build is available, identify that limitation; this does not pass the installed-app milestone. |
| 7 | Show webcam. | Demonstrate the live mirrored preview and camera status. |
| 8 | Show 21 landmarks. | Move one hand and show the skeleton following it. |
| 9 | Explain MediaPipe. | MediaPipe Hand Landmarker locates landmarks using VIDEO inference; separate geometry and timing code determines gestures and actions. |
| 10 | Show raw gesture. | Change a pose and point out the immediate classification label. |
| 11 | Show stable gesture. | Explain temporal stabilization and heuristic confidence; confidence is not a measured accuracy guarantee. |
| 12 | Move cursor using Pointing. | Keep the physical mouse still and deliberately move across the target desktop area. |
| 13 | Pinch to click. | Perform a short pinch and release on a harmless target; verify one click. |
| 14 | Drag an object/window. | Hold a pinch, move the target, then release; demonstrate that the object stops following. |
| 15 | Scroll. | Show Two Fingers together and move vertically; scroll both ways and stop on release. |
| 16 | Perform a Windows shortcut gesture. | Use a rehearsed action such as Open Palm for Task View or Victory for VS Code; verify the actual result. |
| 17 | Switch mode. | Hold Call Me to enter MEDIA; keep holding briefly to show that it does not repeatedly cycle, then release. |
| 18 | Demonstrate MEDIA. | Show Pinch play/pause, Victory next track, Three Fingers previous track and Closed Fist mute on the prepared player. |
| 19 | Demonstrate DRAW. | Use Call Me to enter DRAW. Show Pointing draw, Open Palm hover, Victory undo, Three Fingers redo, Thumb Up color, Thumb Down eraser, Four Fingers save and Closed Fist clear. Check the saved PNG. |
| 20 | Pause automation with Ctrl+Alt+G. | Confirm PAUSED on the dashboard while camera tracking continues and desktop actions stop. If the shortcut is unavailable, demonstrate the button and disclose the unresolved shortcut limitation. |
| 21 | Resume. | Resume, lower the hand briefly to satisfy the neutral gate, then deliberately show a new gesture. |
| 22 | Explain privacy/local processing. | Frames and landmarks are processed in memory on the device. Explain user-requested local screenshots/drawings and MediaPipe's published performance/usage metrics disclosure; do not claim zero network activity. Refer to the privacy policy. |
| 23 | Show Microsoft Store submission/listing status. | Show only the evidenced state: NOT STARTED, PACKAGE READY, SUBMISSION DRAFT, SUBMITTED, IN CERTIFICATION, PUBLISHED, or REJECTED / ACTION REQUIRED. Use the real listing only after publication. |

## Physical acceptance session: 20–30 minutes

Use the existing [guided mouse check](MOUSE_HARDWARE_CHECK.md) and
[validation tool](../scripts/validate_mouse_controls.py) for the six core input
checks. Follow its Start, neutral re-arm, observation and report controls. It
confines generated input to its target and suppresses mode/system actions only
inside that diagnostic process. Run the installed app separately for normal
desktop, mode, packaging and long-session acceptance.

For a source validation environment, launch the guide from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\validate_mouse_controls.py
```

The guide saves local JSON reports under `logs/`; its documentation explains the
`--report` option. Event receipts alone are not proof of a gesture: keep the
physical mouse still while performing each gesture and record the human
observation. The guide does not save webcam images.

Record the following for every session:

| Field | Record before testing |
|---|---|
| Operator and date/time | Pending |
| Candidate version, commit and installer SHA256 | Pending |
| Environment | Windows version/build, x64, machine, camera model/index, display resolution/scaling |
| Test origin | Installed app, standalone folder, or source; identify each separately |
| Session duration | Start/end times and elapsed minutes |
| Conditions | Lighting, approximate hand distance, other camera applications, workload |
| Evidence | Guide JSON, relevant log excerpt, observed results and any local recording filenames |

Result vocabulary:

- **PASS**: the operator observed the stated behavior on the recorded candidate.
- **FAIL**: attempted behavior was wrong, unreliable or crashed; record the
  trigger, expected/actual result and relevant log time.
- **UNSUPPORTED HARDWARE**: a specific optional hardware capability, such as
  monitor brightness control, is unavailable and the app reports that accurately.
  This does not substitute for required webcam or core-input acceptance. A
  missing application is not unsupported hardware.
- **NOT TESTED**: not attempted, inconclusive, or evidence missing. Automated
  tests and historical observations do not change a new candidate's row to PASS.

A suggested 30-minute schedule is 0–3 minutes setup/tracking, 3–9 minutes guided
mouse checks, 9–14 minutes recovery/safety, 14–22 minutes modes and system actions,
22–28 minutes continued mixed use, and 28–30 minutes exit/relaunch. A shorter
20-minute session must still cover every relevant check; record additional
sessions rather than inventing coverage. Record camera FPS, detector FPS,
inference latency and RAM near the beginning, middle and end. Treat these as
measurements on this machine, not performance promises.

| Check | Procedure and acceptance | Candidate result |
|---|---|---|
| Startup and actual camera format | Launch, verify live preview and 21 moving landmarks; confirm configured camera selection and the reported/observed resolution. | NOT TESTED |
| Lighting and distance | Track an actual hand in normal and dimmer room light at comfortable near/far positions; record recognition gaps and camera/detector rates. | NOT TESTED |
| Cursor | Complete the guide's cursor step, then reach all primary-screen edges in the installed app without severe lag or jitter. | NOT TESTED |
| Single click | Perform separate short pinches; each release produces one click, with no later ghost click. | NOT TESTED |
| Double click | Perform two fast short pinches; observe one double-click and no unintended drag. | NOT TESTED |
| Drag/drop | Hold Pinch, move the object and release; the object stops following and a later physical click works normally. | NOT TESTED |
| Scroll | Move Two Fingers up/down; observe both directions, controlled speed, and immediate stop when the pose releases. | NOT TESTED |
| Right click | Hold Three Fingers; observe one context-menu event. Release and repeat; exactly one new event should occur. | NOT TESTED |
| Hand loss during drag | Start a harmless drag, move the hand fully out of view, then move the physical mouse. The object must no longer follow and no mouse button may remain held. | NOT TESTED |
| Camera loss during drag | With a USB webcam, start a harmless drag and unplug it. Verify release, disconnected/recovering feedback and a responsive UI. For an integrated camera use an actual supported disconnect method; otherwise record NOT TESTED. | NOT TESTED |
| Reconnect | Reconnect the camera and wait for fresh preview/landmarks; previous click/drag state must not resume. Deliberately start a new action. | NOT TESTED |
| Global pause | While another application has focus and a gesture drag is active, use Ctrl+Alt+G. Verify release and PAUSED; repeat with scroll and a pending held action. | NOT TESTED |
| UI pause and re-arm | Use Pause during an active gesture. Resume while still holding it: actions must remain blocked. Lower the hand briefly, then verify deliberate new input. | NOT TESTED |
| Settings/Coach/Trainer | Open each window and practice a gesture; automation must be paused. Closing the window must not silently resume actions. | NOT TESTED |
| Mode switching | Cycle GENERAL → MEDIA → DRAW → GENERAL with separate Call Me holds. One sustained hold must switch only once. | NOT TESTED |
| Application launch | Victory opens VS Code; Rock On opens Chrome when installed. A missing application must give an actionable failure message without a crash. Record availability and each result. | NOT TESTED |
| Desktop functions | Check Open Palm Task View, Closed Fist Show Desktop, Four Fingers screenshot and Crossed Fingers lock on the test machine; unlock normally and confirm control recovers. | NOT TESTED |
| Volume | Thumb Up/Down changes actual volume in controlled steps; record the endpoint/device. An unavailable endpoint must produce accurate UI feedback. | NOT TESTED |
| Brightness | Middle Finger changes actual supported-display brightness smoothly. If unsupported, record the display and confirm truthful feedback without repeated crashes. | NOT TESTED |
| Media | Verify play/pause, next, previous and mute in a real player. Holding a one-shot pose must not repeatedly toggle or skip. | NOT TESTED |
| Drawing | Draw separate strokes, hover, undo/redo, change color, erase and clear. Check visible results and no unintended connecting stroke after hand loss. | NOT TESTED |
| Drawing/screenshot files | Save twice; verify distinct PNG filenames and open the actual images from the configured per-user output folders. | NOT TESTED |
| Drawing resize | Resize the app preview; verify alignment. If camera resolution is changed, restart as Settings directs and verify drawing/coordinate behavior at the actual new format. | NOT TESTED |
| Sustained mixed use | Continue through the full recorded session, including normal background workload. Record stalls, RAM growth, failed actions and repeated errors; no stuck input or unhandled crash is acceptable. | NOT TESTED |
| Exit during drag | Close the app during a harmless active drag. Verify button release, camera indicator off and no continuing automation. | NOT TESTED |
| Relaunch | Relaunch the same installed candidate; verify settings, fresh camera tracking and no retained pending action. | NOT TESTED |

For every FAIL, save the shortest reproduction and its timestamp, fix the cause,
then rerun the failed check and relevant safety checks. A candidate with an
unresolved stuck-button, unintended-action or shutdown failure is not ready for
the live demo. Link the final observed results in
[HARDWARE_VALIDATION_REPORT.md](HARDWARE_VALIDATION_REPORT.md).

## Backup and freeze record

Keep a local presentation folder and a second copy on removable storage. Record
actual filenames and verification dates below; an empty row remains incomplete.

| Required item | Acceptance before freeze | Current record |
|---|---|---|
| Installed demo | Candidate launches from Start Menu, completes the physical matrix and closes safely. | Pending candidate acceptance |
| Installer backup | Exact `SmartGestureOS-Setup-v0.9.0.exe` plus SHA256; verify both backup copies against the recorded hash. | Pending final artifact verification |
| Clean-machine evidence | Install, launch, camera/core gestures, uninstall and reinstall on Windows without depending on Python, a venv or the repository. | Pending physical/clean-machine acceptance |
| Source backup | Archive the precise source commit and dependencies/build instructions; retain its commit ID. | Pending final freeze commit |
| Demo recording | Capture an actual successful installed-app session, including landmarks, cursor/click/drag, modes, pause/resume and real distribution status; play the saved video offline. | NOT CAPTURED |
| Screenshots | Capture real installed-app dashboard, tracking, each mode and useful result states; remove private desktop information before sharing. | NOT CAPTURED |
| Architecture explanation | Explain camera → VIDEO landmarks → raw/stable classification → mode mapping → event engine → controllers → Windows, with GUI state alongside it. | Prepared in specification; rehearsal pending |
| Public URLs | Verify repository, Pages, actual release download, privacy/support and Store listing if one exists. Save a local website copy for offline explanation. | Recheck required; do not imply all are deployed |
| Store evidence | Record exact status/date from Partner Center or the published listing; preserve any certification messages. | NOT STARTED baseline; update only with evidence |
| Known limitations | Record unsupported displays, absent apps, hardware conditions and remaining unverified items. | Complete from acceptance results |
| Rehearsal | Run all 23 steps on the presentation machine/projector within the allocated time; test the offline backup path. | Pending |

If the camera or classroom hardware fails, pause/close the live application and
show the previously recorded successful demonstration. Clearly label it as a
recording, state its candidate version/date and explain the current live failure.
If no recording has been captured, show architecture/source and state that the
live behavior could not be demonstrated; do not substitute fabricated screenshots.

Freeze only the validated candidate. Record version **0.9.0**, commit, installer
hash, acceptance evidence and remaining external distribution status together.
Any code or packaging change after freeze requires a new artifact hash and
relevant checks before replacing the presentation copy. Never label Store
certification complete solely to meet the presentation deadline.
