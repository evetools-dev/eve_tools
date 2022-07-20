import logging
import pyperclip as pc
import sys
from subprocess import check_call, CalledProcessError, DEVNULL

logger = logging.getLogger(__name__)


def to_clipboard(msg: str) -> None:
    """Copies msg to clipboard.

    Copies msg to clipboard using Pyperclip package.
    By default, copy should work on Windows and MacOS.
    Linux needs one of xclip/xsel/gtk/PyQt4 to make it work.
    Some Linux distributions might not have any of these,
    so also tries to install xclip or xsel if possilbe.
    """
    if sys.platform == "linux":  # check xclip/xsel
        xclip_installed = debian_package_check("xclip")
        xsel_installed = debian_package_check("xsel")
        dependency_satisfied = xclip_installed or xsel_installed
        if not xclip_installed and not dependency_satisfied:
            dependency_satisfied = debian_package_install("xclip")
        if not xsel_installed and not dependency_satisfied:
            dependency_satisfied = debian_package_install("xsel")

    try:
        pc.copy(msg)
        logger.debug("Successfully copied to clipboard: %s", msg)
    except pc.PyperclipException as pc_exc:
        if sys.platform == "linux":  # linux2 prior to Python 3.3
            if not dependency_satisfied:
                logger.error(
                    "Pyperclip NotImplementedError: needs copy/paste mechanism for Linux: xclip or xsel"
                )
                raise SystemExit(
                    "With linux, one of xclip, xsel, gtk, PyQt4 is necessary. apt-get install xclip and xsel failed. Try to manually install them using sudo apt-get install, or get gtk or PyQt4 modules installed. See https://pypi.org/project/pyperclip/ for more."
                ) from pc_exc
        # pc.copy() should work in MacOS and Windows by default
        raise


def debian_package_check(name: str) -> bool:
    """Checks if a debian package is installed.
    Should only be called under Linux system."""
    if sys.platform != "linux":
        raise NotImplemented
    try:
        import apt
    except ImportError as exc:
        if not debian_package_install("python3-apt") and not debian_package_install("python-apt"):
            raise SystemExit("Missing package apt. Install using sudo apt-get install python3-apt or sudo apt-get install python-apt.") from exc
        else:
            # python3-apt or python-apt installed
            import apt
    db_packages = apt.Cache()
    package = db_packages.get(name)
    return package is not None and package.is_installed


def debian_package_install(name: str) -> bool:
    """Tries to install a debian package using sudo apt-get install.

    For some users, this could be successful because they run as sudo.
    In case users does not grant sudo to Python, a password prompt might appear,
    or the call might fail, depending on the Python interpreter.

    Note:
        Run check_call with IDLE will fail. Run with command line, or in VS Code.
    """
    try:
        cmd = "sudo apt-get install -y {}".format(name)
        check_call(
            cmd.split(" "),
            stdout=DEVNULL,
            stderr=DEVNULL,
        )
        logger.debug("Installed xclip using: %s", cmd)
        return True
    except CalledProcessError as grepexc:
        logger.warning(
            f"Package install FAILED: {grepexc.cmd}: {grepexc.returncode} - {grepexc.output}"
        )
        return False


def read_clipboard() -> str:
    """Reads clipboard using Pyperclip."""
    return pc.paste()
