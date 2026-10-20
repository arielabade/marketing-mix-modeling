# End to end: `make data train evaluate optimize test`
# Settings come from config/*.yaml and the environment (.env, see .env.example).
-include .env
export

PY ?= .venv/bin/python
ECOMMERCE_DIR ?= ../ecommerce
PROFILE ?= default

.PHONY: install data snapshot geolift train evaluate optimize report serve test test-e2e lint docs docker docker-run all

install:            ## virtualenv with the pinned stack
	python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

data:               ## generate + load the ecommerce database, build the dbt marts, run its tests
	$(MAKE) -C $(ECOMMERCE_DIR)

snapshot:           ## refresh the small parquet fixture (CI / e2e) from the live mart
	$(PY) -m mmm.data.snapshot

geolift:            ## geo-lift design (power, controls) and readout -> reports/geolift
	MMM_PROFILE=$(PROFILE) $(PY) -m mmm.jobs.geolift

train: geolift      ## fit the MMM without and with calibration, register, promote
	MMM_PROFILE=$(PROFILE) $(PY) -m mmm.jobs.train

evaluate:           ## time-ordered backtest + validation against the ground truth
	MMM_PROFILE=$(PROFILE) $(PY) -m mmm.jobs.evaluate

optimize:           ## next month's budget recommendation
	MMM_PROFILE=$(PROFILE) $(PY) -m mmm.jobs.optimize

report:             ## dashboard (docs/dashboard) and README figures
	MMM_PROFILE=$(PROFILE) $(PY) -m mmm.jobs.report

serve:              ## API on :8000
	$(PY) -m mmm.jobs.cli serve

test:               ## unit + contract tests (fast)
	$(PY) -m pytest -m "not e2e"

test-e2e:           ## whole pipeline on the small profile (samples MCMC, ~5 min)
	$(PY) -m pytest -m e2e

lint:
	$(PY) -m ruff check src tests

docs: report        ## rebuild everything under docs/ that is generated

docker:
	docker build -t tecela-mmm:latest .

docker-run:         ## API from the image, serving the local registry
	docker run --rm -p 8000:8000 -v $(PWD)/models:/app/models:ro tecela-mmm:latest serve

all: data train evaluate optimize report test
