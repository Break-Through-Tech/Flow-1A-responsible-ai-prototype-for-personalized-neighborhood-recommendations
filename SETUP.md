# Setup

## Requirements

- Python 3.11
- Git
- VS Code with the Python and Jupyter extensions

## 1. Clone

```
git clone https://github.com/Break-Through-Tech/Flow-1A-responsible-ai-prototype-for-personalized-neighborhood-recommendations.git flow1a
cd flow1a
```

## 2. Virtual environment

Windows (PowerShell):
```
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Mac / Linux:
```
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now start with `(.venv)`.

## 3. Install packages

```
pip install -r requirements.txt
```

## 4. Set up .env

Copy `.env.example` to `.env` and fill in your keys.

Windows: `copy .env.example .env`
Mac / Linux: `cp .env.example .env`

`GEMINI_API_KEY` and `CENSUS_API_KEY` are only needed for October. `.env` is gitignored.

## 5. Check it worked

Open `notebooks/00_azizbek_starter_check.ipynb`. Click "Select Kernel" (top right) → "Python Environments..." → pick `.venv`. Run the first cell. You should see:

```
Python: 3.11.1
pandas: 3.0.5
numpy: 2.4.6
scikit-learn: 1.9.1
```
