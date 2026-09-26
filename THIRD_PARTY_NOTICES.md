# Third-Party Notices

This document lists the direct production dependencies pinned in
`requirements.txt`, checked on 27 September 2026 against installed package
versions and license files. Their licenses are reproduced or linked below.
Transitive dependencies and bundled native components also carry license
notices; the finished distribution must include those notices.

## Dependency network behavior

A real run with MediaPipe 0.10.35 on 27 September 2026 produced a native
`portable_clearcut_uploader.cc` error reporting a failed Clearcut upload.
The log does not identify the payload or establish a successful transfer.
[MediaPipe issue #6291](https://github.com/google-ai-edge/mediapipe/issues/6291)
reports a matching message. This remains unresolved for this project, so these
dependencies cannot currently be represented as having verified zero telemetry
or no network activity. See [PRIVACY.md](PRIVACY.md) for the observation and its
limits.

---

## mediapipe

**Version:** 0.10.35\
**License:** Apache 2.0\
**URL:** https://github.com/google-ai-edge/mediapipe\
Copyright © Google LLC\
License text: https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE

---

## opencv-contrib-python

**Version:** 5.0.0.93\
**License:** MIT for the Python packaging; Apache 2.0 for OpenCV, with additional bundled-component notices\
**URL:** https://github.com/opencv/opencv-python\
Copyright © 2015 OpenCV\
License text: https://github.com/opencv/opencv/blob/master/LICENSE
Python packaging license: https://github.com/opencv/opencv-python/blob/master/LICENSE.txt
The wheel also supplies `LICENSE-3RD-PARTY.txt`.

---

## numpy

**Version:** 2.4.6\
**License:** BSD 3-Clause; the wheel also includes 0BSD, MIT, Zlib, and CC0-1.0 components\
**URL:** https://github.com/numpy/numpy\
Copyright © NumPy Developers\
License text: https://github.com/numpy/numpy/blob/main/LICENSE.txt

---

## Pillow

**Version:** 12.3.0\
**License:** MIT-CMU\
**URL:** https://github.com/python-pillow/Pillow\
Copyright © Jeffrey A. Clark (Alex) and contributors\
License text: https://github.com/python-pillow/Pillow/blob/main/LICENSE

---

## customtkinter

**Version:** 6.0.0\
**License:** MIT\
**URL:** https://github.com/TomSchimansky/CustomTkinter\
Copyright © 2023 Tom Schimansky

The shipped `LICENSE` contains the MIT terms below. This version's package
metadata also lists CC0; retain the shipped license text when distributing it.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the
Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.

---

## pycaw

**Version:** 20251023\
**License:** MIT\
**URL:** https://github.com/AndreMiras/pycaw\
Copyright © 2016 AndreMiras

(MIT License — same terms as above)

---

## psutil

**Version:** 7.0.0\
**License:** BSD 3-Clause\
**URL:** https://github.com/giampaolo/psutil\
Copyright © 2009 Jay Loden, Dave Daeschler, Giampaolo Rodolà\
License text: https://github.com/giampaolo/psutil/blob/master/LICENSE

---

## keyboard

**Version:** 0.13.5\
**License:** MIT\
**URL:** https://github.com/boppreh/keyboard\
Copyright © 2016 BoppreH

---

## pyttsx3

**Version:** 2.99\
**License:** Mozilla Public License 2.0 (MPL-2.0)\
**URL:** https://github.com/nateshmbhat/pyttsx3
License text: https://github.com/nateshmbhat/pyttsx3/blob/master/LICENSE

---

## screen-brightness-control

**Version:** 0.27.2\
**License:** MIT\
**URL:** https://github.com/Crozzers/screen-brightness-control

---

## platformdirs

**Version:** 4.11.7\
**License:** MIT\
**URL:** https://github.com/platformdirs/platformdirs

---

## screeninfo

**Version:** 0.8.1\
**License:** MIT\
**URL:** https://github.com/rr-/screeninfo

---

## comtypes

**Version:** 1.4.16\
**License:** MIT\
**URL:** https://github.com/enthought/comtypes

---

## pywinstyles

**Version:** 1.8\
**License:** CC0 1.0 Universal\
**URL:** https://github.com/Akascape/py-window-styles
License text: https://github.com/Akascape/py-window-styles/blob/main/LICENSE

---

*This file is provided for compliance with the license terms of bundled
open-source components. All trademarks are the property of their respective owners.*
