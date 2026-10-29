# Fujitsu AirPlay 2 fork: installation and verification

This is a GPL-3.0 fork of [iVolt1/hassio-apps](https://github.com/iVolt1/hassio-apps),
based on upstream commit `f77ebf69a2b63061c793cdbdce7c0bf2377d81b0`.
The original license, source history, audio routing, Cast relay, AirPlay 2 build
flags and nqptp service are retained. Only the stable app is modified.

## Interface change

Install **AirPlay 2 Multiroom Audio (Fujitsu)**, version **1.01.1**, with slug
`airplay_2_multiroom_audio_fujitsu`. Its Configuration tab provides:

```yaml
airplay_interface: enp1s0
```

The startup generator reads `/data/options.json` using `airplay_interface.py`.
The same validated name is used for Avahi's `allow-interfaces`, local sink
Shairport configs, and the Cast manager's Shairport configs. The selected name
is embedded in the generated Cast service, because a child stage-2 shell's
environment alone does not propagate back to s6. On every full restart, the
container's generated services and receiver configs are regenerated.

An explicit option is intentional: selecting the first host interface or the
default route could choose a Docker bridge or VPN rather than the LAN.
For manually managed containers, an existing `AIRPLAY_INTERFACE` environment
override still takes precedence. No route, address, link state, NetworkManager
setting, or Home Assistant host configuration is changed.

A nonexistent or unsafe interface stops generation with a useful error.
Successful startup prints this to the app Log tab and generator log:

```text
[airplay2] Using LAN interface enp1s0 (exists); Avahi and Shairport Sync will advertise here
```

This checks existence, not multicast reachability. Avahi remains restricted to
the chosen LAN interface to retain upstream's protection against advertisements
on Docker/veth interfaces. Its private hostname remains `airplay2-multiroom`.
Cast discovery continues to use its independent pychromecast/zeroconf path.
nqptp remains in the same container and is started exactly as upstream did.
Shairport's `interface` option scopes mDNS advertisement; it does not bind all
network sockets to that interface.

## Install and safely switch

1. Create a Home Assistant backup including the **original** app and its data.
   Record its Configuration options, Start on boot and Watchdog settings.
   Keep the original app installed and keep its repository registered.
2. Open **Settings → Apps → App Store → ⋮ → Repositories** (older releases
   call these Add-ons / Add-on Store). Add:

   ```text
   https://github.com/thore22/hassio-apps-fujitsu
   ```

3. Refresh the store and install **AirPlay 2 Multiroom Audio (Fujitsu)** from
   **Fujitsu Audio Apps (based on iVolt1)**. Select the stable Fujitsu app,
   not the unchanged beta. There is no prebuilt `image` override: Supervisor
   builds this fork's Dockerfile on the host. The first installation can take
   several minutes and needs Internet access for Alpine, GitHub and PyPI.
4. Before starting the fork, turn off **Start on boot** and **Watchdog** on
   the original, then **Stop** it. Stop any other copy of this upstream app
   or its beta. Concurrent copies can collide on mDNS hostname, PTP/RTSP
   ports, shared media FIFOs and PulseAudio sinks.
5. In the fork's **Configuration** tab, save `airplay_interface: enp1s0`.
   It is the Ethernet interface name, not an IP address.
6. Normally start with the fork's fresh app data: Cast devices are discovered
   automatically. To retain local zone `.custom` overrides and saved port
   identities, optionally **copy**, never move, the original's
   `shairport-sync/config/` directory into the fork's app config directory
   while both apps are stopped. For Cast HTTP port identities, also copy
   `cast-bridge/http_port_map.txt` if present. Copy files only if you need
   these settings; options must be saved separately in the Configuration tab.
   Do not overwrite or delete the original's files.
7. Start the fork and inspect its Log tab. Wait at least 30 seconds for Cast
   discovery, native AirPlay probing and mDNS announcements. It should find
   your Nest Mini. Discovery runs once per startup; restart after adding or
   renaming a Cast device.
8. Test the checks below, including a complete stop/start. Once satisfied,
   enable Start on boot (and optionally Watchdog) on the fork only.

`addon_config:rw` gives each app separate persistent storage. Inside the app
it is `/config`; via a suitable file share it is usually
`addon_configs/<repository-hash>_airplay_2_multiroom_audio_fujitsu/`.
The original has its own `<repository-hash>_airplay_2_multiroom_audio/`
directory. Some file tools expose these under `/addon_configs/`; use the actual
directories shown by your tool. A normal Terminal/SSH app shell has its own
`/config`, so do not assume it is this app's directory.

## Verify on the Fujitsu and iPhone

1. **Interface:** the Log tab must show `enp1s0 (exists)` and no warning about
   an interface not found. An error listing other interfaces means the option
   does not match the interfaces visible inside the host-network container.
2. **Cast discovery:** read `/config/cast-bridge/logs/cast_bridge_manager.log`
   inside this app's storage. Expect `Found ... Cast device(s)` including your
   speaker, `Using LAN interface enp1s0 (exists)` and a Shairport start message.
   If the speaker was excluded as already advertising AirPlay, stop other
   bridge copies, wait for their advertisements to expire and restart.
3. **Generated configuration:** inspect
   `/config/shairport-sync/config/Schlafzimmer_speaker-ap2.conf`.
   It must contain `interface = "enp1s0";`, `mdns_backend = "avahi";`
   and `output_backend = "pipe";`. The current upstream normalizes Cast
   names, so the advertised receiver is normally **Schlafzimmer_speaker**.
   Sink-backed configurations must use the same interface.
4. **Shairport logs:** read
   `/config/shairport-sync/logs/Schlafzimmer_speaker-ap2.log`.
   Look for `Startup in AirPlay 2 mode`, `NQPTP service found` and successful
   Avahi service registration. Watch for config parse errors, port conflicts,
   repeated restarts or `needs a rename` collisions. Registration success
   alone does not prove that advertisements reach the iPhone.
5. **Avahi:** the Log tab should show Avahi joining mDNS multicast on
   `enp1s0` and successful startup without a hostname collision loop. If you
   already have a host/container shell with Docker access, identify the
   fork's container with `docker ps` and run these read-only checks using
   its real container name in place of `<container>`:

   ```sh
   docker exec <container> ip addr show dev enp1s0
   docker exec <container> cat /etc/avahi/avahi-daemon.conf
   docker exec <container> cat /etc/s6-overlay/s6-rc.d/airplay2-castbridge-manager/run
   ```

   Confirm `allow-interfaces=enp1s0`, `host-name=airplay2-multiroom`, and the
   exported `AIRPLAY_INTERFACE="enp1s0"`. No host shell or protection-mode
   change is necessary for normal installation or LAN browsing.
6. **Bonjour from a separate LAN client:** on a Mac, run each browse in its
   own terminal and stop with Ctrl-C:

   ```sh
   dns-sd -B _raop._tcp local.
   dns-sd -B _airplay._tcp local.
   ```

   On Linux with `avahi-utils` installed:

   ```sh
   avahi-browse -rt _raop._tcp
   avahi-browse -rt _airplay._tcp
   ```

   A Bonjour browser app on the iPhone can check the same types. Both should
   show the generated receiver; RAOP usually prefixes the name with a device
   ID followed by `@`. Resolve the service to verify it advertises the LAN
   address of the Home Assistant host and the generated Shairport port,
   rather than a Docker address. Service registration is on the Fujitsu;
   the Nest Mini itself does not become a native AirPlay endpoint.
7. **iPhone:** connect to the same LAN (avoid guest Wi-Fi/client isolation),
   open Control Center → Now Playing → AirPlay and select
   **Schlafzimmer_speaker**. Test audio and volume on the Nest Mini first.
   Then select it alongside the Apple TV 4K and HomePod mini. Test starting,
   stopping, removing/re-adding a speaker, and a longer session for drift.
8. **Restart persistence:** restart the fork, repeat Bonjour/iPhone checks,
   and confirm generated files still use `enp1s0` and saved ports stay stable.
   Confirm Home Assistant's Google Cast integration still discovers and
   controls the Nest Mini.

If local registration succeeds but the separate client sees no services,
check LAN multicast/UDP 5353 reachability, Wi-Fi isolation and VLAN boundaries.
If Bonjour works but playback fails, inspect
`/config/cast-bridge/logs/Schlafzimmer_speaker-bridge.log` for Cast connection
or HTTP stream failures. The Cast speaker must be able to reach the Fujitsu's
HTTP stream port (8090 or its persisted assignment).

**Not yet proven on your installation:** iPhone visibility, end-to-end Cast
playback, PTP operation and grouping with native AirPlay 2 devices. The relay
retains upstream's Cast buffering/latency limitations; visibility and group
selection do not guarantee tight synchronization with an Apple TV/HomePod.
This interface fix does not attempt to redesign the relay or timing code.

## Rollback

1. Stop the Fujitsu app and disable its Start on boot and Watchdog switches.
2. Start the original app and restore its previous boot/watchdog settings.
   Its configuration is still in its original, separate storage. If needed,
   restore only its app backup from the backup made before switching.
3. Allow stale Bonjour advertisements to expire, then check the picker again.
   The original's interface behavior will also return; rollback restores
   previous behavior rather than fixing that original defect.
4. Leave the fork installed but stopped while investigating. No uninstall,
   repository removal or data deletion is required.

## Validation and build reproducibility

Run from the repository root on Linux:

```sh
python3 -m pip install PyYAML
bash -n airplay_2_multiroom_audio/generate_airplay2_services.sh
bash -n airplay_2_multiroom_audio/run_stage2_hooks.sh
python3 -m compileall -q airplay_2_multiroom_audio tests
python3 -m unittest discover -s tests -v
docker build --progress=plain -t airplay2-fujitsu:test airplay_2_multiroom_audio
```

The regression suite checks option precedence, missing/unsafe interfaces,
restart regeneration, both Shairport generation paths, Avahi configuration,
nqptp service preservation and Home Assistant packaging. Its full service
generation test uses temporary paths and fake audio/network commands.
The workflow `.github/workflows/validate-fujitsu.yaml` also builds an amd64
container and checks installed binaries. Forks may need Actions enabled in
their GitHub Actions tab before the workflow can run.

The inherited Dockerfile uses `ghcr.io/home-assistant/base:latest`, development
branches of Shairport Sync/nqptp and lower-bounded Python requirements.
Those upstream inputs can change, so a source/metadata check alone cannot
guarantee a future build. Check the workflow result and the Supervisor build
log. No container build, network advertisement or playback should be treated
as tested unless a corresponding successful result has been recorded.

The only remaining upstream interface-name mention is a historical entry in
the unchanged beta's `CHANGELOG.md`; it is not an active default in this app.

References: [Home Assistant app configuration](https://contributors.home-assistant.io/apps/reference/configuration/),
[Shairport Sync interface semantics](https://github.com/mikebrady/shairport-sync/blob/development/scripts/shairport-sync.conf).
