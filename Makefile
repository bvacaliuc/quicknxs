.PHONY: gui install test test-core test-gui test-db test-h5 lint clean reduce-headless strace strace-full strace-reduce load-test batch-load-test

INSTRUMENT ?= ref_m

gui: install
	pixi run python scripts/quicknxs --instrument $(INSTRUMENT)

install:
	pixi install

test: install
	pixi run test

test-core: install
	pixi run test-core

test-gui: install
	pixi run test-gui

test-db: install
	pixi run test-db

test-h5: install
	pixi run pytest tests/test_event_h5.py -v --timeout=120

lint: install
	pixi run ruff check quicknxs/

clean:
	rm -rf __pycache__ .pytest_cache *.egg-info

reduce-headless: install
	pixi run python scripts/reduce_headless.py

# Diagnostic targets for memory fault analysis.
# Usage:
#   make strace          - trace memory-related syscalls in the GUI app
#   make strace-reduce   - trace memory-related syscalls in headless reduction
#   make strace-full     - trace all syscalls (large output)
#
# Output files are written to strace.<PID> (one per process).
# The Python application PID is typically the highest-numbered PID file.
# After a crash (exit 137 = OOM kill), examine the Python process log:
#   ls -la strace.*                       # find the files
#   tail -100 strace.<highest_pid>        # see last syscalls before kill
#   grep -c 'mmap\|brk' strace.<pid>      # count memory allocations

STRACE_MEMORY_TRACE = -e trace=memory,signal,process
STRACE_OPTS = -f -ff -o strace -t -T

strace: install
	rm -f strace.*
	strace $(STRACE_OPTS) $(STRACE_MEMORY_TRACE) pixi run python scripts/quicknxs; \
	echo ""; \
	echo "=== strace complete (exit $$?) ==="; \
	echo "Output files:"; \
	ls -lhS strace.* 2>/dev/null || echo "  (no output files found)"; \
	echo ""; \
	echo "To analyze: tail -100 strace.<PID>"

strace-reduce: install
	rm -f strace.*
	strace $(STRACE_OPTS) $(STRACE_MEMORY_TRACE) pixi run python scripts/reduce_headless.py; \
	echo ""; \
	echo "=== strace complete (exit $$?) ==="; \
	echo "Output files:"; \
	ls -lhS strace.* 2>/dev/null || echo "  (no output files found)"; \
	echo ""; \
	echo "To analyze: tail -100 strace.<PID>"

strace-full: install
	rm -f strace.*
	strace $(STRACE_OPTS) pixi run python scripts/quicknxs; \
	echo ""; \
	echo "=== strace complete (exit $$?) ==="; \
	echo "Output files:"; \
	ls -lhS strace.* 2>/dev/null || echo "  (no output files found)"

load-test: install
	@test -n "$(FILE)" || (echo "Usage: make load-test FILE=/path/to/file.nxs"; exit 1)
	pixi run python scripts/load_test.py --file "$(FILE)"

batch-load-test: install
	@test -n "$(DIR)" || (echo "Usage: make batch-load-test DIR=/path/to/data/"; exit 1)
	pixi run python scripts/load_test.py --dir "$(DIR)" $(if $(PATTERN),--pattern "$(PATTERN)",)
