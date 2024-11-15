import multiprocessing

bind = "0.0.0.0:5000"
workers = multiprocessing.cpu_count() * 2 + 1
timeout = 300  # 5 minutes for large video processing
max_requests = 1000
max_requests_jitter = 50