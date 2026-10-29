#!/bin/bash
#
# S6_STAGE2_HOOK only points to one script. generate_airplay2_services.sh
# does everything now: the one-time dbus/avahi/nqptp services, the
# dynamic per-PulseAudio-sink AirPlay 2 zones, AND the one-time
# "airplay2-castbridge-manager" service (execs cast_bridge_manager.py,
# which discovers Cast devices and creates their AirPlay 2 receivers
# directly in this same container).
#
# Cast Bridge used to be a second, separate addon/container. That
# split turned out to cause more problems than it solved — nqptp's
# cross-container IPC limitation, then a config-mount path mismatch
# between the two addons — so its discovery/relay logic was folded in
# here as cast_bridge_manager.py instead. There is no longer a second
# addon or a hand-off file to keep in sync.
#
# Propagate generation failures (including an invalid LAN interface) to s6.
exec /usr/sbin/generate_airplay2_services.sh
