"""Passively listen to a HID receiver's vendor collections.

Prints the report descriptor of every collection it can open and then every input report
the receiver sends for a while. Nothing is ever written to the device. Keyboard and mouse
collections are skipped, so keystrokes are never read.

Usage: python tools/hid_listen.py [VID] [PID] [seconds]
       python tools/hid_listen.py 1234 abcd 60
"""
import sys
import time

import hid

SKIP = {(0x0001, 0x0006), (0x0001, 0x0002)}


def hexs(data):
    return " ".join(f"{b:02x}" for b in data)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    vid, pid = int(sys.argv[1], 16), int(sys.argv[2], 16)
    seconds = int(sys.argv[3]) if len(sys.argv) > 3 else 60

    opened = []
    for d in hid.enumerate(vid, pid):
        usage = (d["usage_page"], d["usage"])
        label = f"interface={d['interface_number']} usage={usage[0]:04x}:{usage[1]:04x}"
        if usage in SKIP:
            print(f"[skipped] {label} (keyboard/mouse input is not read)")
            continue
        try:
            dev = hid.device()
            dev.open_path(d["path"])
            dev.set_nonblocking(True)
        except (OSError, IOError) as e:
            print(f"[cannot open] {label}: {e}")
            continue
        print(f"[opened] {label}")
        try:
            descriptor = dev.get_report_descriptor()
            print(f"  report descriptor ({len(descriptor)} bytes): {hexs(descriptor)}")
        except Exception as e:
            print(f"  report descriptor unavailable: {e}")
        opened.append((label, dev))

    if not opened:
        print("Nothing to listen to. Is the device connected?")
        return

    print(f"\nListening for {seconds} s. Plug/unplug the charging cable and switch the "
          f"device off and on meanwhile.\n")
    start = time.time()
    while time.time() - start < seconds:
        for label, dev in opened:
            data = dev.read(64)
            if data:
                print(f"{time.time() - start:6.1f}s  {label}  {hexs(data)}")
        time.sleep(0.01)
    for _, dev in opened:
        dev.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
