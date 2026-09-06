"""What is served to a browser.

Only `spa/` now -- the built React app, which `zaco/main.py` mounts at `/`. It is a build
artefact, gitignored, and produced inside the image rather than copied from anybody's machine.

This package held the server-rendered interface until the React port replaced it: fourteen Jinja
templates, a stylesheet and 104 lines of JavaScript that built HTML with `innerHTML`. The API it
called is unchanged, which is the whole argument for API-first (D1).
"""
