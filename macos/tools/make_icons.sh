#!/bin/sh
# Renders App/Resources/AppIcon.svg into every size the app icon set lists (XcodeGen's preGenCommand).
# Needs rsvg-convert (brew install librsvg). The PNGs are generated, not committed.
set -e
cd "$(dirname "$0")/.."
out=App/Resources/Assets.xcassets/AppIcon.appiconset
for size in 16 32 64 128 256 512 1024; do
  rsvg-convert -w "$size" -h "$size" App/Resources/AppIcon.svg -o "$out/icon_$size.png"
done
