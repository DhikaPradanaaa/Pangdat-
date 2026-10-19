$project = Split-Path $PSScriptRoot -Parent
python -m streamlit run (Join-Path $project "dashboard\app.py") --server.port 8501 --server.address 127.0.0.1
