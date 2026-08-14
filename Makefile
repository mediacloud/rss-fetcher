# from mc-providers (removed make test), from es-tools, from sitemap-tools

# to create development environment: `make`
# to run pre-commit linting/formatting: `make lint`

VENVDIR=.venv
VENVBIN=$(VENVDIR)/bin
VENVDONE=$(VENVDIR)/.done

# trying uv:
# * Faster than pip-compile
#	(so not painful to run on first checkout)
# * Dokku supports uv (if uv.lock exists)
# * pip-compile is broken by pip v26
# * Removes circular dependency for pip-compile
# * Can install alternate python versions??

# Haven't settled on best way to install / check if uv installed.
# ("pip install uv" is one possibility!)

help:
	@echo Usage:
	@echo "make install -- installs pre-commit hooks, dev environment"
	@echo "make lint -- runs pre-commit checks"
	@echo "make requirements -- create requirements.txt from pyproject.toml"
	@echo "make update -- update .pre-commit-config.yaml"
	@echo "make clean -- remove development environment"
	@echo "make deploy -- run deployment script"

## run pre-commit checks on all files
lint:	$(VENVDONE) uv.lock
	$(VENVBIN)/pre-commit run --all-files

# prevent creation of install from install.sh:
.PHONY: install

# create venv with project dependencies
# --editable skips installing project sources in venv
# pre-commit is in dev optional-requirements

install: $(VENVDONE)

deploy:	lint
	$(VENVBIN)/python dokku-scripts/deploy.py deploy

# currently running mypy from dev venv:
$(VENVDONE): Makefile uv.lock
	uv sync --extra dev --extra deploy --extra mypy
	$(VENVBIN)/pre-commit install
	touch $(VENVDONE)

uv.lock: pyproject.toml
	uv lock

## update .pre-commit-config.yaml
update:	$(VENVDONE)
	$(VENVBIN)/pre-commit autoupdate

## build uv.lock (used by buildpack)
requirements: uv.lock

## clean up development environment
clean:
	-$(VENVBIN)/pre-commit clean
	rm -rf $(VENVDIR) build *.egg-info .pre-commit-run.sh.log \
		__pycache__ .mypy_cache
