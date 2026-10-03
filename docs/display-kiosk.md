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
   | Hostname | `bird-display` |
   | Root password | **blank**, so the admin user gets sudo |
   | User | an admin user (not the kiosk user) |
   | Partitioning | guided, whole disk |
   | Software selection | **SSH server** + **standard system utilities** only, no desktop |

### 3. Post-install packages and the kiosk user

```bash
sudo apt update && sudo apt full-upgrade
sudo apt install avahi-daemon libnss-mdns iw nano cage chromium wlr-randr libinput-tools
```

`avahi-daemon` and `libnss-mdns` make `bird-display.local` reachable over SSH
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
      wlr-randr --output "$OUT" --transform "$(cat /var/lib/kiosk-rotation 2>/dev/null || echo 90)"
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
  name detected automatically. The angle comes from `/var/lib/kiosk-rotation`
  (default `90`), which the rotation hotkeys (§11) write.

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

### 9. Brightness follows the sun

The Surface 3's ambient light sensor does not work under Linux. Plain sysfs reads
always return 0, buffered reads return no samples, and the kernel logs
`hid-sensor-hub: No report with id 0xffffffff found`. The backlight therefore
follows the sun's elevation at the site, not the room: **90%** when the sun is
above +6°, **10%** below −6° (civil twilight), and a linear fade in between. The
fade takes about an hour (05:14→06:13 and 17:34→18:33 in early October).

Source: [`kiosk/`](kiosk/). Install (applied 2026-10-03):

```bash
sudo install -m 755 kiosk-brightness.py /usr/local/bin/kiosk-brightness
sudo install -m 644 kiosk-brightness.conf /etc/default/kiosk-brightness
sudo install -m 644 kiosk-brightness.service kiosk-brightness.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now kiosk-brightness.timer
```

The timer runs every 2 minutes and 20 s after boot. That boot run overrides the
level `systemd-backlight` restores, which may be a night value saved before the
04:00 reboot. Levels and the fade band are in `/etc/default/kiosk-brightness`
and take effect on the next run, with no restart needed.

### 10. Speakers

Out of the box the speakers are silent. The audio DSP needs firmware from
`non-free-firmware` (`intel/fw_sst_22a8.bin`; without it, `dmesg` shows
`intel_sst_acpi … FW download fail -2`). There is no PipeWire or PulseAudio, so
the UCM speaker routing has to be applied by hand once, then saved:

```bash
sudo apt install firmware-intel-sound alsa-utils
sudo reboot                                    # the DSP loads firmware only at boot
sudo alsaucm -c chtrt5645 set _verb HiFi set _enadev Speaker
sudo amixer -c 0 sset Speaker 39 unmute        # max, +12 dB (default 31 = 0 dB)
sudo amixer -c 0 sset 'Speaker ClassD' 6       # amp gain 0-7 (default 4)
sudo alsactl store 0                           # restored at boot by 90-alsa-restore.rules
```

Applied 2026-10-03. Chromium plays through ALSA's default device (card 0), and
logind's seat ACL gives the `kiosk` user access to `/dev/snd` without the
`audio` group. Test with `speaker-test -D plughw:0,0 -c 2 -t pink -l 1`.

**Volume rocker.** No desktop listens for the buttons (`gpio-keys`, KEY_VOLUMEUP/DOWN),
so `triggerhappy` runs [`kiosk-volume`](kiosk/kiosk-volume) on each press or repeat. It
steps `Speaker` by 2 of 39 (3 dB) and runs `alsactl store` so the level survives
reboots. The packaged unit drops to `nobody`, which cannot set the mixer, so a
drop-in runs it as root:

```bash
sudo apt install triggerhappy
sudo install -m 755 kiosk-volume /usr/local/bin/kiosk-volume
sudo install -m 644 volume.conf /etc/triggerhappy/triggers.d/volume.conf
sudo install -D -m 644 triggerhappy-root.conf /etc/systemd/system/triggerhappy.service.d/root.conf
sudo systemctl daemon-reload && sudo systemctl enable --now triggerhappy
```

### 11. Rotation hotkeys

The orientation sensors on the Surface 3 are as dead as the light sensor (§9):
`accel_3d` always reads `0 0 -1000`, `dev_rotation` stays at the identity
quaternion, and buffered reads return nothing. Auto-rotate is therefore not possible.
Instead, Windows-style hotkeys on any plugged-in keyboard rotate the screen:

| Keys | Action |
|---|---|
| Ctrl+Alt+→ | rotate 90° clockwise |
| Ctrl+Alt+← | rotate 90° anticlockwise |
| Ctrl+Alt+↑ | back to default portrait (`90`) |

[`kiosk-rotate`](kiosk/kiosk-rotate) changes the live cage output with `wlr-randr`
(running as `kiosk` in its Wayland session) and saves the angle to
`/var/lib/kiosk-rotation`, so the 04:00 reboot keeps it. Triggerhappy's udev rule
picks up keyboards plugged in after boot. Install (applied 2026-10-03):

```bash
sudo install -m 755 kiosk-rotate /usr/local/bin/kiosk-rotate
sudo install -m 644 rotate.conf /etc/triggerhappy/triggers.d/rotate.conf
echo 90 | sudo tee /var/lib/kiosk-rotation
sudo systemctl restart triggerhappy
```

---

## Maintenance

All over SSH: `ssh <admin>@bird-display.local`. If mDNS is not answering, the
router also names it `bird-display.nbn` (192.168.1.241 at the time of writing).
Connect by IP or `.local` rather than `.nbn`: the host key is saved under those names.

| Task | Command |
|---|---|
| Restart the kiosk | `sudo systemctl restart getty@tty1` |
| Change the URL | `sudo -u kiosk nano /home/kiosk/.bash_profile`, then restart the kiosk |
| Update | `sudo apt update && sudo apt full-upgrade -y` |
| Battery check (should sit ~50%) | `cat /sys/class/power_supply/*/capacity` |
| Change speaker volume | Volume rocker on the side. Range: `Speaker` 0-39; amp gain: `sudo amixer -c 0 sset 'Speaker ClassD' 0-7 && sudo alsactl store 0` |
| Change brightness levels | `sudo nano /etc/default/kiosk-brightness` (`DAY`, `NIGHT`, `ELEV_LOW`/`ELEV_HIGH`) |
| See what brightness it would set now | `kiosk-brightness --dry-run`; history: `journalctl -u kiosk-brightness -n 20` |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Picture upside down or sideways | Ctrl+Alt+arrows (§11), or over SSH: `sudo kiosk-rotate cw` / `ccw` / `reset`. |
| Touch mirrored or rotated wrong | Check the `Calibration` line in `sudo libinput list-devices`, and watch input with `sudo libinput debug-events`. Other matrices to try: `0 1 0 -1 0 1`, `0 1 0 1 0 0`, `0 -1 1 -1 0 1`. **Reboot** after each change. |
| Touch rule edited but nothing changed | Reboot fully. Reloading udev is not enough (§6). |
| Blank page or "can't reach" | Check `getent hosts birdnet.local` on the Surface, and that the Pi is up. |
| Wi-Fi dropouts | Turn off Wi-Fi power save (Marvell chip). **Applied 2026-10-03** after the kiosk dropped off the network (no ARP reply, needed a power cycle). Under `iface wlp1s0` in `/etc/network/interfaces` (root-only, it holds the PSK): `post-up /usr/sbin/iw dev $IFACE set power_save off`. Check with `/usr/sbin/iw dev wlp1s0 get power_save` → `off`. |
