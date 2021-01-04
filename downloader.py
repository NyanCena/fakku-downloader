import os
import pickle
import re

from shutil import rmtree
from time import sleep

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, JavascriptException

from bs4 import BeautifulSoup as bs
from tqdm import tqdm

BASE_URL = 'https://www.fakku.net'
LOGIN_URL = f'{BASE_URL}/login/'
# Initial display settings for headless browser. Any manga in this
# resolution will be opened correctly and with the best quality.
MAX_DISPLAY_SETTINGS = [1440, 2560]
# Path to headless driver
EXEC_PATH = 'chromedriver.exe'
# File with manga urls
URLS_FILE = 'urls.txt'
# File with completed urls
DONE_FILE = 'done.txt'
# File with prepared cookies
COOKIES_FILE = 'cookies.pickle'
# Root directory for manga downloader
ROOT_MANGA_DIR = 'manga'
# Timeout to page loading in seconds
TIMEOUT = 5
# Wait between page loading in seconds
WAIT = 0.75


def program_exit():
    print('Program exit.')
    exit()


class FDownloader():
    """
    Class which allows download manga.
    The main idea of download - using headless browser and just saving
    screenshot from that. Because canvas in fakku.net is protected
    from download via simple .toDataURL js function etc.
    """
    def __init__(self,
            urls_file=URLS_FILE,
            done_file=DONE_FILE,
            cookies_file=COOKIES_FILE,
            root_manga_dir=ROOT_MANGA_DIR,
            driver_path=EXEC_PATH,
            default_display=MAX_DISPLAY_SETTINGS,
            timeout=TIMEOUT,
            wait=WAIT,
            login=None,
            password=None,
        ):
        """
        param: urls_file -- string name of .txt file with urls
            Contains list of manga urls, that's to be downloaded
        param: done_file -- string name of .txt file with urls
            Contains list of manga urls that have successfully been downloaded
        param: cookies_file -- string name of .picle file with cookies
            Contains bynary data with cookies
        param: driver_path -- string
            Path to the headless driver
        param: default_display -- list of two int (width, height)
            Initial display settings. After loading the page, they will be changed
        param: timeout -- float
            Timeout upon waiting for page to load
            If <5 may be poor quality.
        param: wait -- float
            Wait in seconds beetween pages downloading.
            If <1 may be poor quality.
        param: login -- string
            Login or email for authentication
        param: password -- string
            Password for authentication
        """
        self.urls_file = urls_file
        self.urls = self.__get_urls_list(urls_file, done_file)
        self.done_file = done_file
        self.cookies_file = cookies_file
        self.root_manga_dir = root_manga_dir
        self.driver_path = driver_path
        self.browser = None
        self.default_display = default_display
        self.timeout = timeout
        self.wait = wait
        self.login = login
        self.password = password

    def init_browser(self, headless=False):
        """
        Initializing browser and authenticate if necessary
        ---------------------
        param: headless -- bool
            If True: launch browser in headless mode(for download manga)
            If False: launch usualy browser with GUI(for first authenticate)
        """
        options = Options()
        options.headless = headless
        self.browser = webdriver.Chrome(
            executable_path=self.driver_path,
            chrome_options=options
        )
        if not headless:
            self.__auth()
        self.__set_cookies()
        self.browser.set_window_size(*self.default_display)

    def __set_cookies(self):
        self.browser.get(LOGIN_URL)
        #self.browser.delete_all_cookies()
        with open(self.cookies_file, 'rb') as f:
            cookies = pickle.load(f)
            for cookie in cookies:
                if 'expiry' in cookie:
                    cookie['expiry'] = int(cookie['expiry'])
                    self.browser.add_cookie(cookie)
        # self.browser.get(LOGIN_URL)

    def __init_headless_browser(self):
        """
        Recreating browser in headless mode(without GUI)
        """
        options = Options()
        options.headless = True
        self.browser = webdriver.Chrome(
            executable_path=self.driver_path,
            chrome_options=options)

    def __auth(self):
        """
        Authentication in browser with GUI for saving cookies in first time
        """
        self.browser.get(LOGIN_URL)
        if not self.login is None:
            self.browser.find_element_by_id('username').send_keys(self.login)
        if not self.password is None:
            self.browser.find_element_by_id('password').send_keys(self.password)
        self.browser.find_element_by_class_name('js-submit').click()

        ready = input("Tab Enter to continue after you login...")
        with open(self.cookies_file, 'wb') as f:
            pickle.dump(self.browser.get_cookies(), f)

        self.browser.close()
        # Recreating browser in headless mode for next manga downloading
        self.__init_headless_browser()

    def load_all(self):
        """
        Just main function which opening each page and save it in .png
        """
        self.browser.set_window_size(*self.default_display)
        if not os.path.exists(self.root_manga_dir):
            os.mkdir(self.root_manga_dir)
        with open(self.done_file, 'a') as done_file_obj:
            for url in self.urls:
                manga_name = url.split('/')[-1]
                manga_folder = os.sep.join([self.root_manga_dir, manga_name])
                if not os.path.exists(manga_folder):
                   os.mkdir(manga_folder)
                self.browser.get(url)
                self.waiting_loading_page(is_reader_page=False)
                page_count = self.__get_page_count(self.browser.page_source)
                print(f'Downloading "{manga_name}" manga.')
                for page_num in tqdm(range(1, page_count + 1)):
                    self.browser.get(f'{url}/read/page/{page_num}')
                    self.waiting_loading_page(is_reader_page=True, is_first_page=(page_num == 1))

                    # Count of leyers may be 2 or 3 therefore we get different target layer
                    n = self.browser.execute_script("return document.getElementsByClassName('layer').length")
                    try:
                        # Resizing window size for exactly manga page size
                        width = self.browser.execute_script(f"return document.getElementsByTagName('canvas')[{n-2}].width")
                        height = self.browser.execute_script(f"return document.getElementsByTagName('canvas')[{n-2}].height")
                        self.browser.set_window_size(width, height)
                    except JavascriptException:
                        print('\nSome error with JS. Page source are note ready. You can try increase argument -t')

                    # Delete all UI
                    self.browser.execute_script(f"document.getElementsByClassName('layer')[{n-1}].remove()")
                    self.browser.save_screenshot(os.sep.join([manga_folder, f'{page_num}.png']))
                print('>> manga done!')
                done_file_obj.write(f'{url}\n')

    def load_urls_from_collection(self, collection_url):
        """
        Function which records the manga URLs inside a collection
        """
        self.browser.get(collection_url)
        self.waiting_loading_page(is_reader_page=False)
        page_count = self.__get_page_count_in_collection(self.browser.page_source)
        with open(self.urls_file, 'a') as f:
            for page_num in tqdm(range(1, page_count + 1)):
                if page_num != 1: #Fencepost problem, the first page of a collection is already loaded
                    self.browser.get(f'{collection_url}/page/{page_num}')
                    self.waiting_loading_page(is_reader_page=False)
                soup = bs(self.browser.page_source, 'html.parser')
                for div in soup.find_all('div', attrs={'class': 'book-title'}):
                    f.write(f"{BASE_URL}{div.find('a')['href']}\n")

    def __get_page_count(self, page_source):
        """
        Get count of manga pages from html code
        ----------------------------
        param: page_source -- string
            String that contains html code
        return: int
            Number of manga pages
        """
        soup = bs(page_source, 'html.parser')
        page_count = None
        if not page_count:
            try:
                divs = soup.find_all('div', attrs={'class': 'row'})
                page_count = int(next(x for x in divs if x(text="Pages"))
                    .find('div', attrs={'class': 'row-right'}).text
                    .split(' ')[0])
            except Exception as ex:
                print(ex)
        return page_count

    def __get_page_count_in_collection(self, page_source):
        """
        Get count of collection pages from html code
        ----------------------------
        param: page_source -- string
            String that contains html code
        return: int
            Number of collection pages
        """
        soup = bs(page_source, 'html.parser')
        page_count = None
        if not page_count:
            try:
                pagination_text = soup.find('div', attrs={'class': 'pagination-meta'}).text
                page_count = int(re.search("Page\s+\d+\s+of\s+(\d+)", pagination_text).group(1))
            except Exception as ex:
                print(ex)
        return page_count

    def __get_urls_list(self, urls_file, done_file):
        """
        Get list of urls from .txt file
        --------------------------
        param: urls_file -- string
            Name or path of .txt file with manga urls
        param: done_file -- string
            Name or path of .txt file with successfully downloaded manga urls
        return: urls -- list
            List of urls from urls_file
        """
        done = []
        with open(done_file, 'r') as donef:
            for line in donef:
                done.append(line.replace('\n',''))

        urls = []
        with open(urls_file, 'r') as f:
            for line in f:
                clean_line = line.replace('\n','')
                if clean_line not in done:
                    urls.append(clean_line)
        return urls

    def waiting_loading_page(self, is_reader_page=False, is_first_page=False):
        """
        Awaiting while page will load
        ---------------------------
        param: is_non_reader_page -- bool
            False -- awaiting of main manga page
            True -- awaiting of others manga pages
        param: is_first_page -- bool
            False -- the page num != 1
            True -- this is the first page, we need to wait longer to get good quality
        """
        if not is_reader_page:
            sleep(self.wait)
            elem_xpath = "//link[@type='image/x-icon']"
        elif is_first_page:
            sleep(self.wait * 3)
            elem_xpath = "//div[@data-name='PageView']"
        else:
            sleep(self.wait)
            elem_xpath = "//div[@data-name='PageView']"
        try:
            element = EC.presence_of_element_located((By.XPATH, elem_xpath))
            WebDriverWait(self.browser, self.timeout).until(element)
        except TimeoutException:
            print('\nError: timed out waiting for page to load. + \
                You can try increase param -t for more delaying.')
            program_exit()
