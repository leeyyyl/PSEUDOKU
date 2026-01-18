/*******************************************************************************
 * SUDOKU SOLVER - Main Entry Point
 * 
 * This is the main executable for the Sudoku solver. It provides a
 * command-line interface for running different solving algorithms.
 * 
 * Execution Flow:
 * 1. Read puzzle from file or command line
 * 2. Initialize board (triggers constraint propagation)
 * 3. Select and configure algorithm
 * 4. Run solver
 * 5. Validate and output results
 * 
 * Supported Algorithms:
 * - Algorithm 0: Single-threaded Ant Colony System (ACS)
 * - Algorithm 1: Backtracking search
 * - Algorithm 2: Parallel ACS with multiple sub-colonies
 ******************************************************************************/

#include "sudokuantsystem.h"
#include "parallelsudokuantsystem.h"
#include "backtracksearch.h"
#include "sudokusolver.h"
#include "board.h"
#include "arguments.h"
#include "constraintpropagation.h"
#include <iostream>
#include <fstream>
#include <string>
#include <iomanip>
#include <sstream>
using namespace std;

static string JsonEscape(const string &input)
{
	ostringstream out;
	for (char c : input)
	{
		switch (c)
		{
		case '\\': out << "\\\\"; break;
		case '"': out << "\\\""; break;
		case '\n': out << "\\n"; break;
		case '\r': out << "\\r"; break;
		case '\t': out << "\\t"; break;
		default: out << c; break;
		}
	}
	return out.str();
}

// ============================================================================
// SECTION 1: PUZZLE FILE READER
// ============================================================================

/*******************************************************************************
 * ReadFile - Read a Sudoku puzzle from a text file
 * 
 * File format:
 *   Line 1: order (e.g., 3 for 9x9, 4 for 16x16, 5 for 25x25)
 *   Line 2: ignored value
 *   Remaining: cell values (one per line)
 *     -1 represents empty cell (.)
 *     1-9 (for 9x9), 1-16 (for 16x16), etc. represent fixed values
 * 
 * Parameters:
 *   fileName - Path to the puzzle file
 * 
 * Returns: Puzzle string representation (e.g., "4.5...2.1...")
 ******************************************************************************/
string ReadFile( string fileName )
{
	char *puzString;
	ifstream inFile;
	inFile.open(fileName);
	if ( inFile.is_open() )
	{
		int order, idum;
		inFile >> order;
		int numCells = order*order*order*order;
		inFile >> idum;
		puzString = new char[numCells+1];
		for (int i = 0; i < numCells; i++)
		{
			int val;
			inFile >> val;
			if (val == -1)
				puzString[i] = '.';
			else if (order == 3)
				puzString[i] = '1' + (val - 1);
			else if (order == 4)
				if (val < 11)
					puzString[i] = '0' + val - 1;
				else
					puzString[i] = 'a' + val - 11;
			else
				puzString[i] = 'a' + val - 1;
		}
		puzString[numCells] = 0;
		inFile.close();
		string retVal = string(puzString);
		delete [] puzString;
		return retVal;
	}
	else
	{
		cerr << "could not open file: " << fileName << endl;
		return string();
	}
}

// ============================================================================
// SECTION 2: MAIN FUNCTION
// ============================================================================

/*******************************************************************************
 * main - Entry point for the Sudoku solver
 * 
 * This function orchestrates the entire solving process:
 * 1. Parse command-line arguments
 * 2. Load puzzle
 * 3. Initialize board (applies constraint propagation)
 * 4. Configure and run selected algorithm
 * 5. Validate and output results
 ******************************************************************************/
