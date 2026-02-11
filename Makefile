.PHONY: install test test-core test-gui lint clean

install:
	pixi install

test: install
	pixi run test

test-core: install
	pixi run test-core

test-gui: install
	pixi run test-gui

lint: install
	pixi run ruff check quicknxs/

clean:
	rm -rf __pycache__ .pytest_cache *.egg-info
