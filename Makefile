.PHONY: static

develop: update-submodules
	npm install
	bower install
	pip install -e . --use-mirrors
	make install-test-requirements
	alembic upgrade head

install-test-requirements:
	pip install "file://`pwd`#egg=changes[tests]" --use-mirrors

update-submodules:
	git submodule init
	git submodule update

test: develop lint
	@echo "Running Python tests"
	py.test tests
	@echo ""

lint:
	@echo "Linting Python files"
	PYFLAKES_NODOCTEST=1 flake8 changes tests
	@echo ""

test-full: develop lint
	py.test --junitxml=results.xml --cov-report=xml --cov=. tests

resetdb:
	dropdb --if-exists changes
	createdb -E utf-8 changes
	alembic upgrade head

static:
	r.js -o build.js
