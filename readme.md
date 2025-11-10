### how to run a dev env
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

#### set OpenAI key
export OPENAI_API_KEY="sk-..."   # Windows PowerShell: $env:OPENAI_API_KEY="sk-..."

#### run FastAPI
uvicorn app:app --host 0.0.0.0 --port 8000 --reload