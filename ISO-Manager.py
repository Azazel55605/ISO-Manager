#! /bin/python

import os
import ftplib
import re
from concurrent.futures import ThreadPoolExecutor
import signal
from functools import partial
from os.path import exists
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

# const vars
MODULE_PATH = "./Modules/"
SETTINGS_FILE = "./ISO-Manager.conf"

#test vars
BLOCK_DOWNLOAD = False
TEST_FTP_CONNECTION = True

# settings
download_path = ""
max_simultaneous_downloads = 0

def read_settings(settings_file):
    global download_path
    global max_simultaneous_downloads

    with open(f'{SETTINGS_FILE}', 'r') as file:
        conf_data = file.readlines()

    download_path = conf_data[0].split('= ')[1].strip()
    max_simultaneous_downloads = int(conf_data[1].split('= ')[1].strip())


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


def download(urls, dest_dirs):
    """Download multiple files to the given directory."""

    if BLOCK_DOWNLOAD:
        print("Downloads blocked through settings")
        print("Usually because of testing purposes")
        return

    with progress:
        with ThreadPoolExecutor(max_workers=max_simultaneous_downloads) as pool:
            for url in urls:
                dest_dir = dest_dirs[urls.index(url)]

                if not exists(dest_dir):
                    os.makedirs(dest_dir)

                filename = url[0].split("/")[-1]
                dest_path = os.path.join(dest_dir, filename)
                task_id = progress.add_task("download", filename=filename, start=False)
                pool.submit(copy_url, task_id, url[0], dest_path)


def read_conf(name):
    with open(f'{MODULE_PATH}{name}.conf', 'r') as file:
        lines = file.readlines()

    return lines


def create_download_link(server, cwd, filename):
    link = f"https://{server}{cwd}/{filename}"
    return link


def ftp_traverse(os_name, server, cwd, options):
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
            print(newest_entries)
            for new_entry in newest_entries:
                if "-" in new_entry:
                    if (versions[-1] == (new_entry.split('-')[1])) and (new_entry.split(".")[-1] == "iso"):
                        files.append(new_entry)

            return_files.append(create_download_link(server, f"{cwd}/{versions[-1]}", files[int(options)]))

        case "edubuntu" | "ubuntu-cinnamon" | "lubuntu" | "kubuntu" | "xubuntu" | "xubuntu-minimal"| "ubuntu-studio":
            regex = re.compile("[0-9][0-9].[0-9][0-9]?.?[0-9]?[0-9]")
            versions = []
            files = []
            for entry in entries:
                if regex.match(entry):
                    versions.append(entry)
            ftp.cwd(cwd + f"/{versions[-1]}/release")
            newest_entries = ftp.nlst()
            for new_entry in newest_entries:
                if "-" in new_entry:
                    if (versions[-1] == (new_entry.split('-')[1])) and (new_entry.split(".")[-1] == "iso"):
                        files.append(new_entry)

            return_files.append(create_download_link(server, f"{cwd}/{versions[-1]}", files[int(options)]))

        case "ubuntu-budgie" | "ubuntu-unity" | "ubuntu-mate":
            regex = re.compile("[0-9][0-9].[0-9][0-9]?.?[0-9]?[0-9]")
            versions = []
            files = []
            for entry in entries:
                if regex.match(entry):
                    versions.append(entry)
            ftp.cwd(cwd + f"/{versions[-1]}/release")
            newest_entries = ftp.nlst()
            for new_entry in newest_entries:
                if "-" in new_entry:
                    if (versions[-1] == (new_entry.split('-')[2])) and (new_entry.split(".")[-1] == "iso"):
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


def update(os_list, test=False):
    file = []
    os_objects = []
    categorys = []
    download_paths = []

    for os_entry in os_list:
        temp = read_conf(os_entry)
        for line in temp:
            temp[temp.index(line)] = line.split('= ')[1].strip()

        temp.insert(0, os_entry)
        os_objects.append(temp)
        #

    for object in os_objects:
        object_index = os_objects.index(object)
        file.append(ftp_traverse(os_objects[object_index][0], os_objects[object_index][2], os_objects[object_index][3], os_objects[object_index][4]))
        categorys.append(os_objects[object_index][1])

    for path in categorys:
        download_paths.append(f"{download_path}/{path}")

    if test:
        print(file)
        print(download_path)
    else:
        download(file, download_paths)


def main():
    read_settings(SETTINGS_FILE)

    options = [
        "Download All",
        "View Category",
        "Manage Elements",
        "Settings",
        "Test",
        "Exit"
    ]

    terminal_menu = TerminalMenu(options)
    run = True

    while run:
        menu_entry_index = terminal_menu.show()

        match menu_entry_index:
            case 0:
                modules = os.listdir(MODULE_PATH)
                os_list = []
                for module in modules:
                    os_list.append(module.split('.')[0])
                update(os_list)
                run = False
            case 1:
                available = os.listdir(MODULE_PATH)
                modules = []

                for module in available:
                    temp = read_conf(module.split('.')[0])
                    category = temp[0].split('= ')[1].strip()
                    system = module
                    if category not in modules:
                        modules.append([category, system])

                module_names = []
                for object in modules:
                    if object[0] not in module_names:
                        module_names.append(object[0])

                module_names.append("back")
                terminal_menu_2 = TerminalMenu(module_names)
                run2 = True
                exit_pos = module_names.index("back")
                while run2:
                    category_index = terminal_menu_2.show()
                    if category_index == exit_pos:
                        run2 = False
                    else:
                        systems = []
                        for module in modules:
                            if module[0] == module_names[category_index]:
                                systems.append(module[1])

                        temp = systems.copy()

                        temp.insert(0, "Download All")
                        temp.append("back")
                        exit_pos_2 = temp.index("back")
                        terminal_menu_3 = TerminalMenu(temp)
                        run3 = True
                        while run3:
                            system_index = terminal_menu_3.show()
                            if system_index == exit_pos_2:
                                run3 = False
                            elif system_index == 0:
                                update_list = []
                                for element in systems:
                                    update_list.append(element.split('.')[0])

                                update(update_list)
                            else:
                                update([temp[system_index].split(".")[0]], TEST_FTP_CONNECTION)

            case 2:
                pass
            case 3:
                pass
            case 4:
                pass
            case 5:
                run = False


if __name__ == "__main__":
    main()
