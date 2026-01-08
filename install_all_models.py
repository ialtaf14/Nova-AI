import ollama
import time
import sys

# Prioritize deepseek-coder as requested
models = [
    "deepseek-coder",
    "mistral",
    "phi3:mini",
    "qwen3:8b",
    "llava"
]

print("Starting Batch Model Installation...", flush=True)

for model in models:
    print(f"\nTarget: {model}", flush=True)
    success = False
    for attempt in range(3):
        try:
            if attempt > 0:
                print(f"  Retry {attempt+1}...", flush=True)
            
            # stream=True is key for progress
            for progress in ollama.pull(model, stream=True):
                if 'total' in progress and 'completed' in progress:
                    total = progress['total']
                    completed = progress['completed']
                    if total > 0:
                        percent = int((completed / total) * 100)
                        # Write to file
                        with open("download_status.txt", "w") as f:
                            f.write(f"Downloading {model}: {percent}%")
                        
                        if percent % 10 == 0:
                             sys.stdout.write(f"\r  Downloading {model}: {percent}%")
                             sys.stdout.flush()
            
            print(f"\n  [OK] Installed {model}!", flush=True)
            success = True
            break
        except Exception as e:
            print(f"\n  [X] Error: {e}", flush=True)
            time.sleep(2)
    
    if not success:
        print(f"\n  [!] Failed to install {model}.", flush=True)

print("\nAll Downloads Finished.", flush=True)
with open("download_status.txt", "w") as f:
    f.write("All Finished")
