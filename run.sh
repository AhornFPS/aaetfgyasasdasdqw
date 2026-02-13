#!/bin/bash
# Force Qt to use XWayland for better overlay compatibility
export QT_QPA_PLATFORM=xcb

# Run the application
python "Dior Client.py"
