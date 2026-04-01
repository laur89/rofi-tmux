#!/usr/bin/env python
# -*- coding: utf-8 -*-

from .tmux import Tmux
import logging
import rofi
import subprocess


class RFT(object):
    """Abstraction to interface with rofi, tmux, tmuxinator."""

    def __init__(self, conf, tmux, wm):
        """Initialize ."""
        self._rofi = rofi.Rofi()
        self._cur_tmux_s = None  # TODO: remove member
        self.logger = logging.getLogger(__name__)

        self._config = conf
        self._tmux = tmux
        self._wm = wm  # optional


    def _get_sessions_filtered(self) -> list:
        """Return list of tmux sessions, sans ones explicitly blacklisted
        by self._config.ignored_sessions"""
        return [s for s in self._libts.list_sessions() if s.name not in self._config['ignored_sessions']]


    # def _get_cur_session(self) -> libtmux.session.Session:
        # """Return reference to our current tmux session."""
        # for s in self._sessions:
            # if str(s.attached_window) != '0':
                # return s
        # return None

    def _pprint_selection_s(self, session) -> str:
        """Pretty-print rofi selection from session entity"""
        if session:
            w = self._tmux.get_window(session['active_window_id'])
            return self._pprint_selection(session, w)

    def _pprint_selection_w(self, window) -> str:
        """Pretty-print rofi selection from window entity"""
        if window:
            s = self._tmux.get_session(window['session_id'])
            return self._pprint_selection(s, window)

    def _pprint_selection(self, s, w) -> str:
        """Pretty-print rofi selection"""
        return '{}:{}:{}'.format(
            s['name'],
            w['index'],
            w['name'])

    def _get_tmuxinator_projects(self) -> list:
        """Get tmuxinator projects name."""
        out, err = subprocess.Popen(
            "tmuxinator list",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE).communicate()
        projects = []
        for line in out.splitlines():
            line_str = line.decode('utf-8')
            if "tmuxinator projects" in line_str:
                continue
            projects += line_str.split()
        return projects

    def _get_session_by_name(self, session_name) -> None:  #libtmux.session.Session:
        """Get libtmux.session.Session.

        :session_name: session name

        """
        if self._sessions:
            for s in self._sessions:
                if s.name == session_name:
                    return s
        return None

    def _rofi_tmuxinator(self, rofi_msg, rofi_err) -> None:
        """Launch rofi for loading a tmuxinator project.

        :rofi_msg: rofi displayed message
        :err_msg: rofi error message

        """
        projects = self._get_tmuxinator_projects()
        if not projects:
            self._rofi.error(rofi_err)
            return

        res, key = self._rofi.select(rofi_msg, projects, rofi_args=['-i'])
        if key == 0 and res >= 0:
            out, err = subprocess.Popen(
                "tmuxinator {}".format(projects[res]),
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE).communicate()
            # update sessions.
            self._sessions = self._get_sessions_filtered()
            if not (session := self._get_session_by_name(projects[res])):
                return
            if self._wm:
                self._wm.focus_tmux_window(self._cur_tmux_s)
            try:
                session.attach_session()
            except libtmux.exc.LibTmuxException as e:  # TODO: libtmux dependency is no more
                # there are no attached clients just switch instead.
                session.switch_client()
            if self._cur_tmux_s:
                self._cache['last_tmux_s'] = self._cur_tmux_s.name  # TODO: self._cache is no more

    def load_tmuxinator(self) -> None:
        """Load tmuxinator project."""
        self._rofi_tmuxinator(
            rofi_msg='Tmuxinator project',
            rofi_err='There are no projects available')

    async def _rofi_tmux_session(self, action, rofi_msg) -> None:
        """Launch rofi for a specific tmux session action.

        :action: 'switch', 'kill'
        :rofi_msg: rofi displayed message

        """
        if not (sessions := self._tmux.get_sessions()):
            self._rofi.error("There are no sessions yet")
            return

        cur_session = self._tmux.get_current_session()
        sessions_list = [s['name'] for s in sessions]
        is_tmux_win_visible = False
        if self._wm:
            self.logger.debug('resolving is_tmux_win_visible...')
            is_tmux_win_visible = await self._wm.is_tmux_win_visible(cur_session)
            self.logger.debug('is_tmux_win_visible: {}'.format(is_tmux_win_visible))

        last_s = self._tmux.get_last_session()
        if is_tmux_win_visible and last_s and last_s['name'] in sessions_list:
            sel = sessions_list.index(last_s['name'])
        elif cur_session['name'] in sessions_list:
            sel = sessions_list.index(cur_session['name'])
        else:
            sel = 0

        res, key = self._rofi.select(rofi_msg, sessions_list, select=sel, rofi_args=['-i'])
        if key == 0 and res >= 0:
            session = sessions[res]
            if action == 'switch':
                if self._wm:
                    await self._wm.focus_tmux_window(cur_session)
                await self._tmux.switch_to_session(session)
            elif action == 'kill':
                session.kill_session()
            else:
                self._rofi.error('This action is not implemented')

    async def switch_session(self) -> None:
        """Switch tmux session."""
        await self._rofi_tmux_session(action='switch', rofi_msg='Switch session')

    def kill_session(self) -> None:
        """Kill tmux session."""
        self._rofi_tmux_session(action='kill', rofi_msg='Kill session')

    async def _rofi_tmux_window(self, action, session_name, global_scope,
                          rofi_msg) -> None:
        """Launch rofi for a specific tmux window action.

        :action: 'switch', 'kill'
        :session_name: if it's not None, the scope is limited to this session
        :global_scope: if True, it will take into account all existent windows
        :rofi_msg: rofi displayed message

        """
        windows = None
        cur_session = self._tmux.get_current_session()
        if session_name:
            windows = self._tmux.get_windows_for_session_name(session_name)
        elif global_scope:
            # print('is GLOBAL')
            windows = self._tmux.get_windows()
            # print(f'windows: {windows}')
        elif cur_session:
            windows = self._tmux.get_windows_for_session_id(cur_session['id'])

        if not windows: return

        windows_str = [self._pprint_selection_w(w) for w in windows]
        is_tmux_win_visible = False
        cur_win = self._pprint_selection_s(cur_session)
        if self._wm:
            self.logger.debug('resolving is_tmux_win_visible...')
            is_tmux_win_visible = await self._wm.is_tmux_win_visible(cur_session)
            self.logger.debug('is_tmux_win_visible: {}'.format(is_tmux_win_visible))

        if (last_w := self._tmux.get_last_window()):
            last_w = self._pprint_selection_w(last_w)

        if is_tmux_win_visible and last_w in windows_str:
            sel = windows_str.index(last_w)
        elif cur_win in windows_str:
            sel = windows_str.index(cur_win)
        else:
            sel = 0

        res, key = self._rofi.select(rofi_msg, windows_str, select=sel, rofi_args=['-i'])
        if key == 0 and res >= 0:
            win = windows[res]
            if action == 'switch':
                self.logger.debug('selected: {}'.format(windows_str[res]))

                if self._wm:
                    await self._wm.focus_tmux_window(cur_session)
                self.logger.debug('tmux switching to: {}'.format(win))
                await self._tmux.switch_to_window(win)
            elif action == 'kill':
                await self._tmux.kill_window(win)
            else:
                self._rofi.error('This action is not implemented')

    async def switch_window(self, session_name=None, global_scope=True) -> None:
        """Switch to a window of a particular session or any session.

        :session_name: if it's not None, the scope is limited to this session
        :global_scope: if True, it will take into account all existent windows

        """
        await self._rofi_tmux_window(
            action='switch',
            rofi_msg='Switch window',
            session_name=session_name,
            global_scope=global_scope)

    async def kill_window(self, session_name=None, global_scope=True) -> None:
        """Kill window of a particular session or any session.

        :session_name: if it's not None, the scope is limited to this session
        :global_scope: if True, it will take into account all existent windows

        """
        await self._rofi_tmux_window(
            action='kill',
            rofi_msg='Kill window',
            session_name=session_name,
            global_scope=global_scope)

