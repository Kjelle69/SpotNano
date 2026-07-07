from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.audio_in import parse_voice_command, start_audio_listener, stop_audio_listener
from app.camera import camera
from app.config import config
from app.web_server import auto_vision_service, command_manager, router, shared_state, spot


@asynccontextmanager
async def lifespan(app: FastAPI):
    shared_state.update(
        audio_input_enabled=config.audio_in_enabled,
        audio_in_backend=config.audio_in_backend,
    )
    camera.start()
    auto_vision_service.start()
    start_audio_listener(
        command_callback=lambda command, phrase: command_manager.handle(command, source="audio_listener"),
        phrase_callback=lambda phrase: shared_state.update(
            last_audio_phrase=phrase,
            last_parsed_voice_command=parse_voice_command(phrase) or "",
        ),
    )
    yield
    stop_audio_listener()
    auto_vision_service.stop()
    camera.stop()
    spot.close()


app = FastAPI(title=config.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(router)
