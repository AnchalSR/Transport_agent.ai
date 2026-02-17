from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.transport_agent import TransportAgent
from models.intent_parser import IntentParser


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    route: Optional[Dict[str, Any]] = None
    from_options: List[str]
    to_options: List[str]


app = FastAPI(title="Lucknow Transport Chatbot")

base_dir = Path(__file__).resolve().parents[1]
ui_dir = base_dir / "ui"

app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")

intent_parser = IntentParser()
transport_agent = TransportAgent()


def _option_payload() -> Dict[str, List[str]]:
    return transport_agent.get_options()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(ui_dir / "index.html"))


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    text = req.message.strip()
    options = _option_payload()

    if text == "__OPTIONS__":
        return ChatResponse(reply="", route=None, **options)

    intent = intent_parser.parse_intent(text)

    if intent["type"] == "greeting":
        return ChatResponse(
            reply="Hello! You can ask me about bus routes in Lucknow.",
            route=None,
            **options,
        )

    if intent["type"] == "route_query":
        if not intent["from"] or not intent["to"]:
            return ChatResponse(
                reply="Please tell me the starting place and destination.",
                route=None,
                **options,
            )

        route = transport_agent.find_route(intent["from"], intent["to"], intent["after_time"])
        if route is None:
            alternative = transport_agent.suggest_alternative(intent["from"], intent["to"], intent["after_time"])
            if alternative is None:
                return ChatResponse(reply="No matching bus route found.", route=None, **options)

            leg1 = alternative["leg1"]
            leg2 = alternative["leg2"]
            transfer = alternative["transfer_stop"]
            reply = (
                "No direct bus route found. "
                f"Alternate route: Take Bus {leg1['bus_number']} at {leg1['departure_time']} "
                f"from {leg1['stops'][0]} to {transfer}. "
                f"Then take Bus {leg2['bus_number']} at {leg2['departure_time']} "
                f"from {transfer} to {alternative['to_stop']}."
            )
            return ChatResponse(reply=reply, route=alternative, **options)

        stops_text = " -> ".join(route["stops"])
        reply = (
            f"Bus {route['bus_number']} departs at {route['departure_time']}. "
            f"Duration {route['duration_minutes']} minutes. "
            f"Stops: {stops_text}"
        )
        return ChatResponse(reply=reply, route=route, **options)

    return ChatResponse(
        reply="Please tell me the starting place and destination.",
        route=None,
        **options,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="127.0.0.1", port=8000, reload=True)
