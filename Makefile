# from mc-providers (removed make test), from es-tools, from sitemap-tools

# to create development environment: `make`
# to run pre-commit linting/formatting: `make lint`

VENVDIR=venv
VENVBIN=$(VENVDIR)/bin
VENVDONE=$(VENVDIR)/.done

help:
	@echo Usage:
	@echo "make install -- installs pre-commit hooks, dev environment"
	@echo "make lint -- runs pre-commit checks"
	@echo "make update -- update .pre-commit-config.yaml"
	@echo "make clean -- remove development environment"

## run pre-commit checks on all files
lint:	$(VENVDONE)
	$(VENVBIN)/pre-commit run --all-files

# create venv with project dependencies
# --editable skips installing project sources in venv
# pre-commit is in dev optional-requirements
install $(VENVDONE): $(VENVDIR) Makefile pyproject.toml
	$(VENVBIN)/python3 -m pip install --editable '.[dev]'
	$(VENVBIN)/pre-commit install
	touch $(VENVDONE)

$(VENVDIR):
	python3 -m venv $(VENVDIR)

## update .pre-commit-config.yaml
update:	$(VENVDONE)
	$(VENVBIN)/pre-commit autoupdate

## build requirements.txt (requied by Heroku buildpack?)
requirements:
	$(VENVBIN)/pip-compile -o requirements.txt.tmp --strip-extras pyproject.toml
	mv requirements.txt.tmp requirements.txt

## clean up development environment
clean:
	-$(VENVBIN)/pre-commit clean
	rm -rf $(VENVDIR) build *.egg-info .pre-commit-run.sh.log \
		__pycache__ .mypy_cache
