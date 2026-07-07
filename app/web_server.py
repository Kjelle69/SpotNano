from fastapi import APIRouter, Form
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app import audio_out
from app.audio_in import parse_voice_command, record_mic_test
from app.auto_vision import AutoVisionService
from app.camera import camera
from app.command_manager import CommandManager
from app.config import config
from app.logger import event_logger
from app.spot_interface import create_spot_interface
from app.state import shared_state
from app.vision_moondream import VisionService


router = APIRouter()
templates = Jinja2Templates(directory="templates")
spot = create_spot_interface(shared_state)
command_manager = CommandManager(shared_state, spot)
vision_service = VisionService(camera)
auto_vision_service = AutoVisionService(shared_state, vision_service)


class SayRequest(BaseModel):
    text: str


class VoiceTextRequest(BaseModel):
    text: str


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/video_feed")
def video_feed() -> StreamingResponse:
    return StreamingResponse(camera.mjpeg_stream(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/api/status")
def api_status() -> dict:
    status = shared_state.snapshot()
    status["app_version"] = config.app_version
    status["audio_input_enabled"] = config.audio_in_enabled
    status["audio_in_backend"] = config.audio_in_backend
    status["bark_sounds"] = audio_out.bark_sound_status()
    status.update(spot.status())
    return status


@router.get("/api/spot/status")
def api_spot_status() -> dict:
    return spot.status()


@router.post("/api/spot/connect")
def api_spot_connect() -> JSONResponse:
    if not getattr(spot, "is_real", False):
        return JSONResponse({"accepted": False, "status": "fake_mode", **spot.status()})
    result = spot.connect()
    return JSONResponse({"accepted": bool(result.get("spot_connected")), "status": "connected" if result.get("spot_connected") else "unavailable", **result})


@router.get("/api/logs")
def api_logs() -> dict:
    return {"logs": event_logger.recent()}


@router.post("/api/stop")
def api_stop() -> JSONResponse:
    result = command_manager.handle("STOP", source="web")
    return JSONResponse(result.__dict__)


@router.post("/api/reset_stop")
def api_reset_stop() -> JSONResponse:
    result = command_manager.reset_stop()
    return JSONResponse(result.__dict__)


@router.post("/api/command")
def api_command(command: str = Form(...)) -> JSONResponse:
    result = command_manager.handle(command, source="web")
    return JSONResponse(result.__dict__)


@router.post("/api/vision/analyze_once")
def api_vision_analyze_once() -> JSONResponse:
    result = vision_service.analyze_once(source="manual")
    return JSONResponse(result)


@router.post("/api/vision/toggle_auto")
def api_vision_toggle_auto() -> JSONResponse:
    return JSONResponse(auto_vision_service.toggle())


@router.post("/api/audio/beep")
def api_audio_beep() -> JSONResponse:
    audio_out.beep()
    shared_state.update(last_audio_phrase="beep")
    event_logger.event("audio_api", action="beep")
    return JSONResponse({"accepted": True, "action": "beep"})


@router.post("/api/audio/bark")
def api_audio_bark() -> JSONResponse:
    audio_out.bark()
    shared_state.update(last_audio_phrase="bark")
    event_logger.event("audio_api", action="bark")
    return JSONResponse({"accepted": True, "action": "bark"})


@router.post("/api/audio/bark_ok")
def api_audio_bark_ok() -> JSONResponse:
    audio_out.bark_ok()
    shared_state.update(last_audio_phrase="bark_ok")
    event_logger.event("audio_api", action="bark_ok")
    return JSONResponse({"accepted": True, "action": "bark_ok"})


@router.post("/api/audio/bark_no")
def api_audio_bark_no() -> JSONResponse:
    audio_out.bark_no()
    shared_state.update(last_audio_phrase="bark_no")
    event_logger.event("audio_api", action="bark_no")
    return JSONResponse({"accepted": True, "action": "bark_no"})


@router.post("/api/audio/bark_warn")
def api_audio_bark_warn() -> JSONResponse:
    audio_out.bark_warn()
    shared_state.update(last_audio_phrase="bark_warn")
    event_logger.event("audio_api", action="bark_warn")
    return JSONResponse({"accepted": True, "action": "bark_warn"})


@router.post("/api/audio/bark_snake")
def api_audio_bark_snake() -> JSONResponse:
    audio_out.bark_snake()
    shared_state.update(last_audio_phrase="bark_snake")
    event_logger.event("audio_api", action="bark_snake")
    return JSONResponse({"accepted": True, "action": "bark_snake"})


@router.post("/api/audio/say")
def api_audio_say(payload: SayRequest) -> JSONResponse:
    audio_out.speak(payload.text)
    shared_state.update(last_audio_phrase=payload.text)
    event_logger.event("audio_api", action="say", text=payload.text)
    return JSONResponse({"accepted": True, "action": "say", "text": payload.text})


@router.post("/api/audio/mic_test")
def api_audio_mic_test() -> JSONResponse:
    return JSONResponse(record_mic_test(duration_s=3.0))


@router.post("/api/audio/voice_text")
def api_audio_voice_text(payload: VoiceTextRequest) -> JSONResponse:
    result = handle_voice_text(payload.text, source="voice_text")
    return JSONResponse(result)


def handle_voice_text(text: str, source: str = "voice") -> dict:
    phrase = str(text)
    command = parse_voice_command(phrase)
    shared_state.update(last_audio_phrase=phrase, last_parsed_voice_command=command or "")
    event_logger.event("voice_text", source=source, phrase=phrase, command=command)

    if command is None:
        return {
            "accepted": False,
            "phrase": phrase,
            "parsed_command": None,
            "command_result": None,
            "status": "unrecognized",
            "message": "No whitelisted voice command found",
        }

    command_result = command_manager.handle(command, source=source)
    result = command_result.__dict__
    event_logger.event(
        "voice_command_result",
        source=source,
        phrase=phrase,
        command=command,
        accepted=command_result.accepted,
        status=command_result.status,
        message=command_result.message,
    )
    return {
        "phrase": phrase,
        "parsed_command": command,
        "command_result": result,
        **result,
    }
