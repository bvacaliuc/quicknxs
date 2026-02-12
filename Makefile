.PHONY: gui install test test-core test-gui test-db lint clean

gui: install
	pixi run python scripts/quicknxs

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

lint: install
	pixi run ruff check quicknxs/

clean:
	rm -rf __pycache__ .pytest_cache *.egg-info
