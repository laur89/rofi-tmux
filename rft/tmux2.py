#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# to listen to server activity, then:   $ tmux -CC attach

# from .window_manager import WindowManager
import logging
# import json
import libtmux

class tmux(object):
    """tmux client"""

    def __init__(self, conf, logger_lvl = None) -> None:

        """Constructor

        """
        self._conf = conf
        self._libts = libtmux.Server()
        self._sessions = []
        self._current_session = None
        self.logger = logging.getLogger(__name__)
        if logger_lvl != None:
            self.logger.setLevel(logger_lvl)

        self._register_sessions()

        # super(i3WM, self).__init__()


    def _register_sessions(self) -> None:
        """Register the current tmux sessions _sessions, and
        store current active session in _cur_tmux_s"""
        try:
            self._sessions = self._get_sessions_filtered()
            self.logger.debug('_sessions: {}'.format(self._sessions))
        except libtmux.exc.LibTmuxException as e:
            # if there are no sessions running load_project takes place
            self.load_tmuxinator()
        self._current_session = self._get_cur_session()
        self.logger.debug('_cur_tmux_s: {}'.format(self._cur_tmux_s.name if self._cur_tmux_s else self._cur_tmux_s))


    def get_session(self, session_name) -> dict:
        for s in self._sessions:
            if s.name == session_name:
                return s
        return None


    def get_sessions(self) -> dict:
        return self._sessions


    def get_current_session(self) -> dict:
        return self._current_session


    def _get_sessions_filtered(self) -> list:
        """Return list of tmux sessions, sans ones explicitly blacklisted
        by self._conf.ignored_sessions"""
        return [s for s in self._libts.list_sessions() if s.name not in self._conf['ignored_sessions']]


    def _get_cur_session(self) -> libtmux.session.Session:
        """Return reference to our current tmux session."""
        for s in self._sessions:
            if str(s.attached) != '0':
                return s
        return None
