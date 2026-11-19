#!/usr/bin/env python3
"""Live demo over the board's USB serial cable (no Wi-Fi or Ethernet needed).

The AD2 powers the motor from V+ and measures its current on scope channel 2 (across the 5-ohm shunt).
This script sends each second of current (1000 samples at 1 kHz) down the serial cable to the SK-AM62.
The board runs current_model.eim on it and sends back its prediction, which is printed here.

Before running:
  1. In PuTTY, log in to the board as root (you should see the root@... prompt). Then CLOSE PuTTY.
  2. Close the WaveForms app. Install pyserial once:  pip install pyserial

  python laptop_serial.py COM9                       # motor at 3 V, model in ~/AM62_demo on the board
  python laptop_serial.py COM9 --board-dir ~/demo    # if current_model.eim is in ~/demo
  python laptop_serial.py COM9 --volts 2
  python laptop_serial.py COM9 --replay no_load.no_load_2v_03.csv   # no AD2: stream a saved clip instead
Ctrl+C stops it, turns the motor off and returns the board to its normal prompt.
"""
import argparse, csv, sys, time

try:
    import serial
except ImportError:
    sys.exit("pyserial is missing. Run:  pip install pyserial")

# ---------------- the small program that runs on the board (uploaded automatically) ----------------
BOARD_SCRIPT = r'''
import json, os, socket, subprocess, sys, termios, time
MODEL = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "current_model.eim")
IGNORE = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else set()
SCALE = 100000.0
if not os.path.exists(MODEL):
    print("ERROR model not found: " + MODEL, flush=True)
    sys.exit(1)
sock_path = "/tmp/current_model_serial.sock"
if os.path.exists(sock_path):
    os.remove(sock_path)
proc = subprocess.Popen([MODEL, sock_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
for _ in range(600):
    if os.path.exists(sock_path):
        break
    time.sleep(0.1)
else:
    print("ERROR model did not start. Run: chmod +x current_model.eim", flush=True)
    sys.exit(1)
model = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
model.connect(sock_path)
mid = [0]
def ask(msg):
    mid[0] += 1
    msg["id"] = mid[0]
    model.sendall(json.dumps(msg).encode())
    data = b""
    while True:
        chunk = model.recv(65536)
        if not chunk:
            raise SystemExit("ERROR model stopped")
        if chunk[-1] == 0:
            return json.loads(data + chunk[:-1])
        data += chunk
N = ask({"hello": 1})["model_parameters"]["input_features_count"]
hist = []
fd = sys.stdin.fileno()
old = termios.tcgetattr(fd)
new = termios.tcgetattr(fd)
new[0] &= ~(termios.IXON | termios.IXOFF | termios.ICRNL | termios.INLCR | termios.IGNCR)
new[3] &= ~(termios.ICANON | termios.ECHO | termios.ECHOE | termios.ECHOK | termios.ECHONL)
new[6][termios.VMIN] = 1
new[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, new)
try:
    print("READY %d" % N, flush=True)
    buf = b""
    while True:
        chunk = os.read(fd, 8192)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line == b"QUIT":
                raise SystemExit
            parts = line.split(b",")
            if len(parts) != N:
                print("SKIP got %d values" % len(parts), flush=True)
                continue
            try:
                vals = [int(p) / SCALE for p in parts]
            except ValueError:
                print("SKIP bad data", flush=True)
                continue
            t0 = time.time()
            res = ask({"classify": vals})["result"]["classification"]
            keep = {k: v for k, v in res.items() if k not in IGNORE}
            tot = sum(keep.values()) or 1.0
            best = max(keep, key=keep.get)
            ms = int((time.time() - t0) * 1000)
            hist = (hist + [best])[-3:]
            steady = max(set(hist), key=lambda k: (hist.count(k), k == hist[-1]))
            print("PRED %s %.3f %d %s %s" % (best, keep[best] / tot, ms, steady, " ".join("%s:%.2f" % (k, v / tot) for k, v in keep.items())), flush=True)
finally:
    termios.tcsetattr(fd, termios.TCSANOW, old)
    proc.kill()
'''

