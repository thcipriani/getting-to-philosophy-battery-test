#!/usr/bin/env python3

import argparse
import csv
import pathlib
import re
import subprocess
import urllib.parse

from datetime import datetime, timezone

import psutil
import yaml

from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

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

NS_REGEX = re.compile(rf'^{EN_WIKI}/({r"|".join(WP_NAMESPACES)}):')


class BatteryLog:
    def __init__(self, f):
        self.file = f
        self.writer = csv.writer(f)
        cmd = 'find /sys/class/power_supply -name \'BAT*\''
        bat_folder = subprocess.check_output(cmd, shell=True, text=True).strip()
        self.voltage = pathlib.Path(bat_folder) / 'voltage_now'
        self.power = pathlib.Path(bat_folder) / 'current_now'
        self.track_watts = True
        if not (self.voltage.exists() and self.power.exists()):
            self.track_watts = False
        self.writer.writerow([
            'Timestamp',
            'CPU Percent',
            'Battery Percent',
            'Battery Seconds Remaining',
            'Page',
            'Watts',
        ])

    def log(self, current_page):
        timestamp = datetime.now(timezone.utc).isoformat()
        battery = psutil.sensors_battery()
        cpu = psutil.cpu_percent()
        watts = self.power_use()
        self.writer.writerow([
            timestamp,
            cpu,
            battery.percent,
            battery.secsleft,
            current_page,
            watts,
        ])
        self.file.flush()
        print(f'{timestamp}, {cpu}, {battery.percent}, {battery.secsleft}, {current_page}, {watts}')

    def power_use(self):
        if not self.track_watts:
            return '0W'
        with open(self.voltage) as f:
            cur_volts = int(f.read())
        with open(self.power) as f:
            cur_amps = int(f.read())
        cur_watts = cur_volts * cur_amps / 1000000 / 1000000
        return f'{cur_watts}W'

def remove_first_parenthetical_links(soup):
    within_parens = 0
    first_parens_done = False
    for string in soup.findAll(string=True):
        if within_parens != 0 and string.parent.name == 'a':
            string.parent.extract()
            first_parens_done = True
        if ')' in string.text:
            within_parens = within_parens - string.text.count(')')
            if within_parens == 0 and first_parens_done:
                return
        if '(' in string.text:
            within_parens += string.text.count('(')


def get_first_valid_link(page, element):
    html = element.get_attribute('innerHTML')
    soup = BeautifulSoup(html, 'html.parser')
    remove_first_parenthetical_links(soup)
    all_links = soup.find_all('a')
    for link in all_links:
        href = link.get('href')
        if href is None:
            continue
        # skip red links
        if 'new' in link.get('class', []):
            continue
        if href.startswith('/') or href.startswith('#'):
            href = urllib.parse.urljoin(page, href)
        if is_link_valid(href, page):
            return href


def get_first_page_link(page, driver):
    driver.get(page)
    mw_parser_output = driver.find_elements(
        By.CSS_SELECTOR,
        '.mw-content-ltr.mw-parser-output > p'
    )
    mw_parser_output += driver.find_elements(
        By.CSS_SELECTOR,
        '.mw-content-ltr.mw-parser-output > ul'
    )
    for p in mw_parser_output:
        first_valid_link = get_first_valid_link(page, p)
        if first_valid_link:
            return first_valid_link
    return None


def is_link_valid(link_href, page):
    if not link_href.startswith(EN_WIKI):
        return False
    if 'cite_note' in link_href:
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
            if first_link is None:
                print(f'NO LINKS!? Is "{page}" an article?')
                break_loop = True
            if seen.get(first_link):
                print(f'Loop detected for {page}')
                break_loop = True
            if first_link == PHILOSOPHY:
                print(f'Found philosophy for {page}')
                break_loop = True
            if first_link is not None:
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
