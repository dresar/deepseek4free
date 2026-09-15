@echo off
echo ===================================================
echo 🤖 Memulai Aider CLI bertenaga DeepSeek Reasoning
echo Endpoint: http://localhost:8000/v1
echo Model: deepseek-reasoner (R1 Thinking)
echo ===================================================

.venv\Scripts\aider.exe --set-env OPENAI_API_BASE="http://localhost:8000/v1" --set-env OPENAI_BASE_URL="http://localhost:8000/v1" --set-env OPENAI_API_KEY="sk-deepseek4free" --model "openai/deepseek-reasoner" --no-show-model-warnings --yes-always %*
