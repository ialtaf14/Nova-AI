import ollama
import time
import sys

models = ["llama3.1", "mistral", "phi3:mini", "deepseek-coder"]

print("Starting Download (with Progress Monitor)...", flush=True)

for model in models:
    print(f"\nTarget: {model}", flush=True)
    success = False
    for attempt in range(3):
        try:
            print(f"  Attempt {attempt+1}...", flush=True)
            # stream=True is key for progress
            current_digest = ''
            for progress in ollama.pull(model, stream=True):
                if 'total' in progress and 'completed' in progress:
                    total = progress['total']
                    completed = progress['completed']
                    if total > 0:
                        percent = int((completed / total) * 100)
                        # Write to file for external monitoring
                        with open("download_status.txt", "w") as f:
                            f.write(f"Downloading {model}: {percent}%")
                        
                        # Print progress every 5%
                        if percent % 5 == 0:
                            print(f"\r    Downloading {model}: {percent}%      ", end="", flush=True)
                elif 'status' in progress:
                    # status messages mostly generic
                    pass
            
            print(f"\n    [OK] Installed {model}!", flush=True)
            success = True
            break
        except Exception as e:
            print(f"\n    [X] Error: {e}", flush=True)
            time.sleep(2)
    
    if not success:
        print(f"\n    [!] Failed to install {model}.", flush=True)

print("\nAll Downloads Finished.", flush=True)
