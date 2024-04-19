import sys
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import validators
import undetected_chromedriver as uc
import os
import argparse
import logging

USER_PROFILE_DIRECTORY = "profile"
BASE_URL = "https://www.google.com/"


def setup_logger(name, log_file, level=logging.INFO, console_handler=True):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if console_handler:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    else:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# setup logger
logger = setup_logger("colabctl", "colabctl.log", console_handler=False)


def sleep(seconds):
    for i in range(seconds):
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            return


def exists_by_xpath(driver, thex, howlong):
    try:
        WebDriverWait(driver, howlong).until(
            EC.visibility_of_element_located((By.XPATH, thex))
        )
        return True
    except (NoSuchElementException, TimeoutException) as e:
        logger.warning(f"the element not found by xpath {thex} after waiting for {howlong}")
        return False


def wait_for_xpath(driver, x, timeout=100):
    start_time = time.time()
    while True:
        try:
            element = driver.find_element(By.XPATH, x)
            if element:
                return True
        except:
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                return False
            time.sleep(0.1)


def scroll_to_bottom(driver, scroll_pause_time=0.5):
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        # Scroll down to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        # Wait to load page
        time.sleep(scroll_pause_time)
        # Calculate new scroll height and compare with last scroll height
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def file_to_list(filename):
    colabs = []
    try:
        with open(filename, 'r') as file:
            for line in file:
                clean_line = line.strip()
                if validators.url(clean_line):
                    colabs.append(clean_line)
    except IOError as e:
        logger.critical(f"Error opening or reading the file: {e}")
    return colabs


def wait_for_login(profile_directory):
    chrome_options_gui = uc.ChromeOptions()
    chrome_options_gui.add_argument("--no-sandbox")
    chrome_options_gui.add_argument("--disable-infobars")
    chrome_options_gui.add_argument(f"--user-data-dir={profile_directory}")
    driver = uc.Chrome(options=chrome_options_gui)
    driver.get("https://accounts.google.com/signin")
    wait_for_xpath(
        driver,
        '//*[@id="yDmH0d"]/c-wiz/div/div[2]/div/c-wiz/c-wiz/div/div[3]/div/div/header/div[2]',
    )
    driver.close()
    driver.quit()


def handle_login(profile_directory, test_colab_url):
    if not os.path.isdir(profile_directory):
        logger.warning(f"Profile directory {profile_directory} does not exist...please login")
        # login now
        wait_for_login(profile_directory)
    else:
        logger.info("User profile directory found..trying to load first url for test")
        chrome_options = uc.ChromeOptions()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-infobars")
        driver = uc.Chrome(options=chrome_options, user_data_dir=profile_directory)
        driver.get(test_colab_url)
        sleep(10)
        # check if the request access is asked
        if 'Access Denied' in driver.title:
            logger.error(f"Access Denied to the colab url {test_colab_url},maybe you don't have access to this colab")
        file_found = wait_for_xpath(driver, '//*[@id="file-menu-button"]/div/div/div[1]')
        if file_found:
            logger.info("File found in menu bar...")
            logger.info("Login detected...restarting and starting new session")
        else:
            logger.critical("Loding error,please restart the script...")
        driver.close()
        driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Colab cron job")
    parser.add_argument("fork", type=str, help="Identifier for completion")
    parser.add_argument("timeout", type=int, help="Timeout in seconds")
    parser.add_argument("--filename", type=str, default="notebooks.csv", help="File containing colab URLs")

    args = parser.parse_args()

    colab_urls = file_to_list(args.filename)
    if len(colab_urls) == 0:
        logger.critical("No valid notebook URLs found")
        raise Exception("No valid notebook URLs found")

    handle_login(profile_directory=USER_PROFILE_DIRECTORY, test_colab_url=colab_urls[0])

    chrome_options = uc.ChromeOptions()
    # chrome_options.add_argument("--headless")  # uncomment for headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    wd = uc.Chrome(options=chrome_options, user_data_dir=USER_PROFILE_DIRECTORY)
    wd.get(BASE_URL)
    while True:
        for each_url in colab_urls:
            # switch to new tab
            wd.switch_to.new_window()
            sleep(5)
            wd.get(each_url)
            running = False
            wait_for_xpath(wd, '//*[@id="file-menu-button"]/div/div/div[1]')  # find 'File' option
            logger.info(f"Notebook loaded...{each_url}")
            sleep(10)
            try:
                if not running:
                    # clear all cell outputs
                    logger.info("Clearing all cell outputs")
                    wd.find_element(By.TAG_NAME, "body").send_keys(

                        Keys.CONTROL + Keys.SHIFT + "Q"
                    )
                    sleep(3)

                    # reset all runtimes
                    wd.find_element(By.TAG_NAME, "body").send_keys(
                        Keys.CONTROL + Keys.SHIFT + "K"
                    )
                    sleep(3)
                    # click on 'Ok' for resetting the runtime
                    if exists_by_xpath(wd, '//mwc-dialog[@class="yes-no-dialog"]', 10):
                        logger.info("Resetting all runtimes")
                        ok_button = wd.find_element(By.XPATH,
                                                    '//mwc-dialog[@class="yes-no-dialog"]//mwc-button['
                                                    '@dialogaction="ok"]')

                        ok_button.click()

                    sleep(5)
                    # run all cells
                    logger.info("Running all cells...")
                    wd.find_element(By.TAG_NAME, "body").send_keys(
                        Keys.CONTROL + Keys.SHIFT + 'L'
                    )
                    running = True
            except NoSuchElementException as e:
                logger.warning(f"Error while clearing/resetting/running all cells :{e}")
            while running:
                try:
                    wd.find_element(
                        By.CSS_SELECTOR, ".notebook-content-background"
                    ).click()

                    scroll_to_bottom(wd)
                except Exception as e:
                    logger.warning(f"Error while scrolling to the buttom: {e}")
                cell_outputs = wd.find_elements(By.XPATH, "//pre")
                for output in cell_outputs:
                    if args.fork in output.text:
                        running = False
                        logger.info("Completion string found. Waiting for next cycle.")
                        break
            wd.close()
            wd.switch_to.window(wd.window_handles[0])

        logger.info(f"Sleeping for {args.timeout}")
        sleep(args.timeout)


if __name__ == "__main__":
    main()
