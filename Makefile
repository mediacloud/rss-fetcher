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
	@echo "make deploy -- run deployment script"
	@echo ""
	@echo "make mc-relock -- update mediacloud private package .latest git hashes"
	@echo "make clean -- remove development environment"
	@echo "make list-outdated -- list outdated dependencies"
	@echo "make update-pre-commit -- update .pre-commit-config.yaml"
	@echo "make relock-all -- relock ALL dependencies in pyproject.toml to latest"

## run pre-commit checks on all files
lint:	$(VENVDONE)
	$(VENVBIN)/pre-commit run --all-files

# prevent creation of install from install.sh:
.PHONY: install

## deploy code via Dokku
deploy:	lint
	$(VENVBIN)/python dokku-scripts/deploy.py deploy

# pre-commit is in dev "extra" requiements
# currently running mypy in dev venv
install $(VENVDONE): Makefile uv.lock .python-version
	uv sync --python `cat .python-version` --extra dev --extra deploy --extra mypy
	$(VENVBIN)/pre-commit install
	touch $(VENVDONE)

# check for changed requirements
uv.lock: pyproject.toml
	uv lock

## update mediacloud private package .latest git hashes; run by pre-commit
mc-relock: uv.lock
	uv lock `awk '/git.https:\/\/github.com\/mediacloud\// { print }' pyproject.toml | sed -e 's/^ *"/--upgrade-package /' -e 's/ *@.*//'`

## update .pre-commit-config.yaml
update-pre-commit:	$(VENVDONE)
	$(VENVBIN)/pre-commit autoupdate

## build uv.lock
requirements: uv.lock

# list outdated requirements
# https://github.com/astral-sh/uv/issues/6794
# discusses automagic update
list-outdated:
	uv pip list --outdated

# update ALL packages referenced in pyproject.toml
relock-all:
	uv lock --upgrade

## clean up development environment
clean:
	-$(VENVBIN)/pre-commit clean
	rm -rf $(VENVDIR) build *.egg-info .pre-commit-run.sh.log \
		__pycache__ .mypy_cache
