import time, csv
from pathlib import Path
from datetime import datetime

LOG_FILE = Path(__file__).resolve().parent / "experiment_log.csv"

def log_experiment(point: str, key: str, note: str = ""):
    ts_ms = int(time.time() * 1000)
    ts_readable = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # có mili giây
    is_new = not LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["point", "key", "timestamp_ms", "timestamp_readable", "note"])
        w.writerow([point, key, ts_ms, ts_readable, note])