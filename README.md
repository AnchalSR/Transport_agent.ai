# Transport Agent

A complete end-to-end FastAPI + vanilla JavaScript chatbot for Lucknow bus routes using CSV data.

## Stack
- Backend: Python + FastAPI
- Frontend: HTML + CSS + Vanilla JavaScript
- LLM API: Hugging Face Inference API (free tier)
- Model: `tiiuae/falcon-7b-instruct`
- Data: single CSV file `data/raw/bus_routes.csv`
- Communication: REST via `POST /chat`

## Architecture
- `models/intent_parser.py`
  - Uses Hugging Face model for greeting detection and free-text intent extraction only.
  - Reads token only from `os.getenv("HF_API_TOKEN")`.
  - Expected travel JSON: `{ "from": "", "to": "", "after_time": "" }`.
  - Falls back to deterministic rule parsing if API output is missing/invalid.
- `agent/transport_agent.py`
  - Loads CSV at startup.
  - Normalizes user input and applies aliases (`airport`, `station`, `railway station`, `gomtinagar`).
  - Handles minor spelling mistakes with simple similarity matching.
  - Deterministically selects best matching route.
  - Returns `bus_number`, `departure_time`, `duration_minutes`, and route `stops`.
- `api/server.py`
  - Stateless backend endpoint: `POST /chat`.
  - Supports:
    - free-text chat
    - options payload retrieval (`__OPTIONS__`) for guided UI.
  - Returns route answers from CSV only.
- `ui/chat.js`
  - Handles all guided conversation state in frontend only.
  - Guided flow:
    1. Ask current location
    2. Show selectable `from_stop` options from CSV
    3. Ask destination
    4. Show selectable `to_stop` options from CSV
    5. Send constructed query to backend
  - Adds voice input via browser Web Speech API.

## Run
1. Install dependencies:
   `pip install -r requirements.txt`
2. Ensure environment variable exists:
   - `HF_API_TOKEN`
3. Start server:
   `uvicorn api.server:app --reload`
4. Open:
   `http://127.0.0.1:8000`

## API
### `POST /chat`
Request:
```json
{ "message": "bus from gomtinagar to airport" }
```

Example response:
```json
{
  "reply": "Bus 25A departs at 10:30. Duration 40 minutes. Stops: Gomti Nagar -> Alambagh -> Amausi Airport",
  "route": {
    "bus_number": "25A",
    "departure_time": "10:30",
    "duration_minutes": 40,
    "stops": ["Gomti Nagar", "Alambagh", "Amausi Airport"]
  },
  "from_options": ["Alambagh", "Aminabad", "Aliganj", "Charbagh", "Gomti Nagar", "Hazratganj", "Indira Nagar", "Mahanagar", "Rajajipuram", "Telibagh", "Vikas Nagar"],
  "to_options": ["Alambagh", "Aliganj", "Amausi Airport", "Aminabad", "Charbagh", "Chowk", "Gomti Nagar", "Hazratganj", "Indira Nagar"]
}
```
