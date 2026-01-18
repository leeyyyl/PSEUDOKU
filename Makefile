CC=g++
CFLAGS=-c -O3 -std=c++11 -pthread

sudokusolver : board.o constraintpropagation.o sudokuant.o sudokuantsystem.o parallelsudokuantsystem.o backtracksearch.o solvermain.o 	
	$(CC) -pthread -o sudokusolver obj/board.o obj/constraintpropagation.o obj/sudokuant.o obj/sudokuantsystem.o obj/parallelsudokuantsystem.o obj/backtracksearch.o obj/solvermain.o
board.o: src/board.cpp src/board.h src/constraintpropagation.h
	$(CC) $(CFLAGS) src/board.cpp -o obj/board.o
constraintpropagation.o: src/constraintpropagation.cpp src/constraintpropagation.h src/board.h
	$(CC) $(CFLAGS) src/constraintpropagation.cpp -o obj/constraintpropagation.o
sudokuant.o: src/sudokuant.cpp
	$(CC) $(CFLAGS) src/sudokuant.cpp -o obj/sudokuant.o
sudokuantsystem.o: src/sudokuantsystem.cpp
	$(CC) $(CFLAGS) src/sudokuantsystem.cpp -o obj/sudokuantsystem.o
parallelsudokuantsystem.o: src/parallelsudokuantsystem.cpp
	$(CC) $(CFLAGS) src/parallelsudokuantsystem.cpp -o obj/parallelsudokuantsystem.o
backtracksearch.o: src/backtracksearch.cpp src/backtracksearch.h
	$(CC) $(CFLAGS) src/backtracksearch.cpp -o obj/backtracksearch.o
solvermain.o: src/solvermain.cpp
	$(CC) $(CFLAGS) src/solvermain.cpp -o obj/solvermain.o
clean :
	rm sudokusolver obj/*.o
