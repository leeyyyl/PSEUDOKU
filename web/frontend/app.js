const solveBtn = document.getElementById("solveBtn");
const resetBtn = document.getElementById("resetBtn");
const output = document.getElementById("output");
const gridEl = document.getElementById("grid");
const algSelect = document.getElementById("alg");
const subcoloniesRow = document.getElementById("subcoloniesRow");
const antsRow = document.getElementById("antsRow");
const timeoutRow = document.getElementById("timeoutRow");
const sampleSelect = document.getElementById("sampleSelect");
const keypad = document.getElementById("keypad");
const isTouchDevice =
	"ontouchstart" in window || (navigator.maxTouchPoints || 0) > 0;
let baselinePuzzle = "";

const DEFAULT_GRID = Array.from({ length: 9 }, () => Array(9).fill(0));

function getValue(id) {
	return document.getElementById(id).value;
}

function buildGrid() {
	gridEl.innerHTML = "";
	for (let r = 0; r < 9; r += 1) {
		for (let c = 0; c < 9; c += 1) {
			const input = document.createElement("input");
			input.type = "text";
			input.inputMode = isTouchDevice ? "none" : "numeric";
			input.maxLength = 1;
			input.className = "cell";
			input.dataset.row = String(r);
			input.dataset.col = String(c);
			if (isTouchDevice) {
				input.setAttribute("readonly", "readonly");
			}
			const value = DEFAULT_GRID[r][c];
			input.value = value > 0 ? String(value) : "";
			input.addEventListener("input", () => {
				const cleaned = input.value.replace(/[^1-9]/g, "");
				input.value = cleaned.slice(0, 1);
				clearInvalidMarks();
			});
			input.addEventListener("click", () => {
				const prev = gridEl.querySelector(".cell.selected");
				if (prev && prev !== input) {
					prev.classList.remove("selected");
				}
				input.classList.add("selected");
			});
			if (isTouchDevice) {
				input.addEventListener("touchstart", (event) => {
					event.preventDefault();
					input.click();
				});
			}
			input.addEventListener("focus", () => {
				const prev = gridEl.querySelector(".cell.selected");
				if (prev && prev !== input) {
					prev.classList.remove("selected");
				}
				input.classList.add("selected");
			});
			gridEl.appendChild(input);
		}
	}
}

function resetGrid() {
	const cells = gridEl.querySelectorAll(".cell");
	cells.forEach((cell) => {
		cell.value = "";
		cell.classList.remove("selected");
	});
	if (sampleSelect) {
		sampleSelect.value = "";
	}
	baselinePuzzle = "";
	clearInvalidMarks();
	output.textContent = "Ready.";
}

function clearInvalidMarks() {
	for (const cell of gridEl.querySelectorAll(".cell.invalid")) {
		cell.classList.remove("invalid");
	}
}

function readGrid() {
	const grid = Array.from({ length: 9 }, () => Array(9).fill(0));
	for (const cell of gridEl.querySelectorAll(".cell")) {
		const r = Number(cell.dataset.row);
		const c = Number(cell.dataset.col);
		const value = Number(cell.value);
		grid[r][c] = Number.isFinite(value) ? value : 0;
	}
	return grid;
}

function markInvalid(cells) {
	for (const cell of cells) {
		cell.classList.add("invalid");
	}
}

function validateGrid(grid) {
	const invalidCells = new Set();
	const getCell = (r, c) =>
		gridEl.querySelector(`.cell[data-row="${r}"][data-col="${c}"]`);

	for (let r = 0; r < 9; r += 1) {
		const seen = new Map();
		for (let c = 0; c < 9; c += 1) {
			const value = grid[r][c];
			if (!value) continue;
			if (seen.has(value)) {
				invalidCells.add(getCell(r, c));
				invalidCells.add(getCell(r, seen.get(value)));
			} else {
				seen.set(value, c);
			}
		}
	}

	for (let c = 0; c < 9; c += 1) {
		const seen = new Map();
		for (let r = 0; r < 9; r += 1) {
			const value = grid[r][c];
			if (!value) continue;
			if (seen.has(value)) {
				invalidCells.add(getCell(r, c));
				invalidCells.add(getCell(seen.get(value), c));
			} else {
				seen.set(value, r);
			}
		}
	}

	for (let boxR = 0; boxR < 3; boxR += 1) {
		for (let boxC = 0; boxC < 3; boxC += 1) {
			const seen = new Map();
			for (let r = 0; r < 3; r += 1) {
				for (let c = 0; c < 3; c += 1) {
					const row = boxR * 3 + r;
					const col = boxC * 3 + c;
					const value = grid[row][col];
					if (!value) continue;
					if (seen.has(value)) {
						const [prevR, prevC] = seen.get(value);
						invalidCells.add(getCell(row, col));
						invalidCells.add(getCell(prevR, prevC));
					} else {
						seen.set(value, [row, col]);
					}
				}
			}
		}
	}

	if (invalidCells.size > 0) {
		markInvalid(invalidCells);
		return false;
	}

	return true;
}

