#!/usr/bin/env python3
"""roamerd slam — LIDAR-only 2D SLAM (Hector-style).

Occupancy-grid mapping + ICP scan-to-scan matching. Pose is estimated purely
from scan alignment, so NO wheel odometry is required. The map is structured
as a layered grid (layer 0 = 2D occupancy now; 2.5D depth + semantic camera
layers slot in later without a rewrite).

Coordinate convention (robot frame):
  x = forward, y = left, theta = heading CCW from +x.
  LIDAR angle 0 = forward, increasing CCW: px = d*cos(a), py = d*sin(a).
"""
import io
import logging
import math
import threading
import time

import numpy as np
from PIL import Image, ImageDraw

from . import lidar

log = logging.getLogger("roamerd.slam")

# --- map parameters ---
RES = 0.05        # metres per cell
MAP_M = 40.0      # full map side (metres)
N = int(MAP_M / RES)
ORIGIN = N // 2
MAX_RANGE = 8.0   # ignore returns beyond this (noisy)

# log-odds priors
L_OCC = math.log(0.8 / 0.2)
L_FREE = math.log(0.2 / 0.8)
L_MIN = -4.0
L_MAX = 4.0

# motion gate: below this ICP delta is treated as "no movement" (kills jitter)
MIN_TRANS = 0.02   # metres
MIN_ROT = math.radians(0.5)

_latest_map = None
_pose = np.array([0.0, 0.0, 0.0])   # x, y, theta
_lock = threading.Lock()
_stop = threading.Event()


def _scan_to_points(bins):
    """360-length distance array -> Nx2 robot-frame points (drop invalid)."""
    valid = np.isfinite(bins) & (bins > 0) & (bins < MAX_RANGE)
    if not valid.any():
        return None
    d = bins[valid]
    a = np.deg2rad(np.where(valid)[0].astype(np.float64))
    return np.column_stack([d * np.cos(a), d * np.sin(a)])


def _nearest(P, Q):
    """Brute-force nearest neighbour: index into P for each q in Q. P:(M,2) Q:(N,2)."""
    d = ((P[:, None, :] - Q[None, :, :]) ** 2).sum(-1)
    return d.argmin(0)


def _solve_rigid(A, B):
    """Kabsch: R,t such that B ~= R @ A + t. A,B are (N,2)."""
    cA = A.mean(0)
    cB = B.mean(0)
    Ac = A - cA
    Bc = B - cB
    H = Ac.T @ Bc
    U, _, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    t = cB - R @ cA
    return R, t


def icp(P, Q, max_iter=30, tol=1e-5):
    """Align Q onto P (both robot-frame Nx2). Returns (R,t) with P ~= R@Q + t."""
    if P is None or Q is None or len(P) < 20 or len(Q) < 20:
        return None
    T = np.eye(3)
    Qh = np.column_stack([Q, np.ones(len(Q))])
    prev_err = None
    for _ in range(max_iter):
        Q_t = (T[:2, :2] @ Q.T).T + T[:2, 2]
        idx = _nearest(P, Q_t)
        Pc = P[idx]
        R, t = _solve_rigid(Q_t, Pc)
        dT = np.eye(3)
        dT[:2, :2] = R
        dT[:2, 2] = t
        T = dT @ T
        err = np.mean(np.sum((Pc - (R @ Q_t.T).T - t) ** 2, axis=1))
        if prev_err is not None and abs(prev_err - err) < tol:
            break
        prev_err = err
    return T[:2, :2], T[:2, 2]


