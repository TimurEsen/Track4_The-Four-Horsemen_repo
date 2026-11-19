HackEdge Track 4 - live demo: current-only model running on the SK-AM62

Members: John Barton, Ayden Kurtz, Timur Esenaliev, Krish Bharal

ON THE TI BOARD (needs python3 only, nothing to install)
1. Put current_model.eim and board_predict.py in the same folder on the board.
2. Run:  chmod +x current_model.eim
3. Test without the laptop, using the clips in test_clips (one per condition):
       python3 board_predict.py --replay test_clips/no_load.no_load_2v_03.csv
   Most lines should say NO_LOAD. Try the other four clips the same way.
4. Live mode:  python3 board_predict.py
   It waits for the laptop on port 5005. Get the board's IP address with:  ip addr

ON THE LAPTOP (AD2 plugged in; WaveForms installed but CLOSED)
1. Check the AD2 reading:  python laptop_stream.py --test
   It prints the mean current every second (no load at 2 V is about 55 mA).
2. Stream to the board:    python laptop_stream.py <board IP>
   The board prints one prediction per second. Ignore the first one.

Wiring is the same as for the recordings: scope channel 2 across the 5-ohm shunt.
The laptop and board must be on the same network (or joined with an Ethernet cable).
If the live link fails, use --replay on the board as the fallback demo.

Dependencies

**Windows Laptop:**
- Python 3.8+
- [Digilent WaveForms SDK](https://digilent.com/reference/software/waveforms/waveforms-3/start) (for Analog Discovery 2)
- Python packages:
  ```bash
  pip install pyserial numpy
  ```

**TI SK-AM62 Board (Linux):**
- Python 3
- Edge Impulse Linux SDK:
  ```bash
  pip3 install edge_impulse_linux
  ```

## Installation & Setup

1. Clone this repository on your Windows laptop:
   ```bash
   git clone <YOUR_GITHUB_REPO_URL>
   cd <YOUR_REPO_FOLDER>
   ```
2. Copy `current_model.eim`, `board_predict.py`, `serial_predict.py`, and the `.csv` files to `/root/demo/` on the TI SK-AM62.
3. Make the model executable on the board:
   ```bash
   cd /root/demo
   chmod +x current_model.eim
   ```

## How to Run

> **Important:** Close **Digilent WaveForms** and **PuTTY** before running the laptop scripts to avoid USB driver crashes or COM port lock errors.

### 1. Live USB Serial Mode (No Ethernet Required)
Make sure the board is at the `am62xx-evm login:` prompt, check your lowest COM port in Device Manager (e.g., `COM7`), and run on Windows:
```bash
python laptop_serial.py COM7 --board-dir /root/demo
```

### 2. Live Ethernet Mode
Start the server on the TI SK-AM62:
```bash
cd /root/demo
python3 board_predict.py
```
Then stream from Windows (replace with your board's IP):
```bash
python laptop_stream.py 192.168.10.2
```

### 3. Offline Replay Mode (Board Only)
Run saved CSV data directly on the TI SK-AM62:
```bash
cd /root/demo
python3 board_predict.py --replay no_load.no_load_2v_03.csv
```

## Safe Shutdown
Press `Ctrl + C` to stop the script and run `poweroff` on the TI SK-AM62 before unplugging power.