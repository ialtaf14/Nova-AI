import ollama
try:
    models = ollama.list()
    # print(models) # Debug if needed
    print("Installed Models:")
    if 'models' in models:
        for m in models['models']:
            # The key is likely 'model' or 'name' depending on version
            name = m.get('name') or m.get('model') or "Unknown"
            print(f" - {name}")
except Exception as e:
    print(f"Error listing models: {e}")
