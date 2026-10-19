"""LinkGuard demo server: imitates good, bad and broken download servers (spec §11).

It exists so every test and the demo run offline, against known behaviour, with no real
malware. It binds to 127.0.0.1 only and must never be exposed.
"""
