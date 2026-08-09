# NOTE: superseded by install_all_models.py, which pulls the full model
# list main.py actually needs (this file is missing qwen3:8b and llava).
# Kept only for reference; prefer: python install_all_models.py
import ollama
import time
import sys

# Standard model names
models = ["llama3.1", "mistral", "phi3:mini", "deepseek-coder"]

print("Starting Robust Model Download...")

for model in models:
    print(f"\nAttempts to pull {model}...")
    success = False
    for attempt in range(3):
        try:
            ollama.pull(model)
            print(f"Success: {model}")
            success = True
            break
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    
    if not success:
        print(f"Failed to pull {model} after 3 attempts.")

print("\nOperations complete.")
