# EmoDict - quick start

Dictate anywhere on your PC, 100% locally. Nothing you say ever leaves your machine.

## 1. Install
**Recommended:** run `EmoDict-Setup.exe`. It installs EmoDict with a Start-menu
entry and an uninstaller (Settings > Apps). During setup you can pick a desktop
shortcut and "start with Windows".

**Portable alternative:** unzip the zip anywhere (Desktop is fine) and
double-click **EmoDict.exe**. No install, no admin.

Either way, the first-run setup will:
- check your hardware and download the right speech model (one time, 150MB-800MB; needs internet)
- list your microphones and test one
- save settings (you can change everything later from the tray)

Windows SmartScreen may warn about an unknown publisher. Click
"More info" -> "Run anyway". (Unsigned beta; code signing comes later.)

## 2. Dictate
Hold **Right-Ctrl**, speak, release. Your words are typed wherever your cursor is.

## 3. Tray menu (right-click the mic icon, check the hidden-icons ^ arrow)
- **Settings** - change the hold key, microphone, model, output mode
- **Pause dictation** - suspend it temporarily (the icon goes grey)
- **Check for updates** - compares your version with the latest release
- **Quit** - clean exit; nothing can be typed after quit

## 4. Make it yours
Settings -> Dictionary. One correction per line, format:

    heard -> corrected
    flyt base -> Flytbase
    ashish -> Ashish

Words you fix once stay fixed forever.

## 5. Troubleshooting
- No text appears? Open Settings and check the microphone; the level meter must move when you talk.
- Words get cut? Speak a beat after pressing and a beat before releasing.
- App misbehaves? Logs are at `%LOCALAPPDATA%\EmoDict\logs\` (emodict.log, crash.log).
- Health check: run `EmoDict.exe --selftest` from a terminal.

## Privacy
Recording lives in RAM only, transcription runs on your machine, and no
network call happens after the one-time model download (except the optional
manual update check). Source of truth for this claim: the app has no other
networking code.

EmoDict v0.1.0 - beta
