#!/bin/bash
deactivate

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

pip install -r requirements.txt