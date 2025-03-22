#! /bin/python

import os
import ftplib
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
import signal
from functools import partial
from os.path import exists
from threading import Event
from urllib.request import urlopen

from simple_term_menu import TerminalMenu
import requests
from bs4 import BeautifulSoup

from rich.console import Console
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

#run vars
downloaded_distros = []

#test vars
BLOCK_DOWNLOAD = False
TEST_FTP_CONNECTION = False

# settings
download_path = ""
max_simultaneous_downloads = 0

def clear():
    os.system('clear')


def read_settings(settings_file):
    global download_path
    global max_simultaneous_downloads

    with open(f'{SETTINGS_FILE}', 'r') as file:
        conf_data = file.readlines()

    download_path = conf_data[0].split('= ')[1].strip()
    max_simultaneous_downloads = int(conf_data[1].split('= ')[1].strip())


def setup():
    # create Download directory
    if not exists(download_path):
        os.makedirs(download_path)


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
        print(urls)
        print(dest_dirs)
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


def ubuntu_model_manager(server, cwd, options, ftp, entries, version):
    regex = re.compile("[0-9][0-9].[0-9][0-9]?.?[0-9]?[0-9]")
    versions = []
    up_to_date_version = -1
    files = []
    for entry in entries:
        if regex.match(entry):
            versions.append(entry)
    if version == 0:
        ftp.cwd(cwd + f"/{versions[up_to_date_version]}")
    elif version == 1 or version == 2:
        ftp.cwd(cwd + f"/{versions[up_to_date_version]}")
        if not ("release" in ftp.nlst()):
            up_to_date_version = -2
        ftp.cwd(cwd + f"/{versions[up_to_date_version]}/release")

    newest_entries = ftp.nlst()
    for new_entry in newest_entries:
        if "-" in new_entry:
            if version == 0 or version == 1:
                if (versions[up_to_date_version] == (new_entry.split('-')[1])) and (new_entry.split(".")[-1] == "iso"):
                    files.append(new_entry)
            elif version == 2:
                if (versions[up_to_date_version] == (new_entry.split('-')[2])) and (new_entry.split(".")[-1] == "iso"):
                    files.append(new_entry)

    if version == 0:
        return create_download_link(server, f"{cwd}/{versions[up_to_date_version]}", files[int(options)])
    elif version == 1 or version == 2:
        return create_download_link(server, f"{cwd}/{versions[up_to_date_version]}/release", files[int(options)])


def http_traverse(os_name, server, cwd, options):
    options = int(options.strip())
    download_links = []
    if "garuda" in os_name:
        forward_link = ""
        object = []
        fp = requests.get(f"https://{server}{cwd}")
        # print(fp)
        soup = BeautifulSoup(fp.content, 'html.parser')
        regex = re.compile("[0-9][0-9][0-9][0-9][0-9][0-9]/")
        for link in soup.find_all("a", href=True):
            if regex.match(link["href"]):
                object.append(link["href"])

        # print(object)

        forward_link += str(object[-1])
        new_link = f"https://{server}{cwd}/{forward_link}"
        fp = requests.get(new_link)
        soup = BeautifulSoup(fp.content, 'html.parser')
        file = ""
        for link in soup.find_all("a", href=True):
            if link["href"].split(".")[-1] == "iso":
                file = link["href"]

        download_links.append(f"{new_link}/{file}")

    elif "kali" in os_name:
        fp = requests.get(f"https://{server}{cwd}")
        soup = BeautifulSoup(fp.content, 'html.parser')
        new_link = f"https://{server}{cwd}"
        files = []
        for link in soup.find_all("a", href=True):
            if link["href"].split("-")[-1] == "amd64.iso":
                files.append(link["href"])

        download_links.append(f"{new_link}/{files[options]}")

    elif "mint" in os_name:
        forward_link = ""
        object = []
        fp = requests.get(f"https://{server}{cwd}")
        soup = BeautifulSoup(fp.content, 'html.parser')
        regex = re.compile("[0-9][0-9]?.?[0-9]")
        for link in soup.find_all("a", href=True):
            if regex.match(link["href"]):
                object.append(link["href"])
        forward_link += str(object[-1])
        new_link = f"https://{server}{cwd}/{forward_link}"
        fp = requests.get(new_link)
        soup = BeautifulSoup(fp.content, 'html.parser')
        files = []
        for link in soup.find_all("a", href=True):
            if link["href"].split(".")[-1] == "iso":
                files.append(link["href"])

        download_links.append(f"{new_link}/{files[options]}")

    elif "manjaro" in os_name:
        forward_link = ""
        object = []
        fp = requests.get(f"https://{server}{cwd}")
        soup = BeautifulSoup(fp.content, 'html.parser')
        for link in soup.find_all("a", href=True):
            if "download" in link["href"] and "manjaro" in link["href"]:
                object.append(link["href"])

        forward_link += str(object[options])
        download_links.append(forward_link)

    return download_links


def ftp_traverse(os_name, server, cwd, options):
    ftp = ftplib.FTP(server)
    ftp.login()
    ftp.cwd(cwd)
    try:
        entries = ftp.nlst()
    except:
        print(f"timeout on {server}{cwd}")
        return ""
    return_files = []
    match os_name:
        case "":
            return_files.append(ubuntu_model_manager(server, cwd, options, ftp, entries, 0))

        case "ubuntu" | "ubuntu-server" | "edubuntu" | "ubuntu-cinnamon" | "lubuntu" | "kubuntu" | "xubuntu" | "xubuntu-minimal"| "ubuntu-studio":
            return_files.append(ubuntu_model_manager(server, cwd, options, ftp, entries, 1))

        case "ubuntu-budgie" | "ubuntu-unity" | "ubuntu-mate":
            return_files.append(ubuntu_model_manager(server, cwd, options, ftp, entries, 2))

        case "arch":
            regex = re.compile("[0-9][0-9][0-9][0-9].[0-9][0-9].[0-9][0-9]")
            files = []
            for entry in entries:
                if "-" in entry:
                    if (regex.match(entry.split('-')[1])) and (entry.split(".")[-1] == "iso"):
                        files.append(entry)

            return_files.append(create_download_link(server, cwd, files[0]))
    return return_files


def update(os_list, check_version=False):
    file = []
    os_objects = []
    categories = []
    download_paths = []

    for os_entry in os_list:
        temp = read_conf(os_entry)
        for line in temp:
            temp[temp.index(line)] = line.split('= ')[1].strip()

        temp.insert(0, os_entry)
        os_objects.append(temp)

    console = Console()
    with console.status("[bold green]Compiling files...") as status:
        for object in os_objects:
            object_index = os_objects.index(object)

            http_list = ["garuda", "kali", "mint", "manjaro"]

            if not os_objects[object_index][1] in http_list:
                file.append(ftp_traverse(os_objects[object_index][0], os_objects[object_index][2], os_objects[object_index][3], os_objects[object_index][4]))
            else:
                file.append(http_traverse(os_objects[object_index][0], os_objects[object_index][2], os_objects[object_index][3], os_objects[object_index][4]))
            categories.append(os_objects[object_index][1])
            console.log(f"Completed file: {os_objects[object_index][0]}")

    for path in categories:
        download_paths.append(f"{download_path}/{path}")

    if check_version:
        return [file, download_paths, os_list]
    else:
        download(file, download_paths)


def cleanup_old_files():
    total_size = 0
    folder_size = []
    folders = os.listdir(download_path)
    for folder in folders:
        if exists(f"{download_path}/{folder}/old"):
            size = 0
            for entry in os.listdir(f"{download_path}/{folder}/old"):
                if os.path.isfile(f"{download_path}/{folder}/old/{entry}"):
                    size += os.path.getsize(f"{download_path}/{folder}/old/{entry}")
            total_size += size
            folder_size.append([folder, size])

    print(total_size)
    print(folder_size)


def main():
    clear()
    read_settings(SETTINGS_FILE)
    setup()
    clear()

    options = [
        "Download All",
        "Check For Updates",
        "View Category",
        "Manage Elements",
        "Settings",
        "Test",
        "Exit"
    ]

    terminal_menu = TerminalMenu(options)
    run = True

    while run:
        clear()
        menu_entry_index = terminal_menu.show()

        match menu_entry_index:
            case 0:
                modules = os.listdir(MODULE_PATH)
                os_list = []
                for module in modules:
                    os_list.append(module.split('.')[0])
                update(os_list, TEST_FTP_CONNECTION)
                run = False
            case 1:
                modules = os.listdir(MODULE_PATH)
                os_list = []
                systems_to_update = []
                old_files = []
                for module in modules:
                    os_list.append(module.split('.')[0])
                object = update(os_list, True)
                existing_downloads = []
                for folder in os.listdir(download_path):
                    for file in os.listdir(f"{download_path}/{folder}"):
                        existing_downloads.append(file)

                # check if any given files already exist
                for entry in object[0]:
                    filename = entry[0].split('/')[-1]
                    file_download_path = str(object[1][object[0].index(entry)])
                    if filename in existing_downloads:
                        print(f"{object[2][object[0].index(entry)]} up to date")
                    else:
                        match file_download_path.split("/")[-1]:
                            case "arch" :
                                if exists(file_download_path):
                                    for element in os.listdir(file_download_path):
                                        if f"{filename.split('-')[0]}" in element:
                                            print(f"an older file exists for {filename} -> {object[2][object[0].index(entry)]}")
                                            if not object[2][object[0].index(entry)] in systems_to_update:
                                                systems_to_update.append(object[2][object[0].index(entry)])
                                            if not element in old_files:
                                                old_files.append(element)
                            case "ubuntu":
                                match filename.split('-')[1]:
                                    case "budgie" | "mate" | "unity":
                                        if exists(file_download_path):
                                            for element in os.listdir(file_download_path):
                                                if f"{filename.split('-')[0]}-{filename.split('-')[1]}" in element:
                                                    print(f"an older file exists for {filename} -> {object[2][object[0].index(entry)]}")
                                                    if not object[2][object[0].index(entry)] in systems_to_update:
                                                        systems_to_update.append(object[2][object[0].index(entry)])
                                                    if not element in old_files:
                                                        old_files.append(element)
                                    case _:
                                        if filename.split('-')[0] == "ubuntu":
                                            if exists(file_download_path):
                                                for element in os.listdir(file_download_path):
                                                    if element.split('-')[0] == "ubuntu" and not (element.split('-')[1] in ['budgie', 'unity', 'mate']):
                                                        if "beta" in filename:
                                                            if f"{filename.split('-')[0]}" in element and f"{filename.split('-')[3]}" in element:
                                                                print(f"an older file exists for {filename} -> {object[2][object[0].index(entry)]}")
                                                                if not object[2][
                                                                           object[0].index(entry)] in systems_to_update:
                                                                    systems_to_update.append(
                                                                        object[2][object[0].index(entry)])
                                                                if not element in old_files:
                                                                    old_files.append(element)
                                                        else:
                                                            if f"{filename.split('-')[0]}" in element and f"{filename.split('-')[2]}" in element:
                                                                print(f"an older file exists for {filename} -> {object[2][object[0].index(entry)]}")
                                                                if not object[2][
                                                                           object[0].index(entry)] in systems_to_update:
                                                                    systems_to_update.append(
                                                                        object[2][object[0].index(entry)])
                                                                if not element in old_files:
                                                                    old_files.append(element)
                                        else:
                                            if exists(file_download_path):
                                                for element in os.listdir(file_download_path):
                                                    if f"{filename.split('-')[0]}" in element:
                                                        print(f"an older file exists for {filename} -> {object[2][object[0].index(entry)]}")
                                                        if not object[2][object[0].index(entry)] in systems_to_update:
                                                            systems_to_update.append(object[2][object[0].index(entry)])
                                                        if not element in old_files:
                                                            old_files.append(element)
                            case "garuda":
                                if exists(file_download_path):
                                    for element in os.listdir(file_download_path):
                                        if f"{filename.split(filename.split('-')[-1])[0]}" in element:
                                            print(f"an older file exists for {filename} -> {object[2][object[0].index(entry)]}")
                                            if not object[2][object[0].index(entry)] in systems_to_update:
                                                systems_to_update.append(object[2][object[0].index(entry)])
                                            if not element in old_files:
                                                old_files.append(element)
                            case "kali":
                                if exists(file_download_path):
                                    for element in os.listdir(file_download_path):
                                        if f"{filename.split('-')[0]}" in element and f"{filename.split('-')[3]}" in element and f"{filename.split('-')[4]}" in element:
                                            print(f"an older file exists for {filename} -> {object[2][object[0].index(entry)]}")
                                            if not object[2][object[0].index(entry)] in systems_to_update:
                                                systems_to_update.append(object[2][object[0].index(entry)])
                                            if not element in old_files:
                                                old_files.append(element)
                            case "mint":
                                if exists(file_download_path):
                                    for element in os.listdir(file_download_path):
                                        if f"{filename.split('-')[0]}" in element and f"{filename.split('-')[2]}" in element:
                                            print(f"an older file exists for {filename} -> {object[2][object[0].index(entry)]}")
                                            if not object[2][object[0].index(entry)] in systems_to_update:
                                                systems_to_update.append(object[2][object[0].index(entry)])
                                            if not element in old_files:
                                                old_files.append(element)
                            case "manjaro":
                                if exists(file_download_path):
                                    for element in os.listdir(file_download_path):
                                        if f"{filename.split('-')[0]}" in element and f"{filename.split('-')[2]}" in element:
                                            print(f"an older file exists for {filename} -> {object[2][object[0].index(entry)]}")
                                            if not object[2][object[0].index(entry)] in systems_to_update:
                                                systems_to_update.append(object[2][object[0].index(entry)])
                                            if not element in old_files:
                                                old_files.append(element)

                clear()
                terminal_menu_update = TerminalMenu(systems_to_update, multi_select=True)
                selection = terminal_menu_update.show()
                os_update_list = []
                if selection:
                    for entry in selection:
                        os_update_list.append(systems_to_update[entry])

                    if os_update_list:
                        for entry in os_update_list:
                            if not exists(f"{object[1][object[2].index(entry)]}/old"):
                                os.makedirs(f"{object[1][object[2].index(entry)]}/old")
                            shutil.move(f"{object[1][object[2].index(entry)]}/{old_files[systems_to_update.index(entry)]}", f"{object[1][object[2].index(entry)]}/old/{old_files[systems_to_update.index(entry)]}")

                        update(os_update_list, TEST_FTP_CONNECTION)
                        cleanup_old_files()
                else:
                    print("Nothing selected to update")
            case 2:
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
                    clear()
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
                            clear()
                            system_index = terminal_menu_3.show()
                            if system_index == exit_pos_2:
                                run3 = False
                            elif system_index == 0:
                                update_list = []
                                for element in systems:
                                    update_list.append(element.split('.')[0])

                                update(update_list, TEST_FTP_CONNECTION)
                            else:
                                update([temp[system_index].split(".")[0]], TEST_FTP_CONNECTION)
            case 3:
                pass
            case 4:
                pass
            case 5:
                cleanup_old_files()
                run = False
            case 6:
                run = False


if __name__ == "__main__":
    main()
