#!/usr/bin/env bash
# Recompile and rebuild USLExtractor.jar after any source changes.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "Compiling..."
mkdir -p build/fat
cd build/fat && jar xf "$DIR/sqlite-jdbc.jar" && cd "$DIR"
javac -cp sqlite-jdbc.jar:. -d build/fat Database.java USLExtractorGUI.java

echo "Packaging..."
echo "Main-Class: USLExtractorGUI" > build/MANIFEST.MF
jar cfm USLExtractor.jar build/MANIFEST.MF -C build/fat .
rm -rf build

echo "Done — $(du -h USLExtractor.jar | cut -f1) JAR written to USLExtractor.jar"
