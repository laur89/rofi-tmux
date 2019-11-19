#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(level=logging.INFO)
import xmlrpc.client

class RFT(object):
    """Abstraction to interface with rofi, tmux, tmuxinator."""

    def __init__(self, debug=False):
        """Initialize ."""
        self.logger = logging.getLogger(__name__)
        if debug:
            self.logger.setLevel(logging.DEBUG)
        self._s = xmlrpc.client.ServerProxy('http://localhost:8000', allow_none=True)

    def _load_config(self, conf_file_loc) -> None:
        """Load json config file ~/.rft.

        Currently supported window managers: 'i3'

        """
        conf = {
                'wm': None,
                'tmux_title_rgx': '{session}',
                'ignored_sessions': []
        }
        conf.update(_read_dict_from_file(conf_file_loc))
        self.logger.debug('effective config: {}'.format(conf))
        return conf

    def switch_session(self) -> None:
        """Switch tmux session."""
        self._rofi_tmux_session(action='switch', rofi_msg='Switch session')

    def kill_session(self) -> None:
        """Kill tmux session."""
        self._rofi_tmux_session(action='kill', rofi_msg='Kill session')

    def switch_window(self, session_name=None, global_scope=True) -> None:
        """Switch to a window of a particular session or any session.

        :session_name: if it's not None, the scope is limited to this session
        :global_scope: if True, it will take into account all existent windows

        """
        print(' sent msg!')
        self._s.switch_window(session_name, global_scope)
        # self._rofi_tmux_window(
            # action='switch',
            # rofi_msg='Switch window',
            # session_name=session_name,
            # global_scope=global_scope)

    def kill_window(self, session_name=None, global_scope=True) -> None:
        """Kill window of a particular session or any session.

        :session_name: if it's not None, the scope is limited to this session
        :global_scope: if True, it will take into account all existent windows

        """
        self._rofi_tmux_window(
            action='kill',
            rofi_msg='Kill window',
            session_name=session_name,
            global_scope=global_scope)

def _read_dict_from_file(file_loc):
    try:
        with open(file_loc, 'r') as f:
            return json.load(f)
    except Exception as e:
        return {}
