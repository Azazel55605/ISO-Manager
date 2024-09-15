#! /bin/python

import os.path
import ftplib
import re
from concurrent.futures import ThreadPoolExecutor
import signal
from functools import partial
from threading import Event
from urllib.request import urlopen
from simple_term_menu import TerminalMenu

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

progress = Progress(
    TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
    BarColumn(bar_width=None),
    "[progress.percentage]{task.percentage:>3.1f}%",
    "•",
    DownloadColumn(),
    "•",
    TransferSpeedColumn(),
    "•",
    TimeRemainingColumn(),
)


done_event = Event()


def handle_sigint(signum, frame):
    done_event.set()


signal.signal(signal.SIGINT, handle_sigint)


def copy_url(task_id: TaskID, url: str, path: str) -> None:
    """Copy data from a url to a local file."""
    # progress.console.log(f"Requesting {url}")
    response = urlopen(url)
    # This will break if the response doesn't contain content length
    progress.update(task_id, total=int(response.info()["Content-length"]))
    with open(path, "wb") as dest_file:
        progress.start_task(task_id)
        for data in iter(partial(response.read, 32768), b""):
            dest_file.write(data)
            progress.update(task_id, advance=len(data))
            if done_event.is_set():
                return
    # progress.console.log(f"Downloaded {path}")


def download(urls, dest_dir: str):
    """Download multiple files to the given directory."""

    with progress:
        with ThreadPoolExecutor(max_workers=2) as pool:
            for url in urls:
                filename = url[0].split("/")[-1]
                dest_path = os.path.join(dest_dir, filename)
                task_id = progress.add_task("download", filename=filename, start=False)
                pool.submit(copy_url, task_id, url[0], dest_path)

def read_conf(name):
    with open(f'./Modules/{name}.conf', 'r') as file:
        lines = file.readlines()

    return lines


def create_download_link(server, cwd, filename):
    link = f"https://{server}{cwd}/{filename}"
    return link


def ftp_traverse(os_name):

    conf_data = read_conf(os_name)

    server = conf_data[1].split('= ')[1].strip()
    cwd = conf_data[2].split('= ')[1].strip()
    options = conf_data[3].split('= ')[1].strip()

    ftp = ftplib.FTP(server)
    ftp.login()
    ftp.cwd(cwd)
    entries = ftp.nlst()
    return_files = []
    match os_name:
        case "ubuntu" | "ubuntu-server":
            regex = re.compile("[0-9][0-9].[0-9][0-9]?.?[0-9]?[0-9]")
            versions = []
            files = []
            for entry in entries:
                if regex.match(entry):
                    versions.append(entry)
            ftp.cwd(cwd + f"/{versions[-1]}")
            newest_entries = ftp.nlst()
            for new_entry in newest_entries:
                if "-" in new_entry:
                    if (versions[-1] == (new_entry.split('-')[1])) and (new_entry.split(".")[-1] == "iso"):
                        files.append(new_entry)

            return_files.append(create_download_link(server, f"{cwd}/{versions[-1]}", files[int(options)]))

        case "arch":
            regex = re.compile("[0-9][0-9][0-9][0-9].[0-9][0-9].[0-9][0-9]")
            files = []
            for entry in entries:
                if "-" in entry:
                    if (regex.match(entry.split('-')[1])) and (entry.split(".")[-1] == "iso"):
                        files.append(entry)

            return_files.append(create_download_link(server, cwd, files[0]))
    return return_files


def main():
    os_list = {
        "ubuntu",
        "ubuntu-server",
    }

    file = []
    for os_entry in os_list:
        file.append(ftp_traverse(os_entry))
    download(file, "./")

if __name__ == "__main__":
    main()
