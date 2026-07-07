# Vision Skill

The vision system uses a USB webcam through OpenCV/V4L2.

Initial task:
Detect whether a blue toy snake / blue dog toy shaped like a snake is visible.

Use Moondream through Ollama `/api/chat`.

Prompt format should force a very simple answer:

```text
BLUE_SNAKE: YES
BLUE_SNAKE: NO
```

Do not rely on free-form JSON unless necessary. Moondream may not always produce valid JSON.

Vision service must update shared state only. It must not command Spot directly.

Vision state fields:
- `blue_snake_visible`
- `blue_snake_stable`
- `last_vision_raw`
- `last_vision_time`
- `last_vision_duration_s`
- `last_frame_time`

Implementation notes:
- Use V4L2 backend: `cv2.VideoCapture(0, cv2.CAP_V4L2)`
- Use frame resize before sending to Moondream, e.g. 320x240
- Use JPEG quality around 60 to reduce load
- Use digital brightness enhancement carefully; avoid overexposure
- Add OpenCV blue/turquoise pre-filter later to reduce Moondream calls

Never let vision directly send movement commands.

