#!/usr/bin/env python
# -*- coding: utf-8 -*-

import click
import rft.rft as rft
import rft.version as version
import rft.server as server

# TODO try also this (From https://stackoverflow.com/questions/45938091/multiple-context-objects-in-cli-click)
# class Config(object):

    # def __init__(self, config):
        # # do something with config here ...
        # self.a = 'example_A'
        # self.b = 'example_B'

@click.group()
@click.pass_context
@click.option(
    '--debug',
    default=False,
    is_flag=True,
    help='Enables logging at debug level.')
@click.option(
    '--daemon',
    default=False,
    is_flag=True,
    help='Start our listening server.')
def main(ctx, debug, daemon):
    """RFT (rofi-tmux) switcher."""
    if daemon:
        ctx.obj = server.Listener(debug=debug)
    else:
        ctx.obj = rft.RFT(debug=debug)
    ctx.obj._is_daemon = daemon

    # if ctx.obj is None:
        # ctx.obj = dict()
    # ctx.obj = rft.RFT(debug=debug)
    # ctx.obj['client'] = rft.RFT(debug=debug)
    # ctx.obj['server'] = server.Listener(debug=debug)
    # ctx.obj['server'].run()


@main.command()
@click.pass_obj
def ss(ctx):
    """Switch tmux session.

    :param ctx: context
    """
    ctx.switch_session()


@main.command()
@click.pass_obj
def ks(ctx):
    """Kill tmux session.

    :param ctx: context
    """
    ctx.kill_session()


@main.command()
@click.option(
    '--session_name',
    default=None,
    help='limit the scope to this this sesison')
@click.option(
    '--global_scope',
    default=True,
    type=bool,
    help='true, if you want to consider all windows')
@click.pass_obj
def sw(ctx, session_name, global_scope):
    """Switch tmux window.

    :param ctx: context
    :param session_name: tmux session name
    :param global_scope: True to consider all windows
    """
    ctx.switch_window(session_name=session_name, global_scope=global_scope)


@main.command()
@click.option(
    '--session_name',
    default=None,
    help='limit the scope to this this sesison')
@click.option(
    '--global_scope',
    default=True,
    type=bool,
    help='true, if you want to consider all windows')
@click.pass_obj
def kw(ctx, session_name, global_scope):
    """Kill tmux window.

    :param ctx: context
    :param session_name: tmux session name
    :param global_scope: True to consider all windows
    """
    ctx.kill_window(session_name=session_name, global_scope=global_scope)


@main.command()
@click.pass_obj
def lp(ctx):
    """Load tmuxinator project.

    :param ctx: context
    """
    ctx.load_tmuxinator()


@main.command()
@click.pass_obj
def start(ctx):
    """Start our daemon."""
    if not ctx._is_daemon:
        raise RuntimeError('start command only available with --daemon flag')
    ctx.run()

@main.command()
def v():
    """Print version."""
    print(version.__version__)


if __name__ == "__main__":
    print(' !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1!')
    main()
