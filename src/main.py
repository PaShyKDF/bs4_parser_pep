import logging
import re
from urllib.parse import urljoin
from collections import defaultdict

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from constants import BASE_DIR, EXPECTED_STATUS, MAIN_DOC_URL, MAIN_PEP_URL
from configs import configure_argument_parser, configure_logging
from outputs import control_output
from utils import find_tag, get_response


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    response = get_response(session, whats_new_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})
    sections_by_python = div_with_ul.find_all(
        'li', attrs={'class': 'toctree-l1'}
    )
    results = [('Ссылка на статью', 'Заголовок', 'Редактор, Автор')]
    for section in tqdm(sections_by_python):
        version_a_tag = find_tag(section, 'a')
        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)
        response = requests_cache.CachedSession()
        response = get_response(session, version_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, features='lxml')
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append((version_link, h1.text, dl_text))
    return results


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, 'lxml')
    sidebar = find_tag(soup, 'div', attrs={'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')
    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise Exception('Ничего не нашлось')
    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern, a_tag.text)
        if text_match is not None:
            version, status = text_match.groups()
        else:
            version, status = a_tag.text, ''
        results.append(
            (link, version, status)
        )
    return results


def download(session):

    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    response = get_response(session, downloads_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, 'lxml')
    table_tag = find_tag(soup, 'table', attrs={'class': 'docutils'})
    pdf_a4_tag = find_tag(
        table_tag, 'a', attrs={'href': re.compile(r'.+pdf-a4\.zip$')}
    )
    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)
    filename = archive_url.split('/')[-1]

    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename

    response = get_response(session, downloads_url)
    if response is None:
        return

    with open(archive_path, 'wb') as file:
        file.write(response.content)
    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    configure_logging()
    response = get_response(session, MAIN_PEP_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    count_of_pep_in_status = defaultdict(int)
    total_count_of_pep = 0
    warnings = []
    section_tag = find_tag(soup, 'section', attrs={'id': 'numerical-index'})
    tbody_tag = find_tag(section_tag, 'tbody')
    rows = tbody_tag.find_all('tr')
    for row in tqdm(rows):
        type_and_status_in_tabel = find_tag(row, 'abbr').text
        if len(type_and_status_in_tabel) == 2:
            status_in_table = type_and_status_in_tabel[1]
        else:
            status_in_table = ''
        pep_page_link = find_tag(
            row, 'a', attrs={'class': 'pep reference internal'}
        ).get('href')
        pep_page_url = urljoin(MAIN_PEP_URL, pep_page_link)
        pep_page_response = get_response(session, pep_page_url)
        if response is None:
            return
        soup = BeautifulSoup(pep_page_response.text, features='lxml')
        pep_info = find_tag(soup, 'section', attrs={'id': 'pep-content'})
        for dt in pep_info.find_all('dt'):
            if dt.text == 'Status:':
                status_in_page = dt.find_next_sibling().text
                break
        if status_in_page not in EXPECTED_STATUS[status_in_table]:
            warnings.append(f'{pep_page_url}\n'
                            f'Статус в карточке: {status_in_page}\n'
                            'Ожидаемые статусы: '
                            f'{EXPECTED_STATUS[status_in_table]}')
        count_of_pep_in_status[status_in_page] += 1
        total_count_of_pep += 1
    logging.warning('\n'.join(warnings))
    result = [('Status', 'Count')]
    result.extend(count_of_pep_in_status.items())
    result.append(('Total', total_count_of_pep))
    return result


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')
    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')
    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()
    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)
    if results is not None:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
