import time
from datetime import datetime

def current_time():
    return int(time.time() * 1000)

def current_readable_time():
    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")

    return current_time
