# perpdex-market-maker

## Setup

WIP

## Run

```
python main.py run
```

## Test

```
git submodule update --init --recursive

# compile deps contract
cd deps/perpdex-contract
npm install

# run tests
docker compose run --rm py-test python -m pytest tests
```
