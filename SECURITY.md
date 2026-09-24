# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.9.x (current) | ✅ Active |
| 0.8.x | ⚠️ Patch-only |
| < 0.8 | ❌ End of life |

## Reporting a Vulnerability

**Please do NOT open a public GitHub Issue for security vulnerabilities.**

Report security issues privately via GitHub's
[Security Advisories](https://github.com/Sarvagyabirla/SmartGestureOS/security/advisories/new)
feature ("Report a Vulnerability" button).

You can expect:
- **Acknowledgement** within 48 hours.
- **Initial assessment** within 7 days.
- **Patch or mitigation** within 30 days for confirmed high/critical issues.

## Threat Model

SmartGestureOS is a **local-only** Windows desktop application:

- **No network access.** The application does not make any outbound connections.
- **No remote code execution surface.** All input is from local camera and user settings.
- **Attack surface:** Local input validation (profile names, gesture names, file paths).
  All user-provided strings that are used to construct file paths are now validated
  against an allowlist regex before use.
- **Camera frames:** Processed in memory by MediaPipe. Never written to disk.
- **Privilege:** Runs as the current user. Does not request elevation.

## Out of Scope

- Issues in bundled third-party libraries (report to those projects directly).
- Theoretical issues that require physical access to an already-compromised machine.
- Visual spoofing / adversarial hand gestures (no security guarantee for gesture recognition accuracy).
