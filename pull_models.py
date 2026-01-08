import ollama
import sys

models = ["llama3.1", "mistral", "phi3:mini", "deepseek-coder"]

print("Starting Model Downloads... This may take a while.")

for model in models:
    print(f"\nPulling {model}...")
    try:
        # stream=True produces a generator, we consume it to show progress or just let it finish
        current_digest = ''
        for progress in ollama.pull(model, stream=True):
            # rudimentary progress print
            if 'total' in progress and 'completed' in progress:
                # Avoid division by zero
                if progress['total'] > 0:
                    percent = int((progress['completed'] / progress['total']) * 100)
                    if percent % 10 == 0:
                        print(f".", end="", flush=True)
            elif 'status' in progress:
                # print(progress['status'])
                pass
        print(f"\n{model} installed successfully.")
    except Exception as e:
        print(f"\nError pulling {model}: {e}")

print("\nAll operations complete.")
