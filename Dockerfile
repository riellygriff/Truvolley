FROM python:3.10.7-slim-buster as builder

RUN apt-get update && apt-get install -y
RUN mkdir code
WORKDIR code
RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH
RUN pip install --upgrade pip
RUN pip install poetry
RUN poetry config virtualenvs.create false
COPY pyproject.toml .
COPY README.md .
### UNCOMMENT TO CACHE REQUIREMENTS WHILE DEVELOPING
### poetry export -o requirements.txt --without-hashes
### RUN pip install -r requirements.txt
###
COPY Truvolley ./Truvolley
RUN poetry install

FROM python:3.10.7-slim-buster
RUN apt-get update && apt-get install -y git
COPY --from=builder /venv /venv
ENV PATH=/venv/bin:$PATH
