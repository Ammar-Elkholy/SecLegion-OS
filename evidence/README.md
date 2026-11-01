# evidence

Test results, written by tools only (never by hand). Layout:

    evidence/<test-id>/<iso-sha256>/<UTC-timestamp>/result.json
                                                    serial.log
                                                    screen.png

Each run gets a new timestamp directory; a tracked result is never overwritten.
`result.json` lists each artifact with its sha256, and `serial_patterns`, the regexes
`tools/verify-evidence` re-applies to the stored `serial.log`. `TESTING.md` is generated
from these files (`make evidence`: verify, then generate). See `tools/lib/evidence.py`.
