# netbox-proxmox-automation

## Clone and step into the repo

```
# git clone https://github.com/netboxlabs/netbox-proxmox-automation/
# cd netbox-proxmox-automation
```

## Install required python packages

```
# python3 -m venv venv
# source venv/bin/activate
(venv) # pip install -r requirements.txt
```

## Run mkdocs

```
(venv) # mkdocs serve
INFO    -  Building documentation...
INFO    -  Cleaning site directory
INFO    -  The following pages exist in the docs directory, but are not included in the "nav" configuration:
             - Administration Console/console-overview.md
             - NetBox Cloud/getting-started-with-nbc.md
INFO    -  Documentation built in 0.75 seconds
INFO    -  [13:37:39] Watching paths for changes: 'docs', 'mkdocs.yml'
INFO    -  [13:37:39] Serving on http://127.0.0.1:8000/
```

## :warning:

If you see errors like this...

> ERROR   -  Config value 'theme': Unrecognised theme name: 'material'. The available installed themes are: mkdocs, readthedocs
> ERROR   -  Config value 'markdown_extensions': Failed to load extension 'pymdownx.tabbed'.
>            ModuleNotFoundError: No module named 'pymdownx'

 Try uninstalling `mkdocs` from your package manager, (e.g. `brew uninstall mkdocs`) and just using the version installed by `pip`. It seems that `mkdocs` doesn't like it when you've installed it using different methods.

# What's New in 2025.11.X
  - Switches to calendar (as opposed to semantic) versioning
  - Adds Proxmox cluster and node(s) discovery through a new convenience script
  - Adds Proxmox VM migration to alternate Proxmox node(s) through events
  - Adds [NetBox Branching](https://netboxlabs.com/docs/extensions/branching/) support for Proxmox node and VM discovery
  - Refactors how branching and SSL options are handled
  - Adds --debug option to convenience scripts

# System Requirements
  - NetBox 4.2 or newer.  This is because of a change to mac address modeling, which is imcompatible with previous versions of the NetBox API.
  - Proxmox 8.x.  Proxmox 9.x has not yet been tested (YMWV).
  - Python 3.12 or newer on the system where you are running NetBox (this is effectively also a dependency with NetBox 4.4 and certain plugins).

# Developers
- Nate Patwardhan &lt;npatwardhan@netboxlabs.com&gt;

# Known Issues / Roadmap

## Known Issues
- Might not support Proxmox v9 as of yet
- Can't map all interface types/speeds to NetBox interface objects, so defaults to 'other' if not able to be mapped
- *Only* supports SCSI disk types (this is possibly fine as Proxmox predomininantly provisions disks as SCSI)
- LXC migration is not supported for myriad reasons
- Proxmox "tags" are not supported (seeking community feedback around use cases)

## Roadmap -- Delivery
- Use of NetBox Custom Objects for NetBox > 4.4
- DNS update support via gss-tsig (requires NetBox `netbox-dns` plugin)
- Integration with NetBox Discovery/Assurance
