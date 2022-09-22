#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import os
import re
import json
import time
import argparse
from urllib import request, parse
from dotenv import load_dotenv

load_dotenv()
DEEPL_API_ENDPOINT = "https://api-free.deepl.com/v2/translate"
SLEEP_BETWEEN_API_CALLS = 0.01  # Seconds
INDENTATION_DEFAULT = 2
ENCODING = "utf-8"
GLOBAL_CACHE = dict()


def find_files(path: str) -> list:
    """
    Find all json files in folder

    :param path: directory path to list files
    :return: files in directory
    """
    return [file for file in os.listdir(path) if re.search(r"\.json$", file)]


def get_input_file(json_files: list, input_dir: str) -> str:
    """
    Get input file from folder

    :param json_files: list of files in directory
    :param input_dir: directory containing these files
    :return: file to translate
    """
    if len(json_files) == 0:
        print("No files found")
        exit()

    if len(json_files) == 1:
        return json_files[0]

    if len(json_files) > 1:
        print("Choose the file to use as source file:")
        for idx, file in enumerate(json_files):
            print(f"[{idx}] {file}")

        file_idx = input("Type file number: ")
        return os.path.join(input_dir, json_files[int(file_idx)])


def get_output_file(output: str, lang_code: str, input_file: str, auto_override:bool = False) -> str:
    """
    Get output file

    :param output: output file
    :param lang_code: output file language code
    :param input_file: input file
    :return: file to output translations
    """
    output_file_name = output if output else f"{lang_code}.json"
    if not output_file_name.endswith(".json"):
        output_file_name += ".json"
    output_file = os.path.join(os.path.dirname(input_file), output_file_name)
    if auto_override == True and os.path.exists(output_file):
        override = input(
            f"File {output_file_name} already exists. Do you want to override it? [Y/N] "
        )
        if not override.lower() in ("y", "yes"):
            output_file_name = input(f"Enter the new file name: ")
            if not output_file_name.endswith(".json"):
                output_file_name += ".json"

            return os.path.join(os.path.dirname(input_file), output_file_name)
    return output_file


def get_target_lang_code(locale: str) -> str:
    """
    Get language code from input

    :param locale: locate target to use
    :return: output locale code
    """
    lang_code = "" if not locale else locale
    while len(lang_code) != 2:
        lang_code = input("Language code to translate to (2 letters): ")

    return lang_code


def get_strings_from_file(
    filepath: str,
    output_file: str,
    target_locale: str,
    sleep: float,
    skip: list = None,
    keep: list = None,
    cache: bool = None
) -> dict:
    """
    Get translated strings from file

    :param filepath: file path to translate
    :param target_locale: locale to translate
    :param sleep: sleep time between API calls
    :param skip: list of keys to ignore
    :param keep: list of keys to keep
    :return: translated file
    """
    if skip is None:
        skip = []
    if keep is None:
        keep = []

    with open(filepath) as f:
        data = json.load(f)
        try:
            with open(output_file) as out_f:
                existing = json.load(out_f)
        except FileNotFoundError:
            existing = {}
            
        return iterate_translate(
            data=data,
            target_locale=target_locale,
            sleep=sleep,
            skip=skip,
            keep=keep,
            existing=existing,
            cache=cache
        )


def iterate_translate(data: dict, target_locale: str, sleep: float, skip: list, keep:list, existing:dict, cache:bool):
    """
    Iterate on data and translate the corresponding values

    :param data: data to iterate
    :param target_locale: language into which the data will be translated
    :param sleep: sleep time between calls
    :param skip: list of keys to skip (no translate)
    :param keep: list of keys to keep (translate)
    :param existing: data already existing
    :parem cache: enable cache
    :return: translated block
    """
    if isinstance(data, dict):
        # Value is hierarchical, so iterate it
        res = dict()
        for key, value in data.items():
            if key in skip:
                res[key] = value
            # keep if key is in keep list and existing[key] exist and is not null nor empty
            elif key in keep and existing and existing[key] is not None and existing[key] != "":
                res[key] = existing[key]
            elif key in GLOBAL_CACHE:
                res[key] = GLOBAL_CACHE[key]
            else:
                res[key] = iterate_translate(data=value, target_locale=target_locale, sleep=sleep, skip=skip, keep=keep, existing=existing, cache=cache)
        return res

    if isinstance(data, list):
        # Value is multiple, so iterate it
        return [iterate_translate(data=value, target_locale=target_locale, sleep=sleep, skip=skip, keep=keep, existing=existing, cache=cache) for value in data]

    if isinstance(data, str):
        # Value is string, so translate it
        if data == "":
            return data

        return translate_string(data, target_locale, sleep, cache)

    if isinstance(data, bool) or isinstance(data, int) or isinstance(data, float):
        # Value is boolean or numerical, return same value
        return data


def translate_string(text: str, target_locale: str, sleep: float, cache: dict = None):
    """
    Translate a specifig string

    Test with curl:
    $ curl https://api-free.deepl.com/v2/translate -d auth_key=YOUR-API-KEY-HERE -d "text=Hello, world!" -d "target_lang=ES"

    :param text: string to translate
    :param target_locale: language into which the data will be translated
    :param sleep: sleep time between calls
    :param cache: cache object
    :return: string translation
    """
    global GLOBAL_CACHE
    if type(text) != type(str()):
        return text

    if cache is not None:
        try:
            res = GLOBAL_CACHE[text]
            print("Using cache: ", text, " -> ", res)
            return res
        except KeyError:
            pass

    time.sleep(sleep)

    data = parse.urlencode(
        {
            "target_lang": target_locale,
            "auth_key": os.environ.get("DEEPL_AUTH_KEY"),
            "text": text,
            "preserve_formatting": "1",
        }
    ).encode()

    req = request.Request(DEEPL_API_ENDPOINT, data=data)
    response = request.urlopen(req)

    if response.status != 200:
        print(f"{text}  ->  ERROR (response status {response.status})")
        return text

    response_data = json.loads(response.read())

    if not "translations" in response_data:
        print(f"{text}  ->  ERROR (response empty {response_data})")
        return text

    # print(text, " -> ", response_data["translations"][0]["text"])

    if len(response_data["translations"]) > 1:
        print(f"({text}) More than 1 translation: {response_data['translations']}")

    dec_text = decode_text(response_data["translations"][0]["text"])
    # if cache:
    #     cache[text] = dec_text
    return dec_text


def decode_text(text: str) -> str:
    return str(text)


def save_results_file(data: dict, output_file: str, indent: int = 2, cache_file:str = '') -> None:
    """
    Write output file

    :param data: dict object to dump into file
    :param output_file: output file path
    :param indent: json indentation
    :param cache_file: cache file path
    """
    with open(output_file, "w") as file:
        json.dump(data, file, indent=indent, ensure_ascii=False)

    if(cache_file != None):
        with open(cache_file, "w") as file:
            json.dump(data, file, indent=indent, ensure_ascii=False)
        
    print(f"Results saved on {output_file}")


# get cache folder, if not existing create it
def get_cache_folder():
    folder = os.getcwd() + "/.cache_locale"
    if not os.path.exists(folder):
        os.makedirs(folder)
    return folder
    
def main():
    if not os.environ.get("DEEPL_AUTH_KEY", False):
        raise Exception("Environment variables not loaded")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "file",
        help="Folder or file to look for translation source",
    )
    parser.add_argument(
        "-l",
        "--locale",
        default="en",
        help="Language target to translate",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="en.json",
        help="Output file name",
    )
    parser.add_argument(
        "-i",
        "--indent",
        type=int,
        default=INDENTATION_DEFAULT,
        help="Indentation spaces",
    )
    parser.add_argument(
        "-s",
        "--sleep",
        type=float,
        default=SLEEP_BETWEEN_API_CALLS,
        help="Sleep time between API calls",
    )
    parser.add_argument(
        "--skip",
        nargs="+",
        help="Keys to skip",
    )
    parser.add_argument(
        "--keep",
        nargs="+",
        help="Keys to keep",
    )
    
    parser.add_argument(
        "--cache",
        type=bool,
        default=True,
        nargs="+",
        help="use a file cache",
    )
    
    parser.add_argument(
        "--nocache",
        nargs="+",
        help="Keys to burst cache",
    )
    
    parser.add_argument(
        "--override",
        type=bool,
        default=False,
        nargs="+",
        help="Override existing file",
    )
      
    args = parser.parse_args()

    input_dir = os.path.normpath(args.file)

    if os.path.isdir(input_dir):
        json_files = find_files(input_dir)
        input_file = get_input_file(json_files, input_dir)
    else:
        if not input_dir.endswith(".json"):
            print("You must select a json file or a folder containing json files")
            exit()
        if not os.path.isfile(os.path.normpath(input_dir)):
            print("File not found")
            exit()
        input_file = os.path.normpath(input_dir)

    lang_code = get_target_lang_code(args.locale)
    json_file_name = os.path.basename(input_file).split(".")[0]

    if lang_code.lower() == json_file_name.lower():
        print("You are trying to translate the same language!")
        exit()
    
    # if cache is enable, load json file into global cache
    
    cache_file = os.path.join(get_cache_folder(),lang_code + '.json') if args.cache else None
    
    if args.cache:
        try:
            with open(cache_file) as f:
                global GLOBAL_CACHE
                GLOBAL_CACHE = json.load(f)
                if args.nocache:
                    for key in args.nocache:
                        GLOBAL_CACHE.pop(key, None)
        except FileNotFoundError:
            pass
                                     

    output_file = get_output_file(args.output, lang_code, input_file, auto_override=args.override)
    results = get_strings_from_file(
        input_file, output_file, lang_code.upper(), args.sleep, args.skip,args.keep, args.cache
    )
    save_results_file(results, output_file, args.indent, cache_file if args.cache else None)


if __name__ == "__main__":
    main()
