"""Dựng dashboard 6 panel từ data/logs.jsonl theo contract config/dashboard.yaml.

Chạy:  python scripts/build_dashboard.py [--out data/dashboard.png] [--minutes 60]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import yaml  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio  # noqa: E402

# Bảng màu categorical cố định (không cycle) + màu trạng thái cho threshold
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]
THRESHOLD = "#e34948"
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_MUTED = "#52514e"
GRID = "#e4e3df"


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def load_events(path: Path, since: datetime) -> list[dict]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            ts = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        if ts >= since:
            rec["_ts"] = ts
            events.append(rec)
    return events


def by_minute(events: list[dict]) -> dict[datetime, list[dict]]:
    buckets: dict[datetime, list[dict]] = defaultdict(list)
    for rec in events:
        buckets[rec["_ts"].replace(second=0, microsecond=0)].append(rec)
    return dict(sorted(buckets.items()))


def compute(events: list[dict]) -> dict:
    sent = [e for e in events if e["event"] == "response_sent"]
    received = [e for e in events if e["event"] == "request_received"]
    failed = [e for e in events if e["event"] == "request_failed"]
    tool = [e for e in events if e.get("tool_success") is not None]
    lat = [e["latency_ms"] for e in sent]
    minutes = max(1, len(by_minute(received)))
    error_types: dict[str, int] = defaultdict(int)
    for e in failed:
        error_types[e.get("error_type") or "unknown"] += 1
    return {
        "requests": len(received),
        "rate_per_minute": len(received) / minutes,
        "p50": percentile(lat, 50),
        "p95": percentile(lat, 95),
        "p99": percentile(lat, 99),
        "ttft_p95": percentile([e["ttft_ms"] for e in sent], 95),
        "error_rate_pct": 100 * len(failed) / len(received) if received else 0.0,
        "error_types": dict(error_types),
        "tool_success_rate_pct": 100 * sum(bool(e["tool_success"]) for e in tool) / len(tool) if tool else float("nan"),
        "cost_total": sum(e["cost_usd"] for e in sent),
        "tokens_in": sum(e["tokens_in"] for e in sent),
        "tokens_out": sum(e["tokens_out"] for e in sent),
        "quality_mean": sum(e["quality_score"] for e in sent) / len(sent) if sent else float("nan"),
    }


def style_axis(ax, title: str, unit: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color=TEXT)
    ax.set_ylabel(unit, color=TEXT_MUTED, fontsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_MUTED, labelsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=datetime.now().astimezone().tzinfo))


def threshold_line(ax, value: float, label: str) -> None:
    ax.axhline(value, color=THRESHOLD, linestyle="--", linewidth=1.5, zorder=1)
    ax.annotate(
        label, xy=(1, value), xycoords=("axes fraction", "data"),
        xytext=(-4, 4), textcoords="offset points", ha="right", va="bottom",
        fontsize=8, color=TEXT_MUTED,
    )


def line(ax, xs, ys, color: str, label: str) -> None:
    ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=4, label=label, zorder=3)


def build(events: list[dict], panels: dict, stats: dict, window_min: int, window_start: datetime, now: datetime, out: Path) -> None:
    # Mỗi panel chỉ bucket theo event của chính nó, để phút không có request không bị vẽ thành 0
    sent_buckets = by_minute([e for e in events if e["event"] == "response_sent"])
    request_buckets = by_minute(
        [e for e in events if e["event"] in ("request_received", "request_failed") or e.get("tool_success") is not None]
    )

    def per_minute(fn, buckets=sent_buckets):
        return list(buckets), [fn(recs) for recs in buckets.values()]

    fig, axes = plt.subplots(2, 3, figsize=(18, 9.5), facecolor=SURFACE)
    local_tz = now.astimezone().tzinfo
    fig.suptitle(
        f"K4-L3A Day 13 Monitoring & LLMOps — last {window_min} min "
        f"({window_start.astimezone(local_tz):%Y-%m-%d %H:%M} → {now.astimezone(local_tz):%H:%M} local) · "
        f"source: data/logs.jsonl · {stats['requests']} requests",
        fontsize=13, color=TEXT, x=0.01, ha="left",
    )

    # 1. Latency + TTFT
    ax = axes[0][0]
    p = panels["latency"]
    style_axis(ax, f"{p['title']}\nP50 {stats['p50']:.0f} · P95 {stats['p95']:.0f} · P99 {stats['p99']:.0f} · TTFT P95 {stats['ttft_p95']:.0f} ms", p["unit"])
    for pct, color in ((50, SERIES[0]), (95, SERIES[1]), (99, SERIES[2])):
        line(ax, *per_minute(lambda r, pct=pct: percentile([e["latency_ms"] for e in r], pct)), color, f"P{pct}")
    line(ax, *per_minute(lambda r: percentile([e["ttft_ms"] for e in r], 95)), SERIES[3], "TTFT P95")
    threshold_line(ax, p["threshold"]["value"], f"SLO P95 ≤ {p['threshold']['value']} ms")
    ax.legend(fontsize=8, frameon=False, loc="upper left")

    # 2. Traffic
    ax = axes[0][1]
    p = panels["traffic"]
    style_axis(ax, f"{p['title']}\n{stats['requests']} requests · {stats['rate_per_minute']:.1f} req/min avg", "requests / min")
    xs, counts = per_minute(lambda r: sum(e["event"] == "request_received" for e in r), request_buckets)
    ax.bar(xs, counts, width=timedelta(seconds=40), color=SERIES[0], zorder=3)
    threshold_line(ax, p["threshold"]["value"], f"min ≥ {p['threshold']['value']} req/min")

    # 3. Errors + retrieval success
    ax = axes[0][2]
    p = panels["errors"]
    breakdown = ", ".join(f"{k}={v}" for k, v in stats["error_types"].items()) or "none"
    style_axis(ax, f"{p['title']}\nerror {stats['error_rate_pct']:.1f}% · retrieval success {stats['tool_success_rate_pct']:.1f}%\nerror_type: {breakdown}", "percent")

    def err_rate(r):
        rec = sum(e["event"] == "request_received" for e in r)
        return 100 * sum(e["event"] == "request_failed" for e in r) / rec if rec else 0.0

    def tool_rate(r):
        tool = [e for e in r if e.get("tool_success") is not None]
        return 100 * sum(bool(e["tool_success"]) for e in tool) / len(tool) if tool else float("nan")

    line(ax, *per_minute(err_rate, request_buckets), SERIES[1], "error rate %")
    line(ax, *per_minute(tool_rate, request_buckets), SERIES[2], "retrieval success %")
    threshold_line(ax, p["threshold"]["value"], f"error ≤ {p['threshold']['value']}%")
    ax.set_ylim(-3, 105)
    ax.legend(fontsize=8, frameon=False, loc="center left")

    # 4. Cost
    ax = axes[1][0]
    p = panels["cost"]
    style_axis(ax, f"{p['title']}\ntotal \\${stats['cost_total']:.4f} of \\${p['threshold']['value']} budget", "USD")
    xs, cost_min = per_minute(lambda r: sum(e["cost_usd"] for e in r))
    ax.bar(xs, cost_min, width=timedelta(seconds=40), color=SERIES[0], zorder=3, label="cost / min")
    cumulative, running = [], 0.0
    for c in cost_min:
        running += c
        cumulative.append(running)
    line(ax, xs, cumulative, SERIES[1], "cumulative")
    threshold_line(ax, p["threshold"]["value"], f"budget \\${p['threshold']['value']}")
    ax.set_yscale("symlog", linthresh=0.01)
    ax.legend(fontsize=8, frameon=False, loc="center left")

    # 5. Tokens
    ax = axes[1][1]
    p = panels["tokens"]
    style_axis(ax, f"{p['title']}\nin {stats['tokens_in']:,} · out {stats['tokens_out']:,} (cumulative)", p["unit"])
    for field, color in (("tokens_in", SERIES[0]), ("tokens_out", SERIES[1])):
        running, cumulative = 0, []
        xs, values = per_minute(lambda r, f=field: sum(e[f] for e in r))
        for v in values:
            running += v
            cumulative.append(running)
        line(ax, xs, cumulative, color, field)
    threshold_line(ax, p["threshold"]["value"], f"≤ {p['threshold']['value']:,} tokens")
    ax.set_yscale("symlog", linthresh=100)
    ax.legend(fontsize=8, frameon=False, loc="center left")

    # 6. Quality
    ax = axes[1][2]
    p = panels["quality"]
    style_axis(ax, f"{p['title']}\nmean {stats['quality_mean']:.2f}", "score 0–1")
    line(ax, *per_minute(lambda r: sum(e["quality_score"] for e in r) / len(r)), SERIES[2], "mean quality")
    threshold_line(ax, p["threshold"]["value"], f"≥ {p['threshold']['value']}")
    ax.set_ylim(0, 1.05)

    for ax in axes.flat:
        ax.set_xlim(window_start, now + timedelta(minutes=1))

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110, facecolor=SURFACE)


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Dựng dashboard 6 panel từ structured log")
    parser.add_argument("--logs", type=Path, default=REPO_ROOT / "data/logs.jsonl")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config/dashboard.yaml")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data/dashboard.png")
    parser.add_argument("--minutes", type=int, help="Ghi đè time_range_minutes trong contract")
    args = parser.parse_args()

    dashboard = yaml.safe_load(args.config.read_text(encoding="utf-8"))["dashboard"]
    panels = {p["id"]: p for p in dashboard["panels"]}
    window_min = args.minutes or dashboard["time_range_minutes"]
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_min)

    events = load_events(args.logs, window_start)
    if not any(e["event"] == "request_received" for e in events):
        print(f"Không có request nào trong {window_min} phút gần nhất ở {args.logs}. Hãy chạy load_test.py trước.")
        return 1

    stats = compute(events)
    build(events, panels, stats, window_min, window_start, now, args.out)

    print(f"Dashboard: {args.out} (last {window_min} min, {stats['requests']} requests)")
    print(f"  latency P50/P95/P99 : {stats['p50']:.0f} / {stats['p95']:.0f} / {stats['p99']:.0f} ms  (TTFT P95 {stats['ttft_p95']:.0f} ms)")
    print(f"  traffic             : {stats['rate_per_minute']:.1f} req/min")
    print(f"  error rate          : {stats['error_rate_pct']:.2f}%  {stats['error_types'] or ''}")
    print(f"  retrieval success   : {stats['tool_success_rate_pct']:.1f}%")
    print(f"  cost total          : ${stats['cost_total']:.6f}")
    print(f"  tokens in/out       : {stats['tokens_in']} / {stats['tokens_out']}")
    print(f"  quality mean        : {stats['quality_mean']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
