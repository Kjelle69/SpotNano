# Web Skill

The dashboard is an operator surface, not an autonomous control brain.

Requirements:
- Provide emergency stop on the main page.
- Provide reset stop only as an explicit operator action.
- Send all command buttons to the API, then through `CommandManager`.
- Show current state, stop status, fake/real mode, blue snake state, last command, and recent logs.
- Do not hide rejected commands.

The web layer must never call `SpotInterface` directly.

