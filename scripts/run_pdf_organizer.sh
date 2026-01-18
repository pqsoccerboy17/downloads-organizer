#!/bin/bash
# Downloads Organizer PDF Scheduler
# This script is called by launchd to run the PDF organizer

cd /Users/mdmac/Documents/downloads-organizer
export PYTHONPATH="/Users/mdmac/Documents/downloads-organizer/src:$PYTHONPATH"

/usr/bin/python3 -c "
import sys
sys.path.insert(0, '/Users/mdmac/Documents/downloads-organizer/src')
from downloads_organizer import pdf_organizer
pdf_organizer.run(auto_yes=True)
"
