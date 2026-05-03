.PHONY: test adversarial red-team smoke-live

test:
	pytest

adversarial:
	pytest tests/test_responder.py -m adversarial -v

red-team:
	python -m yarbo.cli red-team

smoke-live:
	python tests/smoke/synthetic_day.py --live
