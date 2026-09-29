"""Vẽ latency từng request quanh khoảng incident để xác định triệu chứng và khoảng thời gian.

Chạy:  python scripts/incident_view.py --since 2026-09-29T09:05:00Z [--until ...] [--out ...]
Ngưỡng lấy từ latency_threshold_ms trong config/challenge.json (nếu có), ngược lại 3000 ms.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]
THRESHOLD = "#e34948"
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_MUTED = "#52514e"
GRID = "#e4e3df"


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Latency từng request quanh khoảng incident")
    parser.add_argument("--logs", type=Path, default=REPO_ROOT / "data/logs.jsonl")
    parser.add_argument("--challenge", type=Path, default=REPO_ROOT / "config/challenge.json")
    parser.add_argument("--since", required=True, help="ISO UTC, ví dụ 2026-09-29T09:05:00Z")
    parser.add_argument("--until", help="ISO UTC; mặc định là hết log")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data/incident.png")
    args = parser.parse_args()

    threshold, challenge_id = 3000, "practice"
    if args.challenge.exists():
        challenge = json.loads(args.challenge.read_text(encoding="utf-8"))
        threshold = challenge.get("latency_threshold_ms", threshold)
        challenge_id = challenge.get("challenge_id", challenge_id)

    since = parse_ts(args.since)
    until = parse_ts(args.until) if args.until else None
    sent = []
    for line in args.logs.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("event") != "response_sent":
            continue
        ts = parse_ts(rec["ts"])
        if ts >= since and (until is None or ts <= until):
            rec["_ts"] = ts
            sent.append(rec)
    if not sent:
        print("Không có response_sent trong khoảng thời gian đã chọn.")
        return 1

    features = sorted({r["feature"] for r in sent})
    local_tz = datetime.now().astimezone().tzinfo
    fig, ax = plt.subplots(figsize=(13, 6.5), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)

    print(f"Challenge: {challenge_id} | threshold {threshold} ms | window {sent[0]['ts']} → {sent[-1]['ts']}")
    for color, feature in zip(SERIES, features):
        group = [r for r in sent if r["feature"] == feature]
        lat = [r["latency_ms"] for r in group]
        over = sum(v > threshold for v in lat)
        label = f"{feature}: n={len(group)}, P95 {percentile(lat, 95):.0f} ms, {over}/{len(group)} > {threshold} ms"
        ax.scatter([r["_ts"] for r in group], lat, s=70, color=color, edgecolor=SURFACE, linewidth=2, zorder=3, label=label)
        print(f"  {label} | TTFT P95 {percentile([r['ttft_ms'] for r in group], 95):.0f} ms")
        for r in group:
            if r["latency_ms"] > threshold:
                ax.annotate(r["correlation_id"], (r["_ts"], r["latency_ms"]), xytext=(6, 4),
                            textcoords="offset points", fontsize=8, color=TEXT_MUTED)
                print(f"    {r['ts']} {r['correlation_id']} latency {r['latency_ms']} ms ttft {r['ttft_ms']} ms")

    ax.axhline(threshold, color=THRESHOLD, linestyle="--", linewidth=1.5, zorder=1)
    ax.annotate(f"challenge threshold {threshold} ms", xy=(1, threshold), xycoords=("axes fraction", "data"),
                xytext=(-4, 4), textcoords="offset points", ha="right", va="bottom", fontsize=9, color=TEXT_MUTED)

    start, end = sent[0]["_ts"], sent[-1]["_ts"]
    ax.set_title(
        f"Incident metric — {challenge_id}\nresponse_sent.latency_ms per request, "
        f"{start.astimezone(local_tz):%Y-%m-%d %H:%M:%S} → {end.astimezone(local_tz):%H:%M:%S} local",
        loc="left", fontsize=12, fontweight="bold", color=TEXT,
    )
    ax.set_ylabel("latency (ms)", color=TEXT_MUTED)
    ax.set_ylim(0, max(max(r["latency_ms"] for r in sent), threshold) * 1.2)
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_MUTED, labelsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S", tz=local_tz))
    ax.legend(fontsize=9, frameon=False, loc="upper left")
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=110, facecolor=SURFACE)
    print(f"Saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
