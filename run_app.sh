#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python -m streamlit run app.py
