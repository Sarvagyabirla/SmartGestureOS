# STEP 2: physical mouse check

Run from the repository root in PowerShell, with other SmartGestureOS instances closed:

```powershell
.\.venv\Scripts\python.exe scripts\validate_mouse_controls.py
```

This opens the production application paused and one guided mouse target. The
webcam preview uses the actual camera, detector, classifier, mapper, EventEngine
and Windows mouse controller. Nothing starts by importing the script or passing
`--help`. The guided target is brought forward once at startup.

1. Confirm moving hand landmarks in the production preview, then bring the
   **physical mouse check** window to the foreground.
2. Read the current instruction and click **Start / retry this check**. Remove
   your hand briefly so the normal neutral re-arm guard can complete.
3. Use your hand for the requested interaction. Watch the target and Windows
   event counters. Keep your physical mouse still during the check.
4. Press Esc to pause, then click **I observed it using my hand** only after seeing the requested behavior,
   or **Unclear / skip**. Each answer pauses automation and advances the guide.
5. Complete cursor movement, single click, double click, drag/release, scrolling
   in both directions (watch **Wheel: UP/DOWN**), and right click. A held right-click gesture should not
   repeat until released. The dragged square must stop following after release.
6. Click **Save report and close**. Closing either window also shuts down the
   normal app, camera and input resources and saves the local report.

Esc in the target, the existing application Pause button, and Ctrl+Alt+G pause
automation. Switching away from the target automatically pauses; returning to
it does not resume. Resume with the target's Start button or Ctrl+Alt+G while it
has focus. The ordinary application Resume button cannot arm input while the
target is in the background.

Generated cursor movement stays inside the target canvas. New button presses
and wheel events are rejected when the target is not in front or the cursor is
outside that canvas. Button releases remain enabled so a drag can be released
on pause, focus loss or shutdown. The physical mouse is never clipped. Mode
changes, sleep, brightness and mapped system actions are suppressed only in
this diagnostic process; profile settings are not changed.

Reports are written to the ignored `logs/mouse-validation-<timestamp>.json` path;
`--report <path>` selects another local file. Reports contain event counts,
recent raw/stable gesture labels and your explicit observations, without webcam
images. Windows event receipts can also come from a physical mouse and do not
automatically establish a pass. Review the six human observations before marking
STEP 2 complete. Normal unrestricted desktop behavior still needs its own
physical check, and the stability/packaged-build checks remain separate steps.
