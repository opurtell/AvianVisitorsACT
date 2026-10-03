# Display kiosk — Surface 3

The wall display is a **Microsoft Surface 3** (non-Pro, x86_64, UEFI), always
on AC, showing the BirdNET-Pi collage from the Pi 4B at `http://birdnet.local/`.

Windows has been replaced with **Debian 13** (minimal, no desktop) running
**cage** (a Wayland kiosk compositor) and **Chromium** in kiosk mode.

```
power on → getty autologin (kiosk, tty1) → .bash_profile loop
         → cage → wlr-randr rotates to portrait → chromium --kiosk http://birdnet.local/
```

---

## Setup

### 1. Firmware / UEFI — do this in Windows, before wiping

1. **Update the firmware via Windows Update.** Battery Limit needs UEFI
   **≥ 1.51116.218.0**.
2. **Enter UEFI** (hold **Vol Up + Power**) and set:
   - **Battery Limit Mode: ON.** Caps charge at 50% for always-on-AC use. It is
     set in firmware, so it holds whatever OS is installed.
   - **Secure Boot: OFF.**
   - **Boot order: USB first.**

> Once Windows is gone, the firmware can no longer be updated. Do step 1 first.

### 2. Install Debian

1. Flash the Debian 13 amd64 netinst ISO to a USB stick (done from macOS with
   `dd`).
2. Boot from USB: hold **Vol Down + Power**.
3. Run the text installer:

   | Prompt | Answer |
   |---|---|
   | "No Ethernet card" | **No**. The Surface 3 has no Ethernet. Wi-Fi was then detected and connected first try on the 2.4 GHz network. |
   | Hostname | `avian-kiosk` |
   | Root password | **blank**, so the admin user gets sudo |
   | User | an admin user (not the kiosk user) |
   | Partitioning | guided, whole disk |
   | Software selection | **SSH server** + **standard system utilities** only, no desktop |

### 3. Post-install packages and the kiosk user

```bash
sudo apt update && sudo apt full-upgrade
sudo apt install avahi-daemon libnss-mdns iw nano cage chromium wlr-randr libinput-tools
```

`avahi-daemon` and `libnss-mdns` make `avian-kiosk.local` reachable over SSH
and let the Surface resolve `birdnet.local`. Verify:

```bash
getent hosts birdnet.local
```

Create an unprivileged user `kiosk` (**no sudo**). It runs the display and
nothing else.

### 4. Auto-login on tty1

```bash
sudo systemctl edit getty@tty1
```

```ini
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin kiosk --noclear %I $TERM
```

### 5. Launch script — `/home/kiosk/.bash_profile`

```bash
if [ "$(tty)" = "/dev/tty1" ]; then
  while true; do
    cage -- sh -c '
      OUT=$(wlr-randr | head -n1 | cut -d" " -f1)
      wlr-randr --output "$OUT" --transform 90
      exec chromium --kiosk --ozone-platform=wayland \
        --noerrdialogs --disable-infobars --incognito \
        --disable-features=Translate \
        --check-for-update-interval=31536000 \
        http://birdnet.local/
    '
    sleep 3
  done
fi
```

- The `while` loop relaunches Chromium if it crashes.
- **Portrait rotation.** Current cage has **removed** the old `-r` flag.
  Rotation is done with `wlr-randr` inside the cage session, with the output
  name detected automatically. If the picture is upside down, use
  `--transform 270` instead of `90`.

### 6. Touch rotation — `/etc/udev/rules.d/99-touch-rotate.rules`

```
ENV{ID_INPUT_TOUCHSCREEN}=="1", ENV{LIBINPUT_CALIBRATION_MATRIX}="0 -1 1 1 0 0"
```

Rotating the output does not rotate touch input. This matrix pairs with
`--transform 90`.

> **Gotcha:** the rule only took effect after a **full reboot**.
> `udevadm control --reload` / `udevadm trigger` plus a kiosk restart was not
> enough.

### 7. Never sleep

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

`/etc/systemd/logind.conf`:

```ini
HandlePowerKey=ignore
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
```

### 8. Nightly reboot

Applied, in root's crontab (`sudo crontab -e`):

```
0 4 * * * /sbin/reboot
```

---

## Maintenance

All over SSH: `ssh <admin>@avian-kiosk.local`.

| Task | Command |
|---|---|
| Restart the kiosk | `sudo systemctl restart getty@tty1` |
| Change the URL | `sudo -u kiosk nano /home/kiosk/.bash_profile`, then restart the kiosk |
| Update | `sudo apt update && sudo apt full-upgrade -y` |
| Battery check (should sit ~50%) | `cat /sys/class/power_supply/*/capacity` |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Picture upside down | Use `--transform 270` in `.bash_profile` instead of `90`. Change the touch matrix to match. |
| Touch mirrored or rotated wrong | Check the `Calibration` line in `sudo libinput list-devices`, and watch input with `sudo libinput debug-events`. Other matrices to try: `0 1 0 -1 0 1`, `0 1 0 1 0 0`, `0 -1 1 -1 0 1`. **Reboot** after each change. |
| Touch rule edited but nothing changed | Reboot fully. Reloading udev is not enough (§6). |
| Blank page or "can't reach" | Check `getent hosts birdnet.local` on the Surface, and that the Pi is up. |
| Wi-Fi dropouts | Turn off Wi-Fi power save (Marvell chip). **Not applied, since dropouts haven't happened so far.** In `/etc/network/interfaces`, add this under the `wlp…` block: `post-up /usr/sbin/iw dev $IFACE set power_save off` |
