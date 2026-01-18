
import sys
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class RestartHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback
        self.last_restart_time = time.time()

    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            # Debounce rapid changes (e.g. auto-save)
            if time.time() - self.last_restart_time > 1:
                self.last_restart_time = time.time()
                print(f"\n[Auto-Reloader] Change detected in {event.src_path}. Restarting...")
                self.callback()

def run_bot():
    return subprocess.Popen([sys.executable, "-m", "bot"])

def main():
    print("[Auto-Reloader] Starting bot with auto-reload...")
    process = run_bot()
    
    def restart_bot():
        nonlocal process
        # Kill the current process hierarchy
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Start new process
        process = run_bot()

    event_handler = RestartHandler(restart_bot)
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    observer.join()

if __name__ == "__main__":
    main()
