#!/usr/bin/env bash
# Launch USL Extractor from any working directory.
DIR="$(cd "$(dirname "$0")" && pwd)"
java -jar "$DIR/USLExtractor.jar"
