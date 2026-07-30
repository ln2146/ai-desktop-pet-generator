#!/usr/bin/env bash
# Bundle PetGen.app into a distributable .dmg with a drag-to-Applications layout.
# Usage: bash packaging/make_dmg.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/dist/PetGen.app"
DMG="$ROOT/dist/PetGen.dmg"
VOL="PetGen"
STAGING="$(mktemp -d -t petgen-dmg)"
trap 'rm -rf "$STAGING"; hdiutil detach "/Volumes/$VOL" -force >/dev/null 2>&1 || true' EXIT

if [ ! -d "$APP" ]; then
  echo "ERROR: $APP not found. Build the app first: pyinstaller packaging/petgen.spec"
  exit 1
fi

rm -f "$DMG"
echo "Staging $APP into $STAGING ..."
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

echo "Creating DMG image ..."
hdiutil create -volname "$VOL" -srcfolder "$STAGING" -ov -format UDZO "$DMG"

echo "Done: $DMG"
ls -lh "$DMG"
