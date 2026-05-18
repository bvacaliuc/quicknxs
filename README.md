[![CI](https://github.com/bvacaliuc/quicknxs/actions/workflows/ci.yml/badge.svg?branch=next)](https://github.com/bvacaliuc/quicknxs/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/bvacaliuc/quicknxs/branch/next/graph/badge.svg)](https://codecov.io/gh/bvacaliuc/quicknxs)

# QuickNXS v1

Magnetism Reflectometer data reduction software (QuickNXS v1 fork).

## Usage

To run the gui, do the following:

```bash
make gui                    # runs the gui for Magnetism Reflectometer
make INSTRUMENT=ref_l gui   # runs the gui for Liquids Reflectometer
```

## Development

Install dependencies and run the test suite:

```bash
make install   # installs the pixi environment
make test      # runs the full pytest suite
make lint      # runs ruff static analysis
```
