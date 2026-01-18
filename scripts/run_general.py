#!/usr/bin/env python3
"""
Utility to batch-run all general Sudoku instances through the ACS solver.

Example:
    python scripts/run_general.py --verbose
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import statistics
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess, run, PIPE
from typing import Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class InstanceMetadata:
    path: Path
    size_label: str
    fixed_percentage: Optional[int]
    instance_id: Optional[int]

    @property
    def relative_path(self) -> str:
        repo_root = find_repo_root()
        return str(self.path.relative_to(repo_root))


def find_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_solver_candidates() -> Sequence[str]:
    if os.name == "nt":
        return (
            "sudoku_ants.exe",
            "sudoku_ants",
            os.path.join("vs2017", "x64", "Release", "sudoku_ants.exe"),
            os.path.join("vs2017", "Release", "sudoku_ants.exe"),
        )
    return (
        "./sudoku_ants",
        "sudoku_ants",
        os.path.join("vs2017", "x64", "Release", "sudoku_ants"),
        os.path.join("vs2017", "Release", "sudoku_ants"),
    )


def resolve_solver_path(user_value: Optional[str]) -> Path:
    repo_root = find_repo_root()
    if user_value:
        solver_path = Path(user_value)
        if not solver_path.is_absolute():
            solver_path = (repo_root / solver_path).resolve()
        if solver_path.exists():
            return solver_path
        raise FileNotFoundError(f"Solver binary not found at '{solver_path}'.")

    for candidate in default_solver_candidates():
        candidate_path = (repo_root / candidate).resolve()
        if candidate_path.exists() and candidate_path.is_file():
            return candidate_path

    raise FileNotFoundError(
        "Solver binary not found. Build it first (e.g. run `make -f Makefile`)."
    )


def natural_sort_key(path: Path) -> list:
    """
    Generate a sort key that handles numeric parts naturally.
    E.g., '9x9hard_2' comes before '9x9hard_10'
    """
    import re
    parts = []
    for part in re.split(r'(\d+)', path.name):
        if part.isdigit():
            parts.append(int(part))
        else:
            parts.append(part)
    return parts


def iter_instance_files(instances_root: Path) -> Iterable[Path]:
    if not instances_root.exists():
        raise FileNotFoundError(f"Instances folder not found: '{instances_root}'.")
    # Find all .txt files and files without extensions (for "hard" folder)
    all_files = list(instances_root.glob("*.txt"))
    # Also include files without extensions (filter out directories)
    all_files.extend([f for f in instances_root.glob("*") if f.is_file() and f.suffix == ""])
    # Sort naturally so 9x9hard_1, 9x9hard_2, ... 9x9hard_10 are in correct order
    return sorted(all_files, key=natural_sort_key)


def iter_all_instance_files(repo_root: Path) -> Iterable[Path]:
    """Iterate over both general and logic-solvable instances."""
    all_files = []
    
    # General instances
    general_root = repo_root / "instances" / "general"
    if general_root.exists():
        all_files.extend(general_root.glob("*.txt"))
    
    # Logic-solvable instances
    logic_root = repo_root / "instances" / "logic-solvable"
    if logic_root.exists():
        all_files.extend(logic_root.glob("*.txt"))
    
    if not all_files:
        raise FileNotFoundError("No instance files found in 'instances/general' or 'instances/logic-solvable'.")
    
    return sorted(all_files)


def parse_metadata(path: Path) -> InstanceMetadata:
    name = path.stem
    match = re.match(r"inst(?P<size>[0-9x]+)_(?P<fixed>\d+)_(?P<idx>\d+)", name)
    size = None
    fixed = None
    idx = None
    if match:
        size = match.group("size")
        fixed = int(match.group("fixed"))
        idx = int(match.group("idx"))
    else:
        # Logic-solvable instances: use puzzle name as size_label
        size = name
    return InstanceMetadata(path=path, size_label=size or "unknown", fixed_percentage=fixed, instance_id=idx)


def sort_instance_metadata(instances: Sequence[InstanceMetadata]) -> List[InstanceMetadata]:
    size_order = {"9x9": 0, "16x16": 1, "25x25": 2, "36x36": 3}

    def key(meta: InstanceMetadata) -> Tuple[int, int, int, list]:
        return (
            size_order.get(meta.size_label, 99),
            meta.fixed_percentage if meta.fixed_percentage is not None else 999,
            meta.instance_id if meta.instance_id is not None else 999,
            natural_sort_key(meta.path),
        )

    return sorted(instances, key=key)


def format_instance_argument(instance_path: Path, repo_root: Path) -> str:
    try:
        rel_path = instance_path.relative_to(repo_root)
    except ValueError:
        path_str = str(instance_path)
    else:
        prefixed = Path(".") / rel_path
        path_str = str(prefixed)
    
    # Quote paths with spaces (for Windows compatibility)
    if ' ' in path_str:
        return f'"{path_str}"'
    return path_str


def build_solver_command(
    solver_path: Path,
    instance_path: Path,
    repo_root: Path,
    args: argparse.Namespace,
) -> List[str]:
    file_arg = format_instance_argument(instance_path, repo_root)
    cmd: List[str] = [str(solver_path), "--file", file_arg, "--alg", str(args.alg), "--timeout", str(args.timeout)]

    if args.ants is not None:
        cmd.extend(("--ants", str(args.ants)))
    if args.subcolonies is not None:
        cmd.extend(("--subcolonies", str(args.subcolonies)))
    if args.q0 is not None:
        cmd.extend(("--q0", str(args.q0)))
    if args.rho is not None:
        cmd.extend(("--rho", str(args.rho)))
    if args.evap is not None:
        cmd.extend(("--evap", str(args.evap)))
    # Always add verbose for algorithms 0 and 2 to get iteration count
    if args.alg == 0 or args.alg == 2 or args.solver_verbose:
        cmd.append("--verbose")
    return cmd


def run_solver(cmd: Sequence[str], cwd: Path, timeout: Optional[float], show_progress: bool = False) -> CompletedProcess:
    if show_progress:
        # Don't capture stderr so progress messages show in real-time
        return run(
            list(cmd),
            cwd=str(cwd),
            stdout=PIPE,
            stderr=None,  # Let stderr go directly to console
            text=True,
            timeout=timeout,
        )
    else:
        return run(
            list(cmd),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )


def parse_solver_output(stdout: str, stderr: str) -> Tuple[Optional[bool], Optional[float], Optional[int], Optional[bool], Optional[float], Optional[float], Optional[int], str, str]:
    stdout_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    stderr_lines = [line.strip() for line in stderr.splitlines() if line.strip()]

    success: Optional[bool] = None
    solve_time: Optional[float] = None
    iterations: Optional[int] = None
    communication: Optional[bool] = None
    cp_initial: Optional[float] = None
    cp_ant: Optional[float] = None
    cp_calls: Optional[int] = None

    # Combine stdout and stderr for parsing (iterations might be in either)
    all_lines = stdout_lines + stderr_lines

    for line in all_lines:
        if line in {"0", "1"} and success is None:
            success = (line == "0")
            continue

        solved_match = re.search(r"solved in ([0-9]*\.?[0-9]+)", line)
        if solved_match:
            solve_time = float(solved_match.group(1))
            success = True
            continue

        failed_match = re.search(r"failed in time ([0-9]*\.?[0-9]+)", line)
        if failed_match:
            solve_time = float(failed_match.group(1))
            success = False
            continue

        # Parse iterations (for algorithms 0 and 2)
        iter_match = re.search(r"iterations:\s*([0-9]+)", line, re.IGNORECASE)
        if iter_match:
            iterations = int(iter_match.group(1))
            continue

        # Parse communication flag for algorithm 2
        comm_match = re.search(r"communication:\s*(yes|no)", line, re.IGNORECASE)
        if comm_match:
            communication = (comm_match.group(1).lower() == "yes")
            continue
        
        # Parse CP timing data
        cp_initial_match = re.search(r"cp_initial:\s*([0-9]*\.?[0-9]+)", line)
        if cp_initial_match:
            cp_initial = float(cp_initial_match.group(1))
            continue
        
        cp_ant_match = re.search(r"cp_ant:\s*([0-9]*\.?[0-9]+)", line)
        if cp_ant_match:
            cp_ant = float(cp_ant_match.group(1))
            continue
        
        cp_calls_match = re.search(r"cp_calls:\s*([0-9]+)", line)
        if cp_calls_match:
            cp_calls = int(cp_calls_match.group(1))
            continue

    # Fallback: check stdout for time if not found yet
    for line in stdout_lines:
        # Fallback: if a line can be parsed as float and we still do not have a time.
        if solve_time is None:
            try:
                solve_time = float(line)
            except ValueError:
                pass

    if success is None:
        # Check stderr for clues
        for line in stderr_lines:
            if "could not open file" in line.lower():
                success = False
                break

    if solve_time is not None:
        solve_time = round(solve_time, 5)

    return success, solve_time, iterations, communication, cp_initial, cp_ant, cp_calls, "\n".join(stdout_lines), "\n".join(stderr_lines)


def write_csv(output_path: Path, rows: Sequence[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["alg", "puzzle_size", "f%", "ants", "subcolonies", "q0", "rho", "bve", "timeout", "success_rate", "time_mean", "time_std", "iter_mean", "with_comm", "without_comm", "cp_initial_mean", "cp_ant_mean", "cp_total_mean", "cp_percentage"]
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def compute_summary(total: int, successes: int, times: Sequence[float]) -> Tuple[int, int, float]:
    avg_time = sum(times) / len(times) if times else 0.0
    return total, successes, round(avg_time, 5)


def summarize_group(size_label: str, fixed_percentage: Optional[int], stats: dict, args: argparse.Namespace) -> dict:
    total = stats.get("total", 0)
    if total == 0:
        return {}

    successes = stats.get("successes", 0)
    fails = stats.get("fails", 0)
    times = stats.get("times", [])
    iterations = stats.get("iterations", [])
    with_comm = stats.get("with_comm", 0)
    without_comm = stats.get("without_comm", 0)
    cp_initial_list = stats.get("cp_initial", [])
    cp_ant_list = stats.get("cp_ant", [])
    cp_calls_list = stats.get("cp_calls", [])
    
    success_rate = (successes / total) * 100.0 if total else 0.0
    average_time = round(sum(times) / len(times), 5) if times else 0.0
    time_std = round(statistics.pstdev(times), 5) if len(times) > 1 else 0.0
    average_iter = round(sum(iterations) / len(iterations), 2) if iterations else 0.0
    
    # Calculate CP timing statistics
    avg_cp_initial = round(sum(cp_initial_list) / len(cp_initial_list), 6) if cp_initial_list else 0.0
    avg_cp_ant = round(sum(cp_ant_list) / len(cp_ant_list), 6) if cp_ant_list else 0.0
    avg_cp_total = avg_cp_initial + avg_cp_ant
    avg_cp_percentage = round((avg_cp_total / average_time * 100), 2) if average_time > 0 else 0.0

    label = size_label
    if fixed_percentage is not None:
        label = f"{label} @ {fixed_percentage}% fixed"

    # Build summary message
    summary_msg = f"Summary {label}: success={successes}, fail={fails}, success_rate={success_rate:.2f}%, avg_time={average_time:.5f}s"
    
    if iterations:
        summary_msg += f", avg_iter={average_iter:.2f}"
    
    if args.alg == 2 and (with_comm > 0 or without_comm > 0):
        summary_msg += f", comm={with_comm}/{with_comm + without_comm}"
    
    # Add CP timing to summary
    if cp_initial_list and cp_ant_list:
        summary_msg += f", CP: {avg_cp_total:.6f}s ({avg_cp_percentage:.1f}%)"
    
    print(summary_msg)
    sys.stdout.flush()  # Force immediate output to prevent timing issues

    # Get actual ant count (default is 10)
    actual_ants = args.ants if args.ants is not None else 10
    
    # Get actual subcolonies count (default is 4)
    actual_subcolonies = args.subcolonies if args.subcolonies is not None else 4

    return {
        "alg": args.alg,
        "puzzle_size": size_label,
        "f%": fixed_percentage if fixed_percentage is not None else "",
        "ants": actual_ants,
        "subcolonies": actual_subcolonies,
        "q0": args.q0,
        "rho": args.rho,
        "bve": args.evap,
        "timeout": args.timeout,
        "success_rate": round(success_rate, 2),
        "time_mean": average_time,
        "time_std": time_std,
        "iter_mean": average_iter if (args.alg == 0 or args.alg == 2) else "",
        "with_comm": with_comm if args.alg == 2 else "",
        "without_comm": without_comm if args.alg == 2 else "",
        "cp_initial_mean": avg_cp_initial if cp_initial_list else "",
        "cp_ant_mean": avg_cp_ant if cp_ant_list else "",
        "cp_total_mean": avg_cp_total if (cp_initial_list and cp_ant_list) else "",
        "cp_percentage": avg_cp_percentage if (cp_initial_list and cp_ant_list) else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all general Sudoku instances through the solver.")
    parser.add_argument("--instances-root", default=None, help="Folder containing instances (default: runs both instances/general AND instances/logic-solvable)")
    parser.add_argument("--solver", default=None, help="Path to the solver executable (default: auto-detect)")
    parser.add_argument("--output", default="results/general_metrics.csv", help="Destination CSV file for metrics.")
    parser.add_argument("--alg", type=int, default=0, help="Solver algorithm (0=ACS, 1=backtracking).")
    parser.add_argument("--timeout", type=float, default=120.0, help="Timeout per puzzle in seconds (default: 120).")
    parser.add_argument("--ants", type=int, default=None, help="Override number of ants (ACS only).")
    parser.add_argument("--subcolonies", type=int, default=None, help="Number of sub-colonies for parallel ACS (alg=2, default: 4).")
    parser.add_argument("--q0", type=float, default=0.9, help="Override ACS q0 parameter.")
    parser.add_argument("--rho", type=float, default=0.9, help="Override ACS rho parameter.")
    parser.add_argument("--evap", type=float, default=0.005, help="Override ACS evaporation parameter.")
    parser.add_argument("--limit", type=int, default=None, help="Optional cap on number of instances to process.")
    parser.add_argument("--puzzle-size", dest="puzzle_sizes", nargs="+", choices=["9x9", "16x16", "25x25", "36x36"], help="Filter by puzzle size(s), e.g. --puzzle-size 25x25.")
    parser.add_argument("--fixed-percentage", dest="fixed_percentages", type=int, nargs="+", help="Filter by fixed-cell percentage(s), e.g. --fixed-percentage 40.")
    parser.add_argument("--solver-timeout", type=float, default=None, help="Wall-clock timeout applied to each solver invocation.")
    parser.add_argument("--solver-verbose", action="store_true", help="Pass --verbose to the solver binary.")
    parser.add_argument("--verbose", action="store_true", default=True, help="Print per-instance progress to the console (default: True).")
    parser.add_argument("--no-verbose", dest="verbose", action="store_false", help="Disable per-instance progress output.")

    args = parser.parse_args()

    repo_root = find_repo_root()

    try:
        solver_path = resolve_solver_path(args.solver)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    # Determine which instances to run
    if args.instances_root is not None:
        # User specified a specific folder
        instances_root = (repo_root / args.instances_root).resolve()
        try:
            instance_files = list(iter_instance_files(instances_root))
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            return 1
        if not instance_files:
            print(f"No instances found in '{instances_root}'.", file=sys.stderr)
            return 1
        instances_root_display = instances_root
    else:
        # Default: run both general and logic-solvable instances
        try:
            instance_files = list(iter_all_instance_files(repo_root))
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            return 1
        instances_root_display = repo_root / "instances" / "(general + logic-solvable)"

    metadata_list = sort_instance_metadata([parse_metadata(path) for path in instance_files])

    if args.puzzle_sizes:
        allowed_sizes = set(args.puzzle_sizes)
        metadata_list = [meta for meta in metadata_list if meta.size_label in allowed_sizes]

    if args.fixed_percentages:
        allowed_fixed = set(args.fixed_percentages)
        metadata_list = [
            meta
            for meta in metadata_list
            if meta.fixed_percentage is not None and meta.fixed_percentage in allowed_fixed
        ]

    if not metadata_list:
        print("No instances match the specified filters.", file=sys.stderr)
        return 1

    if args.limit is not None:
        metadata_list = metadata_list[: args.limit]

    group_rows: List[dict] = []
    total_instances = len(metadata_list)
    current_group_key: Optional[Tuple[str, Optional[int]]] = None
    group_stats = {"total": 0, "successes": 0, "fails": 0, "times": [], "iterations": [], "with_comm": 0, "without_comm": 0, "cp_initial": [], "cp_ant": [], "cp_calls": []}
    overall_total = 0
    overall_successes = 0
    overall_times: List[float] = []
    overall_iterations: List[int] = []
    overall_with_comm = 0
    overall_without_comm = 0

    for idx, metadata in enumerate(metadata_list, start=1):
        # Determine if this is a logic-solvable instance (no fixed_percentage)
        is_logic_solvable = metadata.fixed_percentage is None
        num_runs = 100 if is_logic_solvable else 1
        
        # Group key for statistics
        group_key = (metadata.size_label, metadata.fixed_percentage)
        if current_group_key is None:
            current_group_key = group_key
        elif group_key != current_group_key:
            row = summarize_group(current_group_key[0], current_group_key[1], group_stats, args)
            if row:
                group_rows.append(row)
            group_stats = {"total": 0, "successes": 0, "fails": 0, "times": [], "iterations": [], "with_comm": 0, "without_comm": 0, "cp_initial": [], "cp_ant": [], "cp_calls": []}
            current_group_key = group_key
        
        # Run the puzzle num_runs times (100 for logic-solvable, 1 for general)
        for run_num in range(1, num_runs + 1):
            cmd = build_solver_command(solver_path, metadata.path, repo_root, args)
            # Show progress for algorithm 2 when verbose is enabled
            show_progress = args.verbose and args.alg == 2
            result = run_solver(cmd, repo_root, timeout=args.solver_timeout, show_progress=show_progress)

            success, solve_time, iterations, communication, cp_initial, cp_ant, cp_calls, stdout_text, stderr_text = parse_solver_output(result.stdout, result.stderr if result.stderr else "")

            if success is False and (solve_time is None or solve_time == 0.0):
                solve_time = round(float(args.timeout), 5)

            if args.verbose:
                status = "OK" if success else "FAIL" if success is not None else "UNKNOWN"
                
                # Build detailed timing string
                timing_str = ""
                if solve_time is not None:
                    timing_str = f"{solve_time:.5f}s"
                    
                    # Add detailed CP breakdown if available
                    if cp_initial is not None and cp_ant is not None and iterations is not None:
                        total_cp = cp_initial + cp_ant
                        aco_only = max(0.0, solve_time - total_cp)  # Pure ACO time (excluding CP)
                        total_aco = solve_time - cp_initial  # ACO phase (including ant CP)
                        
                        # Calculate percentages
                        cp_init_pct = (cp_initial / solve_time * 100) if solve_time > 0 else 0
                        cp_ant_pct = (cp_ant / total_aco * 100) if total_aco > 0 else 0
                        aco_only_pct = (aco_only / total_aco * 100) if total_aco > 0 else 0
                        total_cp_pct = (total_cp / solve_time * 100) if solve_time > 0 else 0
                        aco_total_pct = (total_aco / solve_time * 100) if solve_time > 0 else 0
                        
                        # Format with percentages (using 2 decimal places to show small values like CP_init)
                        timing_str = (f"CP_init={cp_initial:.6f}s ({cp_init_pct:.2f}%), "
                                    f"CP_ant={cp_ant:.6f}s ({cp_ant_pct:.2f}%), "
                                    f"ACO_only={aco_only:.5f}s ({aco_only_pct:.2f}%), "
                                    f"ACO_total={total_aco:.5f}s ({aco_total_pct:.2f}%), "
                                    f"total_CP={total_cp:.6f}s ({total_cp_pct:.2f}%), "
                                    f"Total={solve_time:.5f}s, {iterations} iter")
                    elif iterations is not None:
                        timing_str += f", {iterations} iter"
                
                if is_logic_solvable:
                    # For logic-solvable, show run number
                    if timing_str:
                        print(f"[run {run_num}/{num_runs}] {metadata.relative_path} -> {status} ({timing_str})")
                    else:
                        print(f"[run {run_num}/{num_runs}] {metadata.relative_path} -> {status}")
                else:
                    # For general instances, show normal format
                    if timing_str:
                        print(f"[{idx}/{total_instances}] {metadata.relative_path} -> {status} ({timing_str})")
                    else:
                        print(f"[{idx}/{total_instances}] {metadata.relative_path} -> {status}")

            group_stats["total"] += 1
            if success:
                group_stats["successes"] += 1
            else:
                group_stats["fails"] += 1
            # Only include times and iterations from successful runs in statistics
            if success and solve_time is not None:
                group_stats["times"].append(solve_time)
                if iterations is not None:
                    group_stats["iterations"].append(iterations)
                if communication is not None:
                    if communication:
                        group_stats["with_comm"] += 1
                    else:
                        group_stats["without_comm"] += 1
                # Track CP timing statistics
                if cp_initial is not None:
                    if "cp_initial" not in group_stats:
                        group_stats["cp_initial"] = []
                    group_stats["cp_initial"].append(cp_initial)
                if cp_ant is not None:
                    if "cp_ant" not in group_stats:
                        group_stats["cp_ant"] = []
                    group_stats["cp_ant"].append(cp_ant)
                if cp_calls is not None:
                    if "cp_calls" not in group_stats:
                        group_stats["cp_calls"] = []
                    group_stats["cp_calls"].append(cp_calls)

            overall_total += 1
            if success:
                overall_successes += 1
            # Only include times and iterations from successful runs in statistics
            if success and solve_time is not None:
                overall_times.append(solve_time)
                if iterations is not None:
                    overall_iterations.append(iterations)
                if communication is not None:
                    if communication:
                        overall_with_comm += 1
                    else:
                        overall_without_comm += 1

    output_path = (repo_root / args.output).resolve()
    if current_group_key is not None:
        row = summarize_group(current_group_key[0], current_group_key[1], group_stats, args)
        if row:
            group_rows.append(row)

    write_csv(output_path, group_rows)

    total, successes, avg_time = compute_summary(overall_total, overall_successes, overall_times)
    failures = total - successes
    avg_iterations = round(sum(overall_iterations) / len(overall_iterations), 2) if overall_iterations else None

    # Get actual ant count (default is 10)
    actual_ants = args.ants if args.ants is not None else 10
    
    # Get actual subcolonies count (default is 4)
    actual_subcolonies = args.subcolonies if args.subcolonies is not None else 4

    print("===== Summary =====")
    print(f"Solver binary   : {solver_path}")
    print(f"Instances folder: {instances_root_display}")
    print(f"Output CSV      : {output_path}")
    print(f"Algorithm       : {args.alg}")
    print(f"Ants            : {actual_ants}")
    if args.alg == 2:
        print(f"Sub-colonies    : {actual_subcolonies}")
    print(f"q0              : {args.q0}")
    print(f"rho             : {args.rho}")
    print(f"bve             : {args.evap}")
    print(f"Timeout         : {args.timeout}s")
    print(f"Total puzzles   : {total}")
    print(f"Succeeded       : {successes}")
    print(f"Failed          : {failures}")
    if total:
        print(f"Average time    : {avg_time:.5f} s")
        if avg_iterations is not None:
            print(f"Average iters   : {avg_iterations:.2f}")
        if args.alg == 2 and (overall_with_comm > 0 or overall_without_comm > 0):
            print(f"With comm       : {overall_with_comm}/{overall_with_comm + overall_without_comm} ({(overall_with_comm / (overall_with_comm + overall_without_comm) * 100.0):.1f}%)")
    else:
        print(f"Average time    : n/a")
    
    sys.stdout.flush()  # Force immediate output to prevent timing issues

    return 0


if __name__ == "__main__":
    sys.exit(main())

