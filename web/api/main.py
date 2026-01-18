import json
import os
import subprocess
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
SOLVER_PATH = os.environ.get("SOLVER_PATH", "/app/sudokusolver")
HARD_SAMPLES = {
	"9x9hard_1": "98.7.....7.....6....6.5.....4...5.3...79..5......2...1..85..9......1...4.....3.2.",
	"9x9hard_2": "98.7.....6.....87...7.....5.4..3.5....65...9......2..1..86...5.....1.3.......4..2",
	"9x9hard_3": "12..3....4....1.2...52..1..5..4..2......6..7......3..8.5....9....9.7..3......8..6",
	"9x9hard_4": ".......39.....1..5..3.5.8....8.9...6.7...2...1..4.......9.8..5..2....6..4..7.....",
	"9x9hard_5": ".2.4...8.....8...68....71..2..5...9..95.......4..3.........1..7..28...4.....6.3..",
	"9x9hard_6": "........1....23.45..51..2....25...1..6...27..8...9......42....7.3...6...9...8....",
	"9x9hard_7": "12.3.....4.5...6...7.....2.6..1..3....453.........8..9...45.1.........8......2..7",
	"9x9hard_8": "5.6...7...1.3.....8...5.9.....1...2.....8.6.7.....2.4.7...9...6.3...42....5......",
	"9x9hard_9": "..3..6.8....1..2......7...4..9..8.6..3..4...1.7.2.....3....5.....5...6..98.....5.",
	"9x9hard_10": ".......12......345..3..46....2..1.3..7..6....8..9.......5..2..4.6..8....9..7.....",
}
SAMPLE_NAMES = list(HARD_SAMPLES.keys())

app = FastAPI(title="Sudoku Ant Solver API")
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_methods=["*"],
	allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


class SolveRequest(BaseModel):
	puzzle: str = Field(..., description="Puzzle string with '.' for empty cells")
	alg: int = Field(0, description="0=ACS, 1=Backtracking, 2=Parallel ACS")
	subcolonies: int = Field(4, description="Number of subcolonies (alg 2)")
	ants: int = Field(10, description="Number of ants")
	timeout: int = Field(120, description="Timeout in seconds")
	q0: float = Field(0.9, description="ACS q0 parameter")
	rho: float = Field(0.9, description="ACS rho parameter")
	evap: float = Field(0.005, description="ACS evaporation rate")


def _parse_solver_output(stdout: str) -> Any:
	lines = [line.strip() for line in stdout.splitlines() if line.strip()]
	if not lines:
		raise ValueError("solver produced no output")
	payload = lines[-1]
	return json.loads(payload)

def _validate_puzzle(puzzle: str) -> dict:
	normalized = puzzle.strip()
	if len(normalized) != 81:
		raise HTTPException(
			status_code=400,
			detail={"error": "Invalid puzzle length", "length": len(normalized)},
		)
	for ch in normalized:
		if ch not in ".123456789":
			raise HTTPException(
				status_code=400,
				detail={"error": "Invalid puzzle characters"},
			)
	given = sum(1 for ch in normalized if ch != ".")
	return {"puzzle": normalized, "given_cells": given}

def _read_sample(name: str) -> str:
	if name not in HARD_SAMPLES:
		raise HTTPException(status_code=404, detail="Sample not found")
	return HARD_SAMPLES[name]


@app.get("/")
def root():
	return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/samples")
def samples():
	return {"samples": SAMPLE_NAMES}

@app.get("/sample/{name}")
def sample(name: str):
	puzzle = _read_sample(name)
	return {"name": name, "puzzle": puzzle}


@app.post("/solve")
def solve(req: SolveRequest):
	if not os.path.isfile(SOLVER_PATH):
		raise HTTPException(status_code=500, detail="Solver binary not found")

	validation = _validate_puzzle(req.puzzle)
	puzzle = validation["puzzle"]

	args = [
		SOLVER_PATH,
		"--puzzle", puzzle,
		"--alg", str(req.alg),
		"--subcolonies", str(req.subcolonies),
		"--ants", str(req.ants),
		"--timeout", str(req.timeout),
		"--q0", str(req.q0),
		"--rho", str(req.rho),
		"--evap", str(req.evap),
		"--json",
	]

	try:
		result = subprocess.run(
			args,
			capture_output=True,
			text=True,
			timeout=req.timeout + 5,
		)
	except subprocess.TimeoutExpired:
		raise HTTPException(status_code=408, detail="Solver timed out")

	if result.returncode != 0:
		raise HTTPException(
			status_code=500,
			detail={
				"error": "Solver failed",
				"stdout": result.stdout.strip(),
				"stderr": result.stderr.strip(),
			},
		)

	try:
		payload = _parse_solver_output(result.stdout)
	except Exception as exc:
		raise HTTPException(
			status_code=500,
			detail={"error": "Invalid solver output", "details": str(exc)},
		)

	payload["input"] = {
		"length": len(puzzle),
		"given_cells": validation["given_cells"],
	}
	return payload
