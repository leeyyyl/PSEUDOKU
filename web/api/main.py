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
SAMPLES_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "instances", "hard"))
SAMPLE_NAMES = [f"9x9hard_{i}" for i in range(1, 11)]

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
	if name not in SAMPLE_NAMES:
		raise HTTPException(status_code=404, detail="Sample not found")
	path = os.path.join(SAMPLES_DIR, name)
	if not os.path.isfile(path):
		raise HTTPException(status_code=404, detail="Sample file missing")
	with open(path, "r", encoding="utf-8") as file:
		tokens = file.read().split()
	if len(tokens) < 3:
		raise HTTPException(status_code=500, detail="Sample file invalid")
	order = int(tokens[0])
	num_cells = order * order * order * order
	values = tokens[2:2 + num_cells]
	if len(values) < num_cells:
		raise HTTPException(status_code=500, detail="Sample file incomplete")
	puzzle_chars = []
	for val_str in values:
		val = int(val_str)
		if val == -1:
			puzzle_chars.append(".")
		elif order == 3:
			puzzle_chars.append(chr(ord("1") + val - 1))
		elif order == 4:
			if val < 11:
				puzzle_chars.append(chr(ord("0") + val - 1))
			else:
				puzzle_chars.append(chr(ord("a") + val - 11))
		else:
			puzzle_chars.append(chr(ord("a") + val - 1))
	return "".join(puzzle_chars)


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
