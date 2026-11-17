#!/bin/sh
set -eu
cd "$(dirname "$0")"
APP='dist/Mac ARJ.app'
mkdir -p "$APP/Contents/MacOS"
xcrun swiftc -swift-version 5 -target "$(uname -m)-apple-macos13.0" -O -framework AppKit -framework UniformTypeIdentifiers Sources/main.swift -o "$APP/Contents/MacOS/Mac ARJ"
cp Info.plist "$APP/Contents/Info.plist"
printf 'APPL????' > "$APP/Contents/PkgInfo"
/usr/bin/codesign --force --sign - "$APP"
/usr/bin/plutil -lint "$APP/Contents/Info.plist"
/usr/bin/codesign --verify --strict "$APP"
printf '\nBuilt: %s/%s\n' "$PWD" "$APP"
