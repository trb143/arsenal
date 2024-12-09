import argparse
import json
import os
import re
import subprocess
import termios
import time
from curses import wrapper

# arsenal
from . import __version__
from .modules import config
from .modules import cheat
from .modules import check
from .modules import gui as arsenal_gui


class App:

    def __init__(self):
        self.stdin = 0
        self.oldattr = None

    def get_args(self):
        examples = '''examples:
        arsenal
        arsenal --copy
        arsenal --print

        You can manage global variables with:
        >set GLOBALVAR1=<value>
        >show
        >clear

        (cmd starting with '>' are internals cmd)
        '''

        parser = argparse.ArgumentParser(
            prog="arsenal",
            description='arsenal v{} - Pentest command launcher'.format(__version__),
            epilog=examples,
            formatter_class=argparse.RawTextHelpFormatter
        )

        group_out = parser.add_argument_group('output [default = prefill]')
        group_out.add_argument('-p', '--print', action='store_true', help='Print the result')
        group_out.add_argument('-o', '--outfile', action='store', help='Output to file')
        group_out.add_argument('-x', '--copy', action='store_true', help='Output to clipboard')
        group_out.add_argument('-e', '--exec', action='store_true', help='Execute cmd')
        group_out.add_argument('-t', '--tmux', action='store_true', help='Send command to tmux panel')
        group_out.add_argument('-c', '--check', action='store_true', help='Check the existing commands')
        group_out.add_argument('-f', '--prefix', action='store_true', help='command prefix')
        group_out.add_argument('--no-tags', action='store_false', help='Whether or not to show the'
                                                                       ' tags when drawing the cheats')
        parser.add_argument('-V', '--version', action='version', version='%(prog)s (version {})'.format(__version__))

        return parser.parse_args()

    def run(self):
        args = self.get_args()

        # load cheatsheets
        cheatsheets = cheat.Cheats().read_files(config.CHEATS_PATHS, config.FORMATS,
                                                config.EXCLUDE_LIST)

        if args.check:
            check.check(cheatsheets)
        else:
            self.start(args, cheatsheets)

    def start(self, args, cheatsheets):
        arsenal_gui.Gui.with_tags = args.no_tags

        # create gui object
        gui = arsenal_gui.Gui()
        while True:
            # launch gui
            cmd = gui.run(cheatsheets, args.prefix)

            if cmd == None:
                exit(0)

            # Internal CMD
            elif cmd.cmdline[0] == '>':
                if cmd.cmdline == ">exit":
                    break
                elif cmd.cmdline == ">show":
                    if (os.path.exists(config.savevarfile)):
                        with open(config.savevarfile, 'r') as f:
                            arsenalGlobalVars = json.load(f)
                            for k, v in arsenalGlobalVars.items():
                                print(k + "=" + v)
                    break
                elif cmd.cmdline == ">clear":
                    with open(config.savevarfile, "w") as f:
                        f.write(json.dumps({}))
                    self.run()
                elif re.match(r"^\>set( [^= ]+=[^= ]+)+$", cmd.cmdline):
                    # Load previous global var
                    if (os.path.exists(config.savevarfile)):
                        with open(config.savevarfile, 'r') as f:
                            arsenalGlobalVars = json.load(f)
                    else:
                        arsenalGlobalVars = {}
                    # Add new glovar var
                    varlist = re.findall("([^= ]+)=([^= ]+)", cmd.cmdline)
                    for v in varlist:
                        arsenalGlobalVars[v[0]] = v[1]
                    with open(config.savevarfile, "w") as f:
                        f.write(json.dumps(arsenalGlobalVars))
                else:
                    print("Arsenal: invalid internal command..")
                    break

            # OPT: Copy CMD to clipboard
            elif args.copy:
                try:
                    import pyperclip
                    pyperclip.copy(cmd.cmdline)
                except ImportError:
                    pass
                break

            # OPT: Only print CMD
            elif args.print:
                print(cmd.cmdline)
                break

            # OPT: Write in file
            elif args.outfile:
                with open(args.outfile, 'w') as f:
                    f.write(cmd.cmdline)
                break

            # OPT: Exec
            elif args.exec and not args.tmux:
                os.system(cmd.cmdline)
                break

            elif args.tmux:
                try:
                    import libtmux
                    try:
                        server = libtmux.Server()
                        session = server.list_sessions()[-1]
                        window = session.attached_window
                        panes = window.panes
                        if len(panes) == 1:
                            # split window to get more pane
                            pane = window.split_window(attach=False)
                            time.sleep(0.3)
                        else:
                            pane = panes[-1]
                        # send command to other pane and switch pane
                        if args.exec:
                            pane.send_keys(cmd.cmdline)
                        else:
                            pane.send_keys(cmd.cmdline, enter=False)
                            pane.select_pane()
                    except libtmux.exc.LibTmuxException:
                        self.prefil_shell_cmd(cmd)
                        break
                except ImportError:
                    self.prefil_shell_cmd(cmd)
                    break
            # DEFAULT: Prefill Shell CMD
            else:
                self.prefil_shell_cmd(cmd)
                break

    def prefil_shell_cmd(self, cmd):
        # save TTY attribute for stdin
        self.oldattr = termios.tcgetattr(self.stdin)
        # create new attributes to fake input
        newattr = termios.tcgetattr(self.stdin)
        # disable echo in stdin -> only inject cmd in stdin queue (with TIOCSTI)
        newattr[3] &= ~termios.ECHO
        # enable non canonical mode -> ignore special editing characters
        newattr[3] &= ~termios.ICANON
        # use the new attributes
        termios.tcsetattr(self.stdin, termios.TCSANOW, newattr)
        # write the selected command in stdin queue
        print(cmd.cmdline, end=" ")
        input()
        print("")
        # run command and pipe to stdin
        subprocess.run([cmd.cmdline], shell=True)
        self.restore_tty()

    def restore_tty(self):
        # restore TTY attribute for stdin if they have been saved
        if self.oldattr:
            termios.tcsetattr(self.stdin, termios.TCSADRAIN, self.oldattr)


def main():
    app = App()
    try:
        app.run()
    except KeyboardInterrupt:
        app.restore_tty()
        exit(0)


if __name__ == "__main__":
    wrapper(main()) 