ap = argparse.ArgumentParser()
ap.add_argument("port", help="the board's serial port, e.g. COM9")
ap.add_argument("--board-dir", default="~/AM62_demo", help="folder on the board that holds current_model.eim")
ap.add_argument("--volts", type=float, default=3.0, help="motor voltage from the AD2's V+ (trained at 2, 3 and 4 V)")
ap.add_argument("--no-power", action="store_true", help="don't power the motor from the AD2")
ap.add_argument("--replay", help="stream a saved clip (CSV with a current_a column) instead of the AD2")
ap.add_argument("--ignore-friction", action="store_true", help="the board never answers 'friction' (picks the best of the other four)")
args = ap.parse_args()
if not args.replay and not args.no_power and not 1.0 <= args.volts <= 4.0:
    sys.exit("Use --volts between 1 and 4")

N, SCALE, HALF = 1000, 100000, 5000

try:
    ser = serial.Serial(args.port, 115200, timeout=0.05)
except serial.SerialException as e:
    sys.exit(f"Could not open {args.port} (close PuTTY first): {e}")


def send(text, pause=0.0):
    ser.write(text.encode())
    if pause:
        time.sleep(pause)


def read_text(wait=0.3):
    time.sleep(wait)
    return ser.read(ser.in_waiting or 1).decode(errors="replace") if ser.in_waiting else ""


def wait_for(token, timeout):
    """Read from the board until `token` shows up; return everything read."""
    text, end = "", time.time() + timeout
    while time.time() < end:
        chunk = ser.read(4096).decode(errors="replace")
        if chunk:
            text += chunk
            if token in text:
                return text
    return text


# ---------------- 1. get a clean shell prompt on the board ----------------
print(f"Connecting to the board on {args.port} ...")
send("\x03", 0.3)
send("\r", 0.8)
text = read_text(0.2) + wait_for("#", 2)
if "login:" in text:
    send("root\r", 2.0)
    text = read_text(0.2)
    if "assword" in text:
        send("\r", 2.0)
send("set +H\r", 0.3)
send(f"cd {args.board_dir} && chmod +x current_model.eim && echo DIR_$((1+1))OK\r")
text = wait_for("DIR_2OK", 5)
if "DIR_2OK" not in text:
    print(text[-600:])
    sys.exit(f"Could not find current_model.eim in {args.board_dir} on the board. Use --board-dir to point at it.")

# ---------------- 2. upload the predictor to the board and start it ----------------
print("Uploading the predictor to the board ...")
send("cat > serial_predict.py << 'EOF'\r", 0.2)
for line in BOARD_SCRIPT.strip("\n").split("\n"):
    send(line + "\r", 0.01)
send("EOF\r", 0.3)
send("echo UP_$((2+3))OK\r")
if "UP_5OK" not in wait_for("UP_5OK", 10):
    sys.exit("Upload to the board failed. Try again.")
ser.reset_input_buffer()
print("Starting the model on the board ...")
send("python3 serial_predict.py current_model.eim" + (" friction" if args.ignore_friction else "") + "\r")
text = wait_for("READY", 60)
if "READY" not in text:
    print(text[-800:])
    sys.exit("The board's predictor did not start (see the board's output above).")
print("Board ready: it runs the model on every second of current it receives.\n")

# ---------------- 3. the data source: the AD2, or a saved clip ----------------
dwf = hdwf = None
powered = False
if args.replay:
    with open(args.replay) as fh:
        clip = [float(r["current_a"]) for r in csv.DictReader(fh)]
    windows = [clip[i:i + N] for i in range(0, len(clip) - N + 1, N)]
    print(f"Replaying {args.replay}: {len(windows)} seconds of recorded current\n")
