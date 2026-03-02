#!/bin/bash
# Create Xcode project for TeslaCam Viewer
# Run this script to set up the project properly

cd "$(dirname "$0")"

echo "=== TeslaCam Viewer iOS Project Setup ==="
echo ""
echo "Due to Xcode project file complexity, please follow these manual steps:"
echo ""
echo "1. Open Xcode"
echo "2. Create New Project → iOS → App"
echo "3. Configure:"
echo "   - Product Name: TeslaCamViewer"
echo "   - Organization Identifier: com.teslacam"
echo "   - Interface: SwiftUI"
echo "   - Language: Swift"
echo ""
echo "4. Delete the auto-generated ContentView.swift"
echo ""
echo "5. Drag ALL files from this folder structure into Xcode:"
echo "   - TeslaCamViewer/App/"
echo "   - TeslaCamViewer/Views/"
echo "   - TeslaCamViewer/ViewModels/"
echo "   - TeslaCamViewer/Models/"
echo "   - TeslaCamViewer/Services/"
echo ""
echo "6. In Xcode Project Settings:"
echo "   - Deployment Target: iOS 16.0"
echo "   - Supported Destinations: iPhone only"
echo ""
echo "7. Connect your iPhone via USB"
echo "8. Select your device and click Run (⌘R)"
echo ""
echo "=== Files Created ==="
find TeslaCamViewer -name "*.swift" -type f | head -20

echo ""
echo "Done! Follow the instructions above to build in Xcode."
