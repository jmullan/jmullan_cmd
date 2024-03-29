"""Command-line tooling helpers."""

import abc
import logging
import os
import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from signal import SIG_DFL, signal, SIGPIPE
from typing import TextIO

logger = logging.getLogger(__name__)


class Jmullan:
    GO = True
    PIPE_OK = True


def my_except_hook(exctype, value, traceback):
    if exctype == BrokenPipeError:
        Jmullan.PIPE_OK = False
        pass
    else:
        sys.__excepthook__(exctype, value, traceback)


def handle_signal(signum, frame):
    logger.debug(f"Received signal {signum}")
    if SIGPIPE == signum:
        sys.stderr.close()
        exit(1)
    if not Jmullan.GO:
        logger.debug("Received two signals, so immediately quitting")
        exit(0)
    Jmullan.GO = False


def ignore_broken_pipe_error():
    sys.excepthook = my_except_hook
    signal(SIGPIPE, SIG_DFL)


def stop_on_broken_pipe_error():
    sys.excepthook = my_except_hook
    signal(SIGPIPE, handle_signal)


def open_file_or_stdin(filename: str) -> TextIO:
    if filename == "-":
        return sys.stdin
    else:
        return open(filename)


def read_file_or_stdin(filename: str) -> str:
    if filename == "-":
        return sys.stdin.read()
    else:
        file_size = os.path.getsize(filename)
        with open(filename) as f:
            return f.read(file_size)


def write_to_file_or_stdout(filename: str, contents: str):
    if filename == "-":
        print(contents)
    else:
        with open(filename, "w") as f:
            f.write(contents)


def add_filenames_arguments(parser: ArgumentParser):
    parser.add_argument(
        "filenames",
        nargs="*",
        help=(
            "a list of files; - for stdin; separate arguments from"
            " files with an optional -- ; specifying no files means stdin"
        ),
    )


def get_filenames(args: Namespace):
    filenames = args.filenames or []
    if not filenames:
        filenames.append("-")
    return filenames


def update_in_place(filename: str, changer: Callable[[str], str]):
    contents = read_file_or_stdin(filename)
    new_contents = changer(contents)
    changed = new_contents != contents
    if changed:
        logger.debug("updated file %s\n" % filename)
        write_to_file_or_stdout(filename, new_contents)


def update_and_print(filename: str, changer: Callable[[str], str]):
    contents = read_file_or_stdin(filename)
    new_contents = changer(contents)
    changed = new_contents != contents
    if changed:
        logger.debug("printing file %s\n" % filename)
        print(new_contents)


def get_module_docstring(module_name: str):
    module = sys.modules.get(module_name)
    if module is not None:
        return module.__doc__


class Main(abc.ABC):
    def __init__(self):
        description = self.__doc__ or get_module_docstring(self.__module__)

        self.parser = ArgumentParser(description=description)
        self.parser.add_argument(
            "-v",
            "--verbose",
            dest="verbose",
            action="store_true",
            default=False,
            help="verbose is more verbose",
        )
        self.args = None

    def main(self):
        stop_on_broken_pipe_error()
        self.args = self.parser.parse_args()


class FileNameProcessor(Main, abc.ABC):
    @abc.abstractmethod
    def process_filename(self, filename: str):
        pass

    def get_filenames(self):
        """This allows overriding if needed"""
        return get_filenames(self.args)

    def main(self):
        add_filenames_arguments(self.parser)
        super().main()
        for filename in self.get_filenames():
            self.process_filename(filename)


class ContentsProcessor(FileNameProcessor, abc.ABC):
    @abc.abstractmethod
    def process_contents(self, contents: str) -> str:
        pass


class InPlaceFileProcessor(ContentsProcessor, abc.ABC):
    def process_filename(self, filename: str):
        update_in_place(filename, self.process_contents)


class PrintingFileProcessor(ContentsProcessor, abc.ABC):
    def process_filename(self, filename: str):
        update_and_print(filename, self.process_contents)


class TextIoProcessor(FileNameProcessor, abc.ABC):
    @abc.abstractmethod
    def process_file_handle(self, filename: str, file_handle: TextIO):
        pass

    def process_filename(self, filename: str):
        self.process_file_handle(filename, open_file_or_stdin(filename))


class TextIoLineProcessor(TextIoProcessor, abc.ABC):
    @abc.abstractmethod
    def process_line(self, filename: str, line: str) -> tuple[bool, str]:
        pass

    def process_file_handle(self, filename: str, file_handle: TextIO):
        for line in file_handle:
            should_print, line = self.process_line(filename, line)
            if should_print:
                sys.stdout.write(line)
