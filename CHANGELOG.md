0.0.3 (2026-04-01)


- change config file location to `$XDG_CONFIG_HOME/rofi-tmux/config.json`


## 0.0.2 (2024-11-26)


- fix daemon.handle_client()
  - cannot convert str direct to bool, need to go via int cast first
- update documentation:
  - remove tmuxinator-related bits;
  - add instructions for starting daemon via systemd service


## 0.0.1 (2024-11-18)
