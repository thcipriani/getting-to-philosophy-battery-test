#!/usr/bin/env python3

import argparse
import csv
import pathlib
import re

from datetime import datetime, timezone

import psutil
import yaml

from selenium import webdriver

BASE_PATH = pathlib.Path(__file__).absolute()
INPUT_FILE = BASE_PATH.parent / 'pageviews.wmcloud.org-top400.yaml'
OUTPUT_FILE = BASE_PATH.parent / 'philosophy-battery-test.csv'

EN_WIKI = 'https://en.wikipedia.org/wiki'
PHILOSOPHY = f'{EN_WIKI}/Philosophy'

WP_NAMESPACES = [
    'User',
    'User_talk',
    'Wikipedia',
    'Wikipedia_talk',
    'File',
    'File_talk',
    'MediaWiki',
    'MediaWiki_talk',
    'Template',
    'Template_talk',
    'Help',
    'Help_talk',
    'Category',
    'Category_talk',
    'Portal',
    'Portal_talk',
    'Draft',
    'Draft_talk',
    'TimedText',
    'TimedText_talk',
    'Module',
    'Module_talk',
    'Gadget',
    'Gadget_talk',
    'Gadget_definition',
    'Gadget_definition_talk',
]

NS_REGEX = re.compile(rf'^{EN_WIKI}/({r"|".join(WP_NAMESPACES)})')


class BatteryLog:
    def __init__(self, f):
        self.file = f
        self.writer = csv.writer(f)
        self.writer.writerow([
            'Timestamp',
            'Load',
            'Battery Percent',
            'Battery Seconds Remaining',
            'Page'])

    def log(self, current_page):
        timestamp = datetime.now(timezone.utc).isoformat()
        battery = psutil.sensors_battery()
        one_min_load = [
            x / psutil.cpu_count() * 100
            for x in psutil.getloadavg()
        ][0]
        self.writer.writerow([
            timestamp,
            one_min_load,
            battery.percent,
            battery.secsleft,
            current_page
        ])
        self.file.flush()
        print(f'{timestamp}, {one_min_load}, {battery.percent}, {battery.secsleft}, {current_page}')


def get_first_page_link(page, driver):
    driver.get(page)
    try:
        mw_parser_output = driver.find_elements(
            'css selector',
            '.mw-content-ltr.mw-parser-output > p'
        )
        first_paragraph = [
            x for x in mw_parser_output if x.text
        ][0]
        first_link = [
            y for y in
            first_paragraph.find_elements('tag name', 'a')
            if is_link_valid(y, page)
        ]
        return first_link[0].get_attribute('href')
    except Exception as e:
        print(f'No link found for {e} on {page}')
        return None


def is_link_valid(link, page):
    link_href = link.get_attribute('href')
    if not link_href.startswith(EN_WIKI):
        return False
    if 'cite_note' in link_href:
        return False
    if link_href.startswith(f'{page}#') or link_href.startswith('#'):
        return False
    if NS_REGEX.match(link_href):
        return False
    return True


def run_test(pages, driver, battery):
    for page in pages:
        seen = {}
        break_loop = False
        current_page = page

        while True:
            battery.log(current_page)
            first_link = get_first_page_link(current_page, driver)
            if seen.get(first_link):
                print(f'Loop detected for {page}')
                break_loop = True
            if first_link == PHILOSOPHY:
                print(f'Found philosophy for {page}')
                break_loop = True
            seen[first_link] = True
            if break_loop:
                for l,_ in seen.items():
                    print(f'\t- {l}')
                break

            current_page = first_link


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--input',
        '-i',
        type=pathlib.Path,
        default=INPUT_FILE,
        help='yaml file of pages to test'
    )
    ap.add_argument(
        '--output',
        '-o',
       type=pathlib.Path,
       default=OUTPUT_FILE,
       help='csv file to write battery test results to'
    )
    args = ap.parse_args()
    return args.input, args.output


def main():
    pages_file, output_file = parse_args()
    with open(pages_file, 'r') as f:
        pages = yaml.safe_load(f)

    test_pass = 1

    options = webdriver.FirefoxOptions()
    driver = webdriver.Firefox(options=options)
    try:
        with open(output_file, 'a') as f:
            battery = BatteryLog(f)
            while True:
                print(f'Starting battery test, PASS {test_pass}...')
                run_test(pages, driver, battery)
                test_pass += 1
    except KeyboardInterrupt:
        driver.quit()
        raise SystemExit('Keyboard interrupt detected, exiting...')


if __name__ == '__main__':
    main()
