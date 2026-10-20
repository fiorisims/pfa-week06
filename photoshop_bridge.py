"""Run ExtendScript (JSX) inside the live Adobe Photoshop session over COM.

Usage:
    python photoshop_bridge.py script.jsx          run a file in Photoshop
    python photoshop_bridge.py -c "$.writeln(1)"   run inline JSX
    python photoshop_bridge.py --ping              check the bridge responds
    python photoshop_bridge.py --debug script.jsx  open the PS debugger on error

In PowerShell, inline code must go through the stop-parsing symbol
(`python photoshop_bridge.py --% -c "$.writeln(1)"`), because PS 5.1 strips the
double quotes inside a single-quoted argument; file mode needs no tricks.

Photoshop has no script port like Maya's command port; the bridge talks to the
Photoshop scripting engine directly and launches Photoshop if it is not running.
On Windows it uses COM (`Photoshop.Application` -> `DoJavaScript`); on macOS it
drives ExtendScript through AppleScript (`osascript` + `do javascript`), so no
extra tools are needed. (Linux has no Photoshop, so only file mode is usable.)
Output (from `$.writeln(...)`), errors and the value of a `__result__` variable
come back in _ps_out.txt.

Inside a script, use the Photoshop DOM (`app`, `Document`, `Layer`, ...) and end
with `__result__ = <value>` to send a value back. `#target` / `#include`
directives are not supported (the source is eval'd).
"""

import argparse
import glob
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK = HERE / "photoshop_hook.jsx"
IN = HERE / "_ps_in.jsx"
OUT = HERE / "_ps_out.txt"
RUNNER = HERE / "_ps_run.jsx"       # macOS: the hook + call written as one file
PROGID = "Photoshop.Application"
EXEC_MODE = 1          # psJavaScriptExecutionMode.psNeverShowDebugger
DEBUG_MODE = 2         # psJavaScriptExecutionMode.psDebuggerOnError

MAC_APPS = "/Applications/Adobe Photoshop*.app"
MAC_TIMEOUT = 600


def to_js(path):
    return str(path).replace("\\", "/")


def _mac_photoshop_app():
    """Newest installed Photoshop app bundle on macOS, or None."""
    apps = sorted(glob.glob(MAC_APPS))
    return apps[-1] if apps else None


def connect(debug_mode):
    """Attach to (or launch) Photoshop. Returns a handle for ``run``."""
    if sys.platform.startswith("win"):
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject(PROGID)
        except pythoncom.com_error:
            print("[bridge] Photoshop is not running - launching it "
                  "(the first call can take a minute)...", file=sys.stderr)
            try:
                app = win32com.client.Dispatch(PROGID)
            except pythoncom.com_error as exc:
                raise RuntimeError(
                    "cannot talk to Photoshop via COM (%s).\n"
                    "Is Adobe Photoshop installed? Try launching it once by hand."
                    % exc) from exc
        app.DoJavaScript("1", [], debug_mode)   # touch the engine early
        return app

    if sys.platform == "darwin":
        app = _mac_photoshop_app()
        if not app:
            raise RuntimeError(
                "Adobe Photoshop was not found in /Applications.\n"
                "Install it, or the app bundle is named unexpectedly.")
        return app                               # the bundle path is the handle

    raise RuntimeError(
        "Photoshop scripting needs Windows (COM) or macOS (AppleScript); "
        "this platform (%s) can't drive Photoshop." % sys.platform)


def _mac_do_javascript(app_path, script, debug):
    """Run ExtendScript in Photoshop on macOS via osascript."""
    name = Path(app_path).stem                   # e.g. "Adobe Photoshop 2026"
    RUNNER.write_text(script, encoding="utf-8")
    lines = [
        'set jsxFile to (POSIX file "%s")' % RUNNER.as_posix(),
        "set jsxCode to read jsxFile as \u00abclass utf8\u00bb",
        'tell application "%s" to do javascript jsxCode%s'
        % (name, " showing debugger" if debug else ""),
    ]
    cmd = ["osascript"]
    for line in lines:
        cmd += ["-e", line]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=MAC_TIMEOUT)
    except FileNotFoundError as exc:
        raise RuntimeError("osascript not found (%s)." % exc) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Photoshop (macOS) timed out after %ds."
                           % MAC_TIMEOUT) from exc
    if proc.returncode != 0:
        raise RuntimeError("Photoshop (macOS) error: %s"
                           % ((proc.stderr or proc.stdout or "").strip()
                              or "unknown error"))


def run(code, debug=False, app=None):
    """Execute JSX in Photoshop; return the captured output (or raise RuntimeError)."""
    if code.startswith("\ufeff"):
        code = code.lstrip("\ufeff")
    IN.write_text(code, encoding="utf-8")
    OUT.unlink(missing_ok=True)

    if app is None:
        app = connect(DEBUG_MODE if debug else EXEC_MODE)

    hook = HOOK.read_text(encoding="utf-8-sig")
    script = "%s\n__bridge_run__(\"%s\", \"%s\");" % (hook, to_js(IN), to_js(OUT))

    if isinstance(app, str):                     # macOS app-bundle path
        _mac_do_javascript(app, script, debug)
    else:                                        # Windows COM object
        app.DoJavaScript(script, [], DEBUG_MODE if debug else EXEC_MODE)

    if not OUT.exists():
        raise RuntimeError("Photoshop ran the script but wrote no reply "
                           "(is _ps_out.txt writable?)")
    return OUT.read_text(encoding="utf-8-sig", errors="replace")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run ExtendScript in the live Photoshop session.")
    ap.add_argument("script", nargs="?", help="jsx file to execute")
    ap.add_argument("-c", "--code", help="inline JSX to execute")
    ap.add_argument("--ping", action="store_true", help="just check the bridge")
    ap.add_argument("--debug", action="store_true",
                    help="open the Photoshop JavaScript debugger on error")
    a = ap.parse_args(argv)

    if a.ping:
        code = "__result__ = app.name + \" \" + app.version;"
    elif a.code:
        code = a.code
    elif a.script:
        p = Path(a.script).expanduser()
        if not p.exists():
            ap.error("no such file: %s" % p)
        code = p.read_text(encoding="utf-8-sig")
    else:
        ap.print_help()
        return 2

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    started = time.time()
    try:
        out = run(code, a.debug)
    except RuntimeError as exc:
        print("BRIDGE ERROR: %s" % exc, file=sys.stderr)
        return 1

    sys.stdout.write(out if out.endswith("\n") else out + "\n")
    sys.stdout.write("--- %.2fs ---\n" % (time.time() - started))
    return 1 if "BRIDGE ERROR:" in out else 0


if __name__ == "__main__":
    sys.exit(main())