class GridMap:
    def __init__(self):
        self.logodds = np.zeros((N, N), dtype=np.float32)   # 0 = unknown

    def _cell(self, x, y):
        return int(round(x / RES)) + ORIGIN, int(round(y / RES)) + ORIGIN

    def _mark(self, x, y, val):
        cx, cy = self._cell(x, y)
        if 0 <= cx < N and 0 <= cy < N:
            self.logodds[cy, cx] = min(max(self.logodds[cy, cx] + val, L_MIN), L_MAX)

    def _raycast(self, x0, y0, x1, y1):
        dist = math.hypot(x1 - x0, y1 - y0)
        steps = max(int(dist / (RES * 0.5)), 1)
        for s in range(steps):
            t = s / steps
            self._mark(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, L_FREE)
        self._mark(x1, y1, L_OCC)

    def update(self, pose, pts_robot):
        x, y, th = pose
        c, s = math.cos(th), math.sin(th)
        R = np.array([[c, -s], [s, c]])
        pts = (R @ pts_robot.T).T + np.array([x, y])
        for px, py in pts:
            self._raycast(x, y, px, py)

    def prob(self):
        # p(occ) = 1 - 1/(1+exp(l)); unknown (l==0) -> 0.5 but we show it separately
        return 1.0 - 1.0 / (1.0 + np.exp(self.logodds))


_map = GridMap()
_prev_scan = None


def _render_map():
    """Render the occupancy grid as a PNG, window centred on the robot pose."""
    win_m = 20.0
    half = int(win_m / RES / 2)          # cells
    cx = int(round(_pose[0] / RES)) + ORIGIN
    cy = int(round(_pose[1] / RES)) + ORIGIN
    x0, x1 = cx - half, cx + half
    y0, y1 = cy - half, cy + half

    sub = np.zeros((2 * half, 2 * half), dtype=np.float32)   # unknown
    sx0, sx1 = max(x0, 0), min(x1, N)
    sy0, sy1 = max(y0, 0), min(y1, N)
    if sx0 < sx1 and sy0 < sy1:
        sub[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = _map.logodds[sy0:sy1, sx0:sx1]

    p = 1.0 - 1.0 / (1.0 + np.exp(sub))
    img = np.zeros((2 * half, 2 * half, 3), dtype=np.uint8)
    img[:] = (24, 28, 38)                 # unknown: dark blue-gray
    known = sub != 0
    g = (255 * (1.0 - p[known])).astype(np.uint8)   # free->white, occ->black
    img[known] = np.stack([g, g, g], axis=-1)

    pil = Image.fromarray(img, "RGB").resize((640, 640), Image.NEAREST)
    draw = ImageDraw.Draw(pil)
    # robot marker at window centre, heading arrow
    c = 320
    draw.ellipse([c - 5, c - 5, c + 5, c + 5], fill=(255, 60, 60))
    th = _pose[2]
    draw.line([c, c, c + int(30 * math.cos(th)), c - int(30 * math.sin(th))],
              fill=(255, 60, 60), width=3)
    buf = io.BytesIO()
    pil.save(buf, "PNG")
    return buf.getvalue()


def run():
    global _latest_map, _prev_scan
    while not _stop.is_set():
        try:
            bins = lidar.get_scan()
            if bins is None:
                time.sleep(0.2)
                continue
            pts = _scan_to_points(bins)
            if pts is None:
                time.sleep(0.2)
                continue

            if _prev_scan is None:
                # first scan: seed map at origin
                _map.update(np.array([0.0, 0.0, 0.0]), pts)
                _prev_scan = pts
                log.info("slam: seeded map with %d points", len(pts))
            else:
                res = icp(_prev_scan, pts)
                if res is not None:
                    R, t = res
                    dth = math.atan2(R[1, 0], R[0, 0])
                    if math.hypot(t[0], t[1]) < MIN_TRANS and abs(dth) < MIN_ROT:
                        pass  # static: no pose change, but still refine map
                    else:
                        # compose: pos_t = pos_{t-1} + R(theta_{t-1}) . t_icp
                        c, s = math.cos(_pose[2]), math.sin(_pose[2])
                        _pose[0] += c * t[0] - s * t[1]
                        _pose[1] += s * t[0] + c * t[1]
                        _pose[2] += dth
                    _map.update(_pose, pts)
                    _prev_scan = pts

            with _lock:
                _latest_map = _render_map()
        except Exception as e:
            log.warning("slam error: %s", e)
        time.sleep(0.25)


def start():
    threading.Thread(target=run, daemon=True, name="slam").start()


def get_map():
    with _lock:
        return _latest_map


def get_pose():
    with _lock:
        return _pose.copy()
