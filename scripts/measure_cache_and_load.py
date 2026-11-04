#!/usr/bin/env python3
"""Measure page-cache and background-load conditions around one command.

The script does not modify the command's inputs. It snapshots /proc before,
during (20 ms sampling) and after the run, then writes a JSON summary and a
CSV sample trace.

Usage:
  python3 measure_cache_and_load.py --label gateann-low-cold \
      --device sdd --out measurements -- <command> [args...]

Notes:
  * ``Cached`` and ``Buffers`` are read from /proc/meminfo in kB.
  * Physical reads are the delta of /proc/diskstats sectors_read for --device.
  * io/cpu pressure uses /proc/pressure/* when the kernel provides it.
  * Peak RSS comes from /usr/bin/time -v if available, else from VmHWM samples.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

MEM_FIELDS = (
    "MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached",
    "SwapCached", "SwapFree", "Dirty", "Writeback",
)


def read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    with open("/proc/meminfo", encoding="ascii") as handle:
        for line in handle:
            key, rest = line.split(":", 1)
            if key in MEM_FIELDS:
                values[key] = int(rest.split()[0])
    return values


def read_diskstats(device: str) -> dict[str, int]:
    with open("/proc/diskstats", encoding="ascii") as handle:
        for line in handle:
            fields = line.split()
            if len(fields) >= 14 and fields[2] == device:
                return {
                    "reads": int(fields[3]),
                    "sectors_read": int(fields[5]),
                    "writes": int(fields[7]),
                    "sectors_written": int(fields[9]),
                }
    return {}


def read_pressure(resource: str) -> dict[str, float]:
    path = Path(f"/proc/pressure/{resource}")
    if not path.exists():
        return {}
    result: dict[str, float] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        fields = line.split()
        kind = fields[0]
        for item in fields[1:]:
            key, value = item.split("=", 1)
            result[f"{kind}_{key}"] = float(value)
    return result


def read_cpu() -> tuple[int, int]:
    with open("/proc/stat", encoding="ascii") as handle:
        fields = [int(x) for x in handle.readline().split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    return sum(fields), idle


def read_loadavg() -> tuple[float, float, float]:
    with open("/proc/loadavg", encoding="ascii") as handle:
        parts = handle.read().split()
    return float(parts[0]), float(parts[1]), float(parts[2])


def read_vm(pid: int) -> tuple[int, int]:
    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as handle:
            rss = hwm = 0
            for line in handle:
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1])
                elif line.startswith("VmHWM:"):
                    hwm = int(line.split()[1])
            return rss, hwm
    except (FileNotFoundError, ProcessLookupError):
        return 0, 0


def process_snapshot() -> list[dict[str, object]]:
    try:
        output = subprocess.check_output(
            ["ps", "-eo", "pid,pcpu,pmem,stat,comm,args", "--sort=-pcpu"],
            text=True, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    own_pid = os.getpid()
    for line in output.splitlines()[1:9]:
        fields = line.split(None, 5)
        if len(fields) == 6:
            pid = int(fields[0])
            if pid == own_pid:
                continue  # do not count the probe itself as background load
            rows.append({
                "pid": pid, "cpu_percent": float(fields[1]),
                "mem_percent": float(fields[2]), "stat": fields[3],
                "comm": fields[4], "args": fields[5],
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--device", default="sdd")
    parser.add_argument("--out", default="measurements")
    parser.add_argument("--interval-ms", type=int, default=20)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("missing command after --")

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir / f"{args.label}.log"
    time_path = outdir / f"{args.label}.time"
    csv_path = outdir / f"{args.label}.samples.csv"
    json_path = outdir / f"{args.label}.json"

    mem_before = read_meminfo()
    disk_before = read_diskstats(args.device)
    psi_io_before = read_pressure("io")
    psi_cpu_before = read_pressure("cpu")
    cpu_before = read_cpu()
    load_before = read_loadavg()
    procs_before = process_snapshot()

    samples: list[dict[str, object]] = []
    stop = threading.Event()
    pid_holder = {"pid": 0}

    def sampler() -> None:
        start = time.perf_counter()
        while not stop.is_set():
            mem = read_meminfo()
            disk = read_diskstats(args.device)
            psi_io = read_pressure("io")
            psi_cpu = read_pressure("cpu")
            rss, hwm = read_vm(pid_holder["pid"]) if pid_holder["pid"] else (0, 0)
            samples.append({
                "t_s": round(time.perf_counter() - start, 6),
                "cached_kb": mem.get("Cached", 0),
                "buffers_kb": mem.get("Buffers", 0),
                "mem_available_kb": mem.get("MemAvailable", 0),
                "sectors_read": disk.get("sectors_read", 0),
                "rss_kb": rss,
                "hwm_kb": hwm,
                "psi_io_some_us": psi_io.get("some_total", 0.0),
                "psi_cpu_some_us": psi_cpu.get("some_total", 0.0),
            })
            time.sleep(max(args.interval_ms, 5) / 1000.0)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()

    start = time.perf_counter()
    time_cmd = shutil.which("/usr/bin/time") or shutil.which("time")
    time_cmd = "/usr/bin/time" if Path("/usr/bin/time").exists() else None
    with open(log_path, "w", encoding="utf-8") as log:
        if time_cmd:
            process = subprocess.Popen(
                [time_cmd, "-v", "-o", str(time_path)] + command,
                stdout=log, stderr=subprocess.STDOUT, text=True,
            )
            pid_holder["pid"] = process.pid
            returncode = process.wait()
        else:
            process = subprocess.Popen(
                command, stdout=log, stderr=subprocess.STDOUT, text=True,
            )
            pid_holder["pid"] = process.pid
            returncode = process.wait()
    elapsed = time.perf_counter() - start
    stop.set()
    thread.join(timeout=1.0)

    mem_after = read_meminfo()
    disk_after = read_diskstats(args.device)
    psi_io_after = read_pressure("io")
    psi_cpu_after = read_pressure("cpu")
    cpu_after = read_cpu()
    load_after = read_loadavg()
    procs_after = process_snapshot()

    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(samples[0].keys()) if samples else [])
        if samples:
            writer.writeheader()
            writer.writerows(samples)

    total_cpu = cpu_after[0] - cpu_before[0]
    idle_cpu = cpu_after[1] - cpu_before[1]
    cpu_busy_percent = 100.0 * (total_cpu - idle_cpu) / total_cpu if total_cpu else 0.0
    sectors_read = disk_after.get("sectors_read", 0) - disk_before.get("sectors_read", 0)

    summary = {
        "label": args.label,
        "command": command,
        "returncode": returncode,
        "elapsed_s": round(elapsed, 6),
        "device": args.device,
        "physical_read_mib": round(sectors_read * 512 / (1024 * 1024), 3),
        "cpu_busy_percent_system_wide": round(cpu_busy_percent, 2),
        "loadavg_before": load_before,
        "loadavg_after": load_after,
        "mem_before_kb": mem_before,
        "mem_after_kb": mem_after,
        "cached_peak_kb": max((s["cached_kb"] for s in samples), default=0),
        "cached_delta_kb": mem_after.get("Cached", 0) - mem_before.get("Cached", 0),
        "psi_io_some_delta_us": round(psi_io_after.get("some_total", 0.0) - psi_io_before.get("some_total", 0.0), 1),
        "psi_cpu_some_delta_us": round(psi_cpu_after.get("some_total", 0.0) - psi_cpu_before.get("some_total", 0.0), 1),
        "background_processes_before": procs_before,
        "background_processes_after": procs_after,
    }
    if time_path.exists():
        text = time_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if "Maximum resident set size" in line:
                summary["peak_rss_kb_time"] = int(line.rsplit(":", 1)[1].strip())
            elif "Percent of CPU this job got" in line:
                summary["process_cpu_percent"] = line.rsplit(":", 1)[1].strip()
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "label": args.label,
        "returncode": returncode,
        "elapsed_s": summary["elapsed_s"],
        "physical_read_mib": summary["physical_read_mib"],
        "cached_peak_mib": round(summary["cached_peak_kb"] / 1024, 1),
        "cached_delta_mib": round(summary["cached_delta_kb"] / 1024, 1),
        "psi_io_delta_us": summary["psi_io_some_delta_us"],
        "cpu_busy_percent": summary["cpu_busy_percent_system_wide"],
        "loadavg": load_after,
    }, ensure_ascii=False))
    return 0 if returncode == 0 else returncode


if __name__ == "__main__":
    sys.exit(main())
