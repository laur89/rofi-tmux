#!/usr/bin/env python
# -*- coding: utf-8 -*-

# from .window_manager import WindowManager
import logging
import json
# import re
from subprocess import check_output, call

WINDOWS_FORMAT  = '{"name":"#{session_name}","attached":#{session_attached},"wins":[{"name":"#{window_name}","active":#{window_active},"index":#{window_index},"session":"#{session_name}"}]}'
CLIENTS_FORMAT = '{"#{client_name}":"#{session_name}"}'

class tmux(object):
    """tmux client"""

    def __init__(self, conf, logger_lvl = None) -> None:
        """Constructor

        """
        self._conf = conf
        self._sessions = []
        self._current_session = None
        self._client = None   # TODO not sure if makes sense; isn't client per-session?
        self.logger = logging.getLogger(__name__)
        if logger_lvl != None:
            self.logger.setLevel(logger_lvl)
        self._register_sessions()


    # TODO: optimize to parse json only once? note wins += wins might be tricky then, as we'd be handling the same object
    def _register_sessions(self) -> None:
        first = True
        try:
            # TODO: instead of json.loads, consider how libtmux does it: https://github.com/tmux-python/libtmux/blob/v0.8.2/libtmux/server.py#L160
            for line in check_output(['tmux', 'list-windows', '-a', '-F', WINDOWS_FORMAT]).decode().splitlines():
                # line = re.sub(r'("[\s\w]*)"([\s\w]*")',r"\1\'\2", line)  # escape illegal double-quotes
                session = json.loads(line)
                if session['name'] in self._conf['ignored_sessions']:
                    continue
                elif first:
                    self._sessions.append(session)
                    if session['attached'] == 1:
                        self._current_session = session
                    first = False
                    continue
                last = self._sessions[-1]
                if last['name'] == session['name']:
                    last['wins'] += session['wins']
                else:
                    self._sessions.append(session)
                    if self._current_session == None and session['attached'] == 1:
                        self._current_session = session

            # register active window:
            # TODO: should we do this for all sessions, not only current one?
            for w in self._current_session['wins']:
                if w['active'] == 1:
                    self._current_session['win'] = w
                    break
        except FileNotFoundError:
            # if xprop not found, fall back to just checking if tmux win is on our current worksapce:
            self.logger.debug('xprop utility is not found - please install it.')
            self.logger.debug('will decide visibility simply by checking if tmux is on our current workspace')
            return self._is_tmux_win_on_current_ws(i3_win)

    # TODO: this is still fucky:
    def _get_client(self, session_name) -> str:
        if self._client: return self._client
        try:
            for line in check_output(['tmux', 'list-clients', '-F', CLIENTS_FORMAT]).decode().splitlines():
                i = json.loads(line)
                for client, session in i.items():
                    if session == session_name:
                        self._client = client
                        return client
                    break
        except FileNotFoundError:
            # if xprop not found, fall back to just checking if tmux win is on our current worksapce:
            self.logger.debug('xprop utility is not found - please install it.')

        return None

    def get_sessions(self) -> list:
        return self._sessions


    def get_session(self, session_name) -> dict:
        for s in self._sessions:
            if s['name'] == session_name:
                return s
        return None

    # ie switch session:
    def switch_client(self, session_name) -> None:
        cmd = ['tmux', 'switch-client', '-t', session_name]
	# any point in having following if-block?
        if self._current_session:  # TODO: do we want to target current_session? perhaps seek the client where session_name is attached to?
            client = self._get_client(self._current_session['name'])
            cmd += ['-c', client]
        call(cmd)

    def select_window(self, win_name) -> None:
        cmd = ['tmux', 'select-window', '-t', win_name]
        call(cmd)

    def kill_window(self, win_name) -> None:
        cmd = ['tmux', 'kill-window', '-t', win_name]
        call(cmd)

    def attach_session(self, session_name) -> None:
        cmd = ['tmux', 'attach-session', '-t', session_name]
        call(cmd)

    def get_current_session(self) -> dict:
        return self._current_session

