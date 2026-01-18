#!/bin/bash
# Downloads Organizer Watcher Launcher
# This script is called by launchd to start the watcher

cd /Users/mdmac/Documents/downloads-organizer
export PYTHONPATH="/Users/mdmac/Documents/downloads-organizer/src:$PYTHONPATH"

/usr/bin/python3 -c "
import sys
sys.path.insert(0, '/Users/mdmac/Documents/downloads-organizer/src')
from downloads_organizer import watcher
watcher.run()
"