int main( int argc, char *argv[] )
{
	// ========================================================================
	// SECTION 2.1: COMMAND-LINE ARGUMENT PARSING
	// ========================================================================
	
	Arguments a( argc, argv );
	string puzzleString;
	
	// Option 1: Generate blank puzzle of specified order
	if ( a.GetArg("blank", 0) && a.GetArg("order", 0))
	{
		int order = a.GetArg("order", 0);
		if ( order != 0 )
			puzzleString = string(order*order*order*order,'.');
	}
	// Option 2: Read puzzle from command line or file
	else 
	{
		// Try reading from command-line argument
		puzzleString = a.GetArg(string("puzzle"),string());
		if ( puzzleString.length() == 0 )
		{
			// Try reading from file
			string fileName = a.GetArg(string("file"),string());
			puzzleString = ReadFile(fileName);
		}
		if ( puzzleString.length() == 0 )
		{
			cerr << "no puzzle specified" << endl;
			exit(0);
		}
	}
	
	// Reset CP timing before starting
	ResetCPTiming();
	
	// Initialize board (triggers constraint propagation)
	Board board(puzzleString);

	// Parse algorithm parameters
	int algorithm = a.GetArg("alg", 0);
	int timeOutSecs = a.GetArg("timeout", -1);
	int nAnts = a.GetArg("ants", 10);
	int nSubColonies = a.GetArg("subcolonies", 4);
	float q0 = a.GetArg("q0", 0.9f);
	float rho = a.GetArg("rho", 0.9f);  // ACS rho (used in Alg 0 and Alg 2)
	float evap = a.GetArg("evap", 0.005f);
	bool blank = a.GetArg("blank", false);
	bool verbose = a.GetArg("verbose", 0);
	bool showInitial = a.GetArg("showinitial", 0);
	bool jsonOutput = a.GetArg("json", 0);
	bool success;

	if ( timeOutSecs <= 0 )
	{
		int cellCount = board.CellCount();
		if ( cellCount == 81 )
			timeOutSecs = 5;
		else if ( cellCount == 256 )
			timeOutSecs = 20;
		else if ( cellCount == 625 )
			timeOutSecs = 120;
		else
			timeOutSecs = 120;
	}

	float solTime;
	Board solution;
	SudokuSolver *solver;
	
	// ========================================================================
	// SECTION 2.2: ALGORITHM SELECTION & CONFIGURATION
	// ========================================================================
	
	if ( algorithm == 0 )
		solver = new SudokuAntSystem( nAnts, q0, rho, 1.0f/board.CellCount(), evap);
	else if ( algorithm == 1 )
		solver = new BacktrackSearch();
	else if ( algorithm == 2 )
		solver = new ParallelSudokuAntSystem( nSubColonies, nAnts, q0, rho, 1.0f/board.CellCount(), evap);
	else
	{
		cerr << "Invalid algorithm: " << algorithm << ". Use 0 (single-thread ACS), 1 (backtracking), or 2 (parallel ACS)." << endl;
		exit(1);
	}

	// Optionally show the puzzle after constraint propagation
	if ( showInitial )
	{
		cout << "Initial constrained grid" << endl;
		cout << board.AsString(false, true) << endl;
	}
	
	// ========================================================================
	// SECTION 2.3: RUN SOLVER
	// ========================================================================
	
	success = solver->Solve(board, (float)timeOutSecs);
	solution = solver->GetSolution();
	solTime = solver->GetSolutionTime();

	// ========================================================================
	// SECTION 2.4: SOLUTION VALIDATION & OUTPUT
	// ========================================================================
	
	// Sanity check the solution
	string errorMessage;
	if ( success && !board.CheckSolution(solution) )
	{
		errorMessage = "solution not valid";
		if ( !jsonOutput )
		{
			cout << "solution not valid" << a.GetArg("file",string()) << " " << algorithm << endl;
			cout << "numfixedCells " << solution.FixedCellCount() << endl;

			string outString = solution.AsString(true );
			cout << outString << endl;
		}
		success = false;
	}
	
	// Get CP timing statistics
	float initialCPTime = GetInitialCPTime();
	float antCPTime = GetAntCPTime();
	int cpCallCount = GetCPCallCount();
	
	// For parallel algorithm, report average per-thread CP time
	// (Total CP time is accumulated across all threads, so divide by thread count)
	int numThreads = 1;
	if ( algorithm == 2 )
		numThreads = nSubColonies;
	
	float avgAntCPTime = antCPTime / numThreads;
	float totalCPTime = initialCPTime + antCPTime;

	int iterations = 0;
	bool communication = false;
	if ( algorithm == 0 )
	{
		SudokuAntSystem* antSolver = dynamic_cast<SudokuAntSystem*>(solver);
		if ( antSolver )
			iterations = antSolver->GetIterationsCompleted();
	}
	else if ( algorithm == 2 )
	{
		ParallelSudokuAntSystem* parallelSolver = dynamic_cast<ParallelSudokuAntSystem*>(solver);
		if ( parallelSolver )
		{
			iterations = parallelSolver->GetIterationsCompleted();
			communication = parallelSolver->GetCommunicationOccurred();
		}
	}
	
	if ( jsonOutput )
	{
		cout << fixed << setprecision(6);
		cout << "{";
		cout << "\"success\":" << (success ? "true" : "false") << ",";
		cout << "\"algorithm\":" << algorithm << ",";
		cout << "\"time\":" << solTime << ",";
		cout << "\"iterations\":" << iterations << ",";
		cout << "\"communication\":" << (communication ? "true" : "false") << ",";
		cout << "\"solution\":\"" << JsonEscape(solution.AsString(true)) << "\",";
		cout << "\"error\":\"" << JsonEscape(errorMessage) << "\",";
		cout << "\"cp_initial\":" << initialCPTime << ",";
		cout << "\"cp_ant_avg\":" << avgAntCPTime << ",";
		cout << "\"cp_ant_total\":" << antCPTime << ",";
		cout << "\"cp_calls\":" << cpCallCount << ",";
		cout << "\"cp_total\":" << totalCPTime;
		cout << "}" << endl;
		return 0;
	}

	// Output results
	if ( !verbose )
	{
		// Compact output format (for batch processing)
		cout << !success << endl << solTime << endl;
	}
	
	// Always output CP timing for parsing by scripts (both verbose and non-verbose)
	cout << "cp_initial: " << initialCPTime << endl;
	cout << "cp_ant: " << avgAntCPTime << endl;
	cout << "cp_calls: " << cpCallCount << endl;
	
	if ( verbose )
	{
		// Verbose output format (for interactive use)
		if ( !success )
		{
			cout << "failed in time " << solTime << endl;
			// Show iterations for algorithms 0 and 2
			if ( algorithm == 0 )
			{
				cout << "iterations: " << iterations << endl;
			}
			else if ( algorithm == 2 )
			{
				cout << "iterations: " << iterations << endl;
				cout << "communication: " << (communication ? "yes" : "no") << endl;
			}
		}
		else
		{
			cout << "Solution:" << endl;
			string outString = solution.AsString(true);
			cout << outString << endl;
			cout << "solved in " << solTime << endl;
			// Show iterations for algorithms 0 and 2
			if ( algorithm == 0 )
			{
				cout << "iterations: " << iterations << endl;
			}
			else if ( algorithm == 2 )
			{
				cout << "iterations: " << iterations << endl;
				cout << "communication: " << (communication ? "yes" : "no") << endl;
			}
		}
		
		// ====================================================================
		// COST-BENEFIT ANALYSIS: CONSTRAINT PROPAGATION OVERHEAD
		// ====================================================================
		cout << "\n=== Constraint Propagation Timing ===" << endl;
		cout << fixed << setprecision(6);
		cout << "Initial CP time:    " << initialCPTime << " s" << endl;
		cout << "Ant CP time:        " << antCPTime << " s" << endl;
		cout << "CP calls during ants: " << cpCallCount << endl;
		cout << "Total CP time:      " << totalCPTime << " s" << endl;
		cout << "Total solve time:   " << solTime << " s" << endl;
		
		float cpPercentage = (totalCPTime / solTime) * 100.0f;
		cout << "\nCP overhead:        " << cpPercentage << "% of total time" << endl;
		cout << "ACO computation:    " << (100.0f - cpPercentage) << "% of total time" << endl;
	}
}
