# Create requirements files for both project and build
create-requirements:
    poetry export -o requirements.txt --only=main --without-hashes

# Run all repo setup
setup-repo: && create-requirements
    poetry add --group dev nox pre-commit pytest pytest-cov ruff
    poetry add prefect
    
    poetry add prefect-github
    poetry add prefect-gcp
    poetry install -v
    

# Create default work pool
create-work-pool:
    poetry run prefect work-pool create \
    cloud-run-pool --type cloud-run
    

# Run tests via nox
test:
    poetry run nox -s tests

# Run linting live and see how changes made effect outputs
live-lint:
    poetry run ruff . --fix --watch

# Format all files using black
format:
    poetry run black .

# Lint repo using pre-commit hooks
lint: format
    poetry run ruff . --fix

# Run pre-commit hooks
pre-commit:
    poetry run pre-commit run --all


home_dir := env_var('HOME')
# Build Docker Image
build-docker:
    docker build . -t riellygriff21/truvolley --platform linux/amd64

# Push Docker Image
push-docker:
    docker push riellygriff21/truvolley:latest