else:
    from ctypes import byref, c_byte, c_double, c_int, cdll, create_string_buffer
    if sys.platform.startswith("win"):
        dwf = cdll.dwf
    elif sys.platform.startswith("darwin"):
        dwf = cdll.LoadLibrary("/Library/Frameworks/dwf.framework/dwf")
    else:
        dwf = cdll.LoadLibrary("libdwf.so")
    CH, VPLUS, VMINUS, ENABLE, VOLTAGE = 1, 0, 1, 0, 1   # scope ch 2; supplies: ch 0 = V+, 1 = V-; node 0 = enable, 1 = voltage
    hdwf = c_int()
    dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf))
    if hdwf.value == 0:
        err = create_string_buffer(512)
        dwf.FDwfGetLastErrorMsg(err)
        send("QUIT\n", 0.5)
        sys.exit("Could not open the AD2 (is WaveForms still open?): " + err.value.decode())

    def motor_power(on):
        dwf.FDwfAnalogIOChannelNodeSet(hdwf, c_int(VMINUS), c_int(ENABLE), c_double(0))
        dwf.FDwfAnalogIOChannelNodeSet(hdwf, c_int(VPLUS), c_int(VOLTAGE), c_double(args.volts))
        dwf.FDwfAnalogIOChannelNodeSet(hdwf, c_int(VPLUS), c_int(ENABLE), c_double(1 if on else 0))
        dwf.FDwfAnalogIOEnableSet(hdwf, c_int(1 if on else 0))
        dwf.FDwfAnalogIOConfigure(hdwf)

    def supply_still_on():
        on = c_int()
        dwf.FDwfAnalogIOStatus(hdwf)
        dwf.FDwfAnalogIOEnableStatus(hdwf, byref(on))
        return bool(on.value)

    dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(CH), c_int(1))
    dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(CH), c_double(5.0))
    dwf.FDwfAnalogInChannelOffsetSet(hdwf, c_int(CH), c_double(0.0))
    dwf.FDwfAnalogInChannelFilterSet(hdwf, c_int(CH), c_int(1))      # Average, same as the training recordings
    dwf.FDwfAnalogInFrequencySet(hdwf, c_double(10000.0))            # 10 kHz like the WaveForms recordings
    dwf.FDwfAnalogInBufferSizeSet(hdwf, c_int(HALF))                  # 0.5 s per capture (fits the AD2 buffer)
    dwf.FDwfAnalogInConfigure(hdwf, c_int(1), c_int(0))
    if not args.no_power:
        motor_power(True)
        powered = True
        print(f"Motor power ON at {args.volts:g} V from the AD2's V+")
    time.sleep(2)
    buf, sts = (c_double * HALF)(), c_byte()


def next_window():
    if args.replay:
        if not windows:
            raise KeyboardInterrupt
        time.sleep(1.0)                                   # keep real-time pace
        return windows.pop(0)
    while True:
        raw = []
        for _ in range(2):                                # two 0.5 s captures at 10 kHz = 1 s
            dwf.FDwfAnalogInConfigure(hdwf, c_int(0), c_int(1))
            while True:
                dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(sts))
                if sts.value == 2:
                    break
                time.sleep(0.005)
            dwf.FDwfAnalogInStatusData(hdwf, c_int(CH), buf, HALF)
            raw.extend(buf)
        if powered and not supply_still_on():
            print("!! The AD2 switched the motor supply off (too much current, e.g. stall). Turning it back on...")
            motor_power(False)
            time.sleep(0.5)
            motor_power(True)
            time.sleep(1.0)
            continue
        # average each 10 samples (1 ms) -> 1000 samples at 1 kHz, exactly how the training clips were made
        return [sum(raw[i:i + 10]) / 10 / 5.0 for i in range(0, 10 * N, 10)]   # 5-ohm shunt -> amps


pending = ""


def show_board_output():
    global pending
    if not ser.in_waiting:
        return
    pending += ser.read(ser.in_waiting).decode(errors="replace")
    while "\n" in pending:
        line, pending = pending.split("\n", 1)
        line = line.strip()
        if line.startswith("PRED "):
            _, label, conf, ms, steady, probs = (line.split(" ", 5) + [""] * 6)[:6]
            print(f"  [SK-AM62] {steady.upper():9s} (this second: {label} {float(conf) * 100:.0f}%)   {probs}")
        elif line:
            print("  [board]", line)


print("Streaming... press Ctrl+C to stop (this also turns the motor off)")
try:
    while True:
        amps = next_window()
        print(f"sent 1 s of current, mean {sum(amps) / len(amps) * 1000:6.1f} mA")
        ser.write((",".join(str(int(round(a * SCALE))) for a in amps) + "\n").encode())
        show_board_output()
except KeyboardInterrupt:
    print("\nStopping")
finally:
    time.sleep(0.8)
    show_board_output()
    try:
        ser.write(b"QUIT\n")
        time.sleep(0.5)
    except Exception:
        pass
    if powered:
        motor_power(False)
        print("Motor power OFF")
    if dwf is not None:
        dwf.FDwfDeviceCloseAll()
    ser.close()
