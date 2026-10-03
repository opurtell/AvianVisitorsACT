#!/usr/bin/env python3
"""Set the kiosk backlight from the sun's elevation at the deployment site.

Day level above +ELEV_HIGH degrees, night level below ELEV_LOW (civil
twilight), linear fade in between. Run by kiosk-brightness.timer every
2 minutes. The Surface 3 ambient light sensor does not report under Linux,
so this follows the sun rather than the room.
"""
import math
import os
import sys
from datetime import datetime, timezone

CONF = '/etc/default/kiosk-brightness'


def load_conf():
    c = {'LAT': -35.28, 'LON': 149.13, 'DAY': 90, 'NIGHT': 10,
         'ELEV_LOW': -6.0, 'ELEV_HIGH': 6.0,
         'BACKLIGHT': '/sys/class/backlight/intel_backlight'}
    if os.path.exists(CONF):
        for line in open(CONF):
            line = line.split('#', 1)[0].strip()
            if '=' in line:
                k, v = (s.strip().strip('"') for s in line.split('=', 1))
                if k in c:
                    c[k] = v if k == 'BACKLIGHT' else float(v)
    return c


def sun_elevation(lat, lon, now):
    """NOAA approximation, good to ~0.5 degrees - plenty for a fade."""
    doy = now.timetuple().tm_yday
    hour = now.hour + now.minute / 60 + now.second / 3600
    g = 2 * math.pi / 365 * (doy - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    tst = hour * 60 + eqtime + 4 * lon          # true solar time, minutes
    ha = math.radians(tst / 4 - 180)            # hour angle
    la = math.radians(lat)
    cosz = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    return 90 - math.degrees(math.acos(max(-1.0, min(1.0, cosz))))


def main():
    c = load_conf()
    elev = sun_elevation(c['LAT'], c['LON'], datetime.now(timezone.utc))
    t = (elev - c['ELEV_LOW']) / (c['ELEV_HIGH'] - c['ELEV_LOW'])
    t = max(0.0, min(1.0, t))
    pct = c['NIGHT'] + (c['DAY'] - c['NIGHT']) * t
    bl = c['BACKLIGHT']
    maxb = int(open(bl + '/max_brightness').read())
    target = max(1, round(maxb * pct / 100))
    cur = int(open(bl + '/brightness').read())
    if '--dry-run' in sys.argv or cur == target:
        print('sun %.1f deg -> %.0f%% (%d/%d)%s' % (elev, pct, target, maxb,
              '' if cur == target else ' [dry run, now %d]' % cur))
        return
    with open(bl + '/brightness', 'w') as f:
        f.write(str(target))
    print('sun %.1f deg -> %.0f%% (%d -> %d/%d)' % (elev, pct, cur, target, maxb))


if __name__ == '__main__':
    main()
