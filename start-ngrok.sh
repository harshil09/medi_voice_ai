#!/bin/bash
# Run from project root after: uvicorn main:app --port 8000
#
# First time only (paste ONLY the token, nothing else):
#   ./bin/ngrok config add-authtoken PASTE_TOKEN_HERE
# Get token: https://dashboard.ngrok.com/get-started/your-authtoken
#
# Do NOT use: export NGROK_AUTHTOKEN=... with add-authtoken
# Do NOT use: NGROK_AUTHTOKEN=xxx as the token argument

cd "$(dirname "$0")"
export PATH="$(pwd)/bin:$PATH"
exec ngrok http 8000
