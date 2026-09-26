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

SmartGestureOS is a Windows desktop application with local camera processing:

- **Dependency network behavior:** MediaPipe 0.10.35 logged a failed native
  uploader attempt during a real run. Payload and successful transmission were
  not established. The current dependency stack has no verified zero-network
  guarantee; see [PRIVACY.md](PRIVACY.md).
- **Inputs:** Camera frames, local profiles and custom gesture files. The
  application does not implement a remote-control server.
- **Attack surface:** Local input validation (profile names, gesture names, file paths).
  All user-provided strings that are used to construct file paths are now validated
  against an allowlist regex before use.
- **Camera frames:** The normal pipeline processes frames in memory. Explicit
  development diagnostics can save frames, and the screenshot action saves the
  desktop when invoked.
- **Privilege:** Runs as the current user. Does not request elevation.

## Out of Scope

- Issues in bundled third-party libraries (report to those projects directly).
- Theoretical issues that require physical access to an already-compromised machine.
- Visual spoofing / adversarial hand gestures (no security guarantee for gesture recognition accuracy).