function gridToPuzzleString(grid) {
	return grid.map((row) => row.map((v) => (v ? String(v) : ".")).join("")).join("");
}

function updateSubcoloniesVisibility() {
	const alg = Number(algSelect.value);
	const showSubcolonies = alg === 2;
	subcoloniesRow.style.display = showSubcolonies ? "block" : "none";
	const showOnlyTimeout = alg === 1;
	antsRow.style.display = showOnlyTimeout ? "none" : "block";
	subcoloniesRow.style.display = showOnlyTimeout ? "none" : subcoloniesRow.style.display;
	timeoutRow.style.display = "block";
}

function normalizeSolution(solution) {
	if (!solution) return "";
	if (solution.length === 81) return solution;
	const matches = solution.match(/[1-9.]/g) || [];
	if (matches.length === 81) return matches.join("");
	return "";
}

function normalizePuzzle(puzzle) {
	return normalizeSolution(puzzle);
}

function applySolution(solution) {
	const normalized = normalizeSolution(solution);
	if (!normalized) return;
	const cells = gridEl.querySelectorAll(".cell");
	for (let i = 0; i < cells.length && i < normalized.length; i += 1) {
		const ch = normalized[i];
		cells[i].value = ch === "." ? "" : ch;
	}
	const prev = gridEl.querySelector(".cell.selected");
	if (prev) {
		prev.classList.remove("selected");
	}
}

document.addEventListener("keydown", (event) => {
	const selected = gridEl.querySelector(".cell.selected");
	if (!selected) return;
	const active = document.activeElement;
	if (active && active !== selected && active.tagName === "INPUT") return;

	if (event.key >= "1" && event.key <= "9") {
		selected.value = event.key;
		clearInvalidMarks();
		event.preventDefault();
		return;
	}

	if (event.key === "Backspace" || event.key === "Delete") {
		selected.value = "";
		clearInvalidMarks();
		event.preventDefault();
	}
});

if (keypad) {
	keypad.addEventListener("click", (event) => {
		const target = event.target;
		if (!target || !target.dataset) return;
		const value = target.dataset.key;
		if (!value) return;
		const selected = gridEl.querySelector(".cell.selected");
		if (!selected) return;
		if (value === "clear") {
			selected.value = "";
		} else {
			selected.value = value;
		}
		clearInvalidMarks();
	});
}

document.addEventListener("click", (event) => {
	const target = event.target;
	if (!target) return;
	if (target.classList && target.classList.contains("cell")) return;
	if (gridEl.contains(target)) return;
	const prev = gridEl.querySelector(".cell.selected");
	if (prev) {
		prev.classList.remove("selected");
	}
});

async function loadSample(name) {
	if (!name) return;
	try {
		const response = await fetch(`/sample/${name}`);
		const data = await response.json();
		if (!response.ok) {
			output.textContent = JSON.stringify(data, null, 2);
			return;
		}
		baselinePuzzle = normalizePuzzle(data.puzzle || "");
		if (!baselinePuzzle) {
			output.textContent = `Sample invalid: ${data.name}`;
			return;
		}
		applySolution(baselinePuzzle);
		clearInvalidMarks();
		if (sampleSelect) {
			sampleSelect.value = "";
		}
		output.textContent = `Loaded sample: ${data.name}`;
	} catch (err) {
		output.textContent = String(err);
	}
}

solveBtn.addEventListener("click", async () => {
	output.textContent = "Solving...";
	clearInvalidMarks();
	const grid = readGrid();
	if (!validateGrid(grid)) {
		output.textContent = "Invalid puzzle: duplicate values in a row, column, or 3x3 box.";
		return;
	}
	const payload = {
		puzzle: gridToPuzzleString(grid),
		alg: Number(getValue("alg")),
		subcolonies: Number(getValue("subcolonies")),
		ants: Number(getValue("ants")),
		timeout: Number(getValue("timeout")),
	};

	if (!payload.puzzle) {
		output.textContent = "Please enter at least one clue.";
		return;
	}

	try {
		const response = await fetch("/solve", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(payload),
		});

		const data = await response.json();
		if (!response.ok) {
			output.textContent = data?.detail?.error || "Solve failed.";
			return;
		}

		const time = typeof data.time === "number" ? data.time.toFixed(3) : "n/a";
		const cycles = typeof data.iterations === "number" ? data.iterations : "n/a";
		output.textContent = `Total Time: ${time}s\nCycles: ${cycles}`;
		applySolution(data.solution);
	} catch (err) {
		output.textContent = String(err);
	}
});

resetBtn.addEventListener("click", () => {
	resetGrid();
});

buildGrid();
updateSubcoloniesVisibility();
algSelect.addEventListener("change", updateSubcoloniesVisibility);
if (sampleSelect) {
	sampleSelect.addEventListener("change", () => loadSample(sampleSelect.value));
	sampleSelect.addEventListener("click", () => loadSample(sampleSelect.value));
}