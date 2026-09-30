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
	@echo "make requirements -- create uv.lock from pyproject.toml"
	@echo "make update -- update .pre-commit-config.yaml"
	@echo "make clean -- remove development environment"
	@echo "make deploy -- run deployment script"
	@echo "make list-outdated -- list outdated dependencies"

## run pre-commit checks on all files
lint:	$(VENVDONE)
	$(VENVBIN)/pre-commit run --all-files

# prevent creation of install from install.sh:
.PHONY: install

## create venv with project dependencies
install: $(VENVDONE)

## deploy code via Dokku
deploy:	lint
	$(VENVBIN)/python dokku-scripts/deploy.py deploy

# pre-commit is in dev "extra" requiements
# currently running mypy in dev venv
$(VENVDONE): Makefile uv.lock .python-version
	uv sync --python `cat .python-version` --extra dev --extra deploy --extra mypy
	$(VENVBIN)/pre-commit install
	touch $(VENVDONE)

# also updated via pre-commit
uv.lock: pyproject.toml
	uv lock

## update .pre-commit-config.yaml
update:	$(VENVDONE)
	$(VENVBIN)/pre-commit autoupdate

## build uv.lock (used by buildpack)
# uv.lock also updated by pre-commit
requirements: uv.lock

# list outdated requirements
# https://github.com/astral-sh/uv/issues/6794
# discusses automagic update
list-outdated:
	uv pip list --outdated

## clean up development environment
clean:
	-$(VENVBIN)/pre-commit clean
	rm -rf $(VENVDIR) build *.egg-info .pre-commit-run.sh.log \
		__pycache__ .mypy_cache
