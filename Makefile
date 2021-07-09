run:
	python -m uvicorn main:app --reload

lint:
	flake8 ./
	mypy --install-types ./
	isort -l 120 ./
