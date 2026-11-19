#!/usr/bin/env python3
"""Run current_model.eim on the TI board. Standard library only (no pip installs needed).

Live mode (laptop streams current from the AD2):   python3 board_predict.py
Replay mode (no laptop, uses a saved clip):        python3 board_predict.py --replay no_load.no_load_2v_03.csv
"""
import argparse, csv, json, os, socket, subprocess, sys, time

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="./current_model.eim")
ap.add_argument("--port", type=int, default=5005)
ap.add_argument("--replay", help="CSV with a current_a column at 1 kHz (e.g. one of the teacher_clips files)")
args = ap.parse_args()

# start the model process and connect to it (same protocol the Edge Impulse Python SDK uses)
sock_path = "/tmp/current_model.sock"
if os.path.exists(sock_path):
    os.remove(sock_path)
proc = subprocess.Popen([os.path.abspath(args.model), sock_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
for _ in range(600):
    if os.path.exists(sock_path):
        break
    time.sleep(0.1)
else:
    sys.exit("Model did not start. Did you run: chmod +x current_model.eim ?")
model = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
model.connect(sock_path)
_msg_id = 0

def ask(msg):
    global _msg_id
    _msg_id += 1
    msg["id"] = _msg_id
    model.sendall(json.dumps(msg).encode())
    data = b""
    while True:
        chunk = model.recv(65536)
        if not chunk:
            sys.exit("Model process stopped")
        if chunk[-1] == 0:
            return json.loads(data + chunk[:-1])
        data += chunk

info = ask({"hello": 1})["model_parameters"]
N = info["input_features_count"]          # 1000 = 1 s of current at 1 kHz
print(f"Model ready: labels {info['labels']}, {N} samples per prediction")

def predict(window):
    t0 = time.time()
    res = ask({"classify": [float(v) for v in window]})["result"]["classification"]
    best = max(res, key=res.get)
    ms = (time.time() - t0) * 1000
    print(f"{best.upper():9s} {res[best]*100:5.1f}%   " + "  ".join(f"{k}:{v:.2f}" for k, v in res.items()) + f"   ({ms:.0f} ms)")
    return best

try:
    if args.replay:
        with open(args.replay) as fh:
            current = [float(row["current_a"]) for row in csv.DictReader(fh)]
        votes = {}
        for i in range(0, len(current) - N + 1, N):       # one prediction per second of data
            label = predict(current[i:i + N])
            votes[label] = votes.get(label, 0) + 1
            time.sleep(0.2)
        print("Summary:", votes)
    else:
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", args.port))
        srv.listen(1)
        print(f"Waiting for the laptop on port {args.port} ...")
        conn, addr = srv.accept()
        print("Laptop connected from", addr[0])
        for line in conn.makefile():
            vals = line.strip().split(",")
            if len(vals) == N:
                predict(vals)
finally:
    proc.kill()
