#!/bin/bash

# Activate the correct environment
source venv311/bin/activate

# Run the summary script
if [ $# -eq 0 ]; then
    python3 run_summary.py
else
    python3 run_summary.py "$1"
fi
