from os import environ
from time import time
from typing import Optional
from platform import system
from logging import DEBUG, Formatter, StreamHandler, getLogger
from asyncio import sleep, get_event_loop
from re import match
from bs4 import BeautifulSoup

from inscriptis import get_text

import zendriver
from zendriver.core.keys import SpecialKeys

from .internal.objects import Response, SearchResult, Theme
from .internal.selectors import DeepSeekSelectors
from .internal.exceptions import (MissingCredentials, InvalidCredentials, ServerDown, MissingInitialization, CouldNotFindElement,
                                  InvalidChatID)

class DeepSeek:
    def __init__(
        self,
        token: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        chat_id: Optional[str] = None,
        headless: bool = True,
        verbose: bool = False,
        chrome_args: list = [],
        attempt_cf_bypass: bool = True,
        browser_executable_path: Optional[str] = None,
        manual_login: bool = False,
        message_prefix: Optional[str] = None,
    ) -> None:
        """Initializes the DeepSeek object.

        Args
        ---------
        token: Optional[str]
            The token of the user.
        email: Optional[str]
            The email of the user.
        password: Optional[str]
            The password of the user.
        chat_id: str
            The chat id.
        headless: bool
            Whether to run the browser in headless mode.
        verbose: bool
            Whether to log the actions.
        chrome_args: list
            The arguments to pass to the Chrome browser.
        attempt_cf_bypass: bool
            Whether to attempt to bypass the Cloudflare protection.
        browser_executable_path: Optional[str]
            Path to Chrome/Chromium executable (e.g. /Applications/Google Chrome.app/Contents/MacOS/Google Chrome).
        manual_login: bool
            If True, open browser and wait until you log in manually; then script continues.
        message_prefix: Optional[str]
            Текст, подставляемый перед каждым запросом (например, инструкция «отвечай кратко, без воды»).
            None — без префикса.

        Raises
        ---------
        ValueError:
            Either the token or the email and password must be provided (unless manual_login=True).
        """
        if not manual_login and not token and not (email and password):
            raise MissingCredentials("Either the token alone or the email and password both must be provided")

        self._email = email
        self._password = password
        self._token = token
        self._chat_id = chat_id
        self._headless = headless
        self._verbose = verbose
        self._chrome_args = chrome_args
        self._attempt_cf_bypass = attempt_cf_bypass
        self._browser_executable_path = browser_executable_path
        self._manual_login = manual_login
        self._message_prefix = message_prefix or ""

        self._deepthink_enabled = False
        self._search_enabled = False
        self._initialized = False
        self.selectors = DeepSeekSelectors()

    async def initialize(self) -> None:
        """Initializes the DeepSeek session.

        This method sets up the logger, starts a virtual display if necessary, and launches the browser.
        It also navigates to the DeepSeek chat page and handles the login process using either a token
        or email and password.

        Raises
        ---------
        ValueError:
            PyVirtualDisplay is not installed.
        ValueError:
            Xvfb is not installed.
        """

        # Initilize the logger
        self.logger = getLogger("DeeperSeek")
        self.logger.setLevel(DEBUG)

        if self._verbose:
            handler = StreamHandler()
            handler.setFormatter(Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S"))
            self.logger.addHandler(handler)

        # Start the virtual display if the system is Linux and the DISPLAY environment variable is not set
        if system() == "Linux" and "DISPLAY" not in environ:
            self.logger.debug("Starting virtual display...")
            try:
                from pyvirtualdisplay.display import Display

                self.display = Display()
                self.display.start()
            except ModuleNotFoundError:
                raise ValueError(
                    "Please install PyVirtualDisplay to start a virtual display by running `pip install PyVirtualDisplay`"
                )
            except FileNotFoundError as e:
                if "No such file or directory: 'Xvfb'" in str(e):
                    raise ValueError(
                        "Please install Xvfb to start a virtual display by running `sudo apt install xvfb`"
                    )
                raise e

        # Start the browser (zendriver expects browser_args, not chrome_args)
        start_kw = dict(browser_args=self._chrome_args, headless=self._headless)
        if self._browser_executable_path:
            start_kw["browser_executable_path"] = self._browser_executable_path
        self.browser = await zendriver.start(**start_kw)

        self.logger.debug("Navigating to the chat page...")
        await self.browser.get("https://chat.deepseek.com/" if not self._chat_id \
            else f"https://chat.deepseek.com/a/chat/s/{self._chat_id}")

        if self._attempt_cf_bypass and not self._manual_login:
            try:
                self.logger.debug("Verifying the Cloudflare protection...")
                await self.browser.main_tab.verify_cf()
            except: # It times out if there was no need to verify
                pass
        
        self._initialized = True
        self._is_active = True
        loop = get_event_loop()
        loop.create_task(self._keep_alive())
        
        if self._manual_login:
            self.logger.debug("Manual login: log in in the browser window, script will continue when chat is ready...")
            last_err = None
            for selector_name, selector, timeout in [
                ("textbox", self.selectors.interactions.textbox, 25),
                ("textbox_fallback", self.selectors.interactions.textbox_fallback, 25),
                ("textarea", self.selectors.interactions.textbox_any, 550),
            ]:
                try:
                    tab = getattr(self.browser, "main_tab", None)
                    if tab is None:
                        raise RuntimeError("Browser window was closed")
                    await tab.wait_for(selector, timeout=timeout)
                    self.logger.debug("Chat ready, continuing.")
                    break
                except Exception as e:
                    last_err = e
                    if self.browser is None or getattr(self.browser, "main_tab", None) is None:
                        raise RuntimeError("Browser window was closed") from e
                    self.logger.debug("Selector %s: %s, trying next...", selector_name, e)
            else:
                if last_err:
                    raise last_err
        elif self._token:
            await self._login()
        else:
            await self._login_classic()
    
    async def _keep_alive(self) -> None:
        """Keeps the browser alive by refreshing the page periodically."""
        try:
            while self._is_active:
                await sleep(300)  # Sleep for 5 minutes (adjustable)
                if hasattr(self, "browser"):
                    # self.logger.debug("Refreshing the page to keep session alive...")
                    # await self.browser.main_tab.reload()
                    continue
        except Exception as e:
            self.logger.error(f"Keep-alive encountered an error: {e}")

    def __del__(self) -> None:
        """Destructor method to stop the browser and the virtual display."""
        self._is_active = False

    async def close(self) -> None:
        """Останавливает браузер. Вызывайте перед выходом из скрипта, чтобы избежать ошибки atexit."""
        self._is_active = False
        if getattr(self, "browser", None) is not None:
            try:
                await self.browser.stop()
            except Exception:
                pass
            self.browser = None

    async def _login(self) -> None:
        """Logs in to DeepSeek using a token.

        This method sets the token in the browser's local storage and reloads the page to authenticate.
        If the token is invalid, it falls back to the classic login method. (email and password)

        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        self.logger.debug("Logging in using the token...")
        # Экранируем токен для вставки в JS (кавычки и обратный слэш)
        token_escaped = self._token.replace("\\", "\\\\").replace("'", "\\'")
        await self.browser.main_tab.evaluate(
            f"localStorage.setItem('userToken', JSON.stringify({{value: '{token_escaped}', __version: '0'}}))",
            await_promise = True,
            return_by_value = True
        )
        await self.browser.main_tab.reload()
        await sleep(2)
        # Даём время на загрузку чата после reload
        try:
            await self.browser.main_tab.wait_for(self.selectors.interactions.textbox, timeout=30)
        except:
            self.logger.debug("Token failed, logging in using email and password...")

            if self._email and self._password:
                return await self._login_classic(token_failed = True)
            else:
                raise InvalidCredentials("The token is invalid and no email or password was provided")
    
        self.logger.debug("Token login successful!")
        
    async def _login_classic(self, token_failed: bool = False) -> None:
        """Logs in to DeepSeek using email and password.

        Args
        ---------
            token_failed (bool): Indicates whether the token login attempt failed.
        
        Raises:
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
            InvalidCredentials: If the email or password is incorrect.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        self.logger.debug("Entering the email and password...")
        email_input = await self.browser.main_tab.select(self.selectors.login.email_input)
        await email_input.send_keys(self._email)

        password_input = await self.browser.main_tab.select(self.selectors.login.password_input)
        await password_input.send_keys(self._password)

        self.logger.debug("Checking the confirm checkbox and logging in...")
        try:
            confirm_checkbox = await self.browser.main_tab.select(
                self.selectors.login.confirm_checkbox, timeout=5
            )
            await confirm_checkbox.click()
        except Exception:
            self.logger.debug("Checkbox not found or skipped, clicking login...")

        login_button = None
        used_selector = None
        for sel in (
            self.selectors.login.login_button,
            getattr(self.selectors.login, "login_button_fallback", "div[role=\"button\"]"),
        ):
            try:
                login_button = await self.browser.main_tab.select(sel, timeout=5)
                used_selector = sel
                break
            except Exception:
                continue
        if not login_button:
            raise CouldNotFindElement("Login button not found (tried button[type=submit] and div[role=button])")

        await login_button.click()
        try:
            escaped = used_selector.replace("\\", "\\\\").replace('"', '\\"')
            await self.browser.main_tab.evaluate(
                f'document.querySelector("{escaped}")?.click()',
                await_promise=True,
                return_by_value=True,
            )
        except Exception:
            pass
        await sleep(3)

        try:
            await self.browser.main_tab.wait_for(
                self.selectors.interactions.textbox, timeout=20
            )
        except Exception:
            try:
                await self.browser.main_tab.wait_for(
                    self.selectors.interactions.textbox_fallback, timeout=10
                )
            except Exception:
                raise InvalidCredentials("The email or password is incorrect" \
                    if not token_failed else "Both token and email/password are incorrect")

        self.logger.debug(f"Logged in successfully using email and password! {'(Token method failed)' if token_failed else ''}")
    
    async def _dev_debug(self) -> None:
        """A method for debugging purposes.
        
        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")
    
        while True:
            class_id = input("Enter the class id [e to exit]: ")
            if class_id == "e":
                break

            try:
                element = await self.browser.main_tab.select(f'div[class="{class_id}"]', timeout = 3)
            except:
                print("Invalid class id")
                continue
            
            print("breakpoint below")
            breakpoint()
        
    async def _find_child_by_text(
        self,
        parent: zendriver.Element,
        text: str,
        in_depth: bool = False,
        depth_limit: int = 10
    ) -> Optional[zendriver.Element]:
        """Finds a child element by it's text.

        Args
        ---------
            parent (zendriver.Element): The parent element.
            text (str): The text to find.
            in_depth (bool): Whether to search in depth.
            depth_limit (int): The depth limit to search in.

        Returns
        ---------
            Optional[zendriver.Element]: The child element if found, otherwise None.

        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        if in_depth: # not the best way to do this, but it works
            for child in parent.children:
                if child.text_all.lower() == text.lower():
                    return child
                
                if depth_limit:
                    found = await self._find_child_by_text(child, text, in_depth, depth_limit - 1)
                    if found:
                        return found
        else:
            for child in parent.children:
                if child.text_all.lower() == text.lower():
                    return child
        
        return None

    async def retrieve_token(self) -> Optional[str]:
        """Retrieves the token from the browser's local storage.
        
        Returns
        ---------
            Optional[str]: The token if found, otherwise None.
        
        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")
        
        return await self.browser.main_tab.evaluate(
            "JSON.parse(localStorage.getItem('userToken')).value",
            await_promise = True,
            return_by_value = True
        )

    async def send_message(
        self,
        message: str,
        slow_mode: bool = False,
        deepthink: bool = False,
        search: bool = False,
        timeout: int = 60,
        slow_mode_delay: float = 0.25
    ) -> Optional[Response]:
        """Sends a message to the DeepSeek chat.

        Args
        ---------
            message (str): The message to send.
            slow_mode (bool): Whether to send the message character by character with a delay.
            deepthink (bool): Whether to enable deepthink mode.
                - Setting this to True will add 20 seconds to the timeout.
            search (bool): Whether to enable search mode.
                - Setting this to True will add 60 seconds to the timeout.
            timeout (int): The maximum time to wait for a response.
                - Sometimes a response may take longer than expected, so it's recommended to increase the timeout if necessary.
                - Do note that the timeout increases by 20 seconds if deepthink is enabled, and by 60 seconds if search is enabled.
            slow_mode_delay (float): The delay between sending each character in slow mode.

        Returns
        ---------
            Optional[Response]: The generated response from DeepSeek, or None if no response is received within the timeout

        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        timeout += 20 if deepthink else 0
        timeout += 60 if search else 0

        payload = (self._message_prefix + message).strip() if self._message_prefix else message
        self.logger.debug("Finding the textbox and sending the message: %s", payload[:80] + ("..." if len(payload) > 80 else ""))
        textbox = await self.browser.main_tab.select(self.selectors.interactions.textbox, timeout=15)
        if slow_mode:
            for char in payload:
                await textbox.send_keys(char)
                await sleep(slow_mode_delay)
        else:
            await textbox.send_keys(payload)

        # DeepThink / Search toggles (optional, skip if selector missing)
        try:
            send_options_parent = await self.browser.main_tab.select(
                self.selectors.interactions.send_options_parent, timeout=3
            )
            if deepthink != self._deepthink_enabled:
                await self._click_toggle_by_index_or_text(send_options_parent, 0, "deepthink", ["think", "думать"])
                self._deepthink_enabled = deepthink
            if search != self._search_enabled:
                await self._click_toggle_by_index_or_text(send_options_parent, 1, "search", ["search", "поиск", "web"])
                self._search_enabled = search
        except Exception:
            pass

        # Отправка: клик по div[role="button"] (кнопка отправки) и Enter в поле ввода
        try:
            await self.browser.main_tab.evaluate(
                'document.querySelector(\'div[role="button"]\')?.click()',
                await_promise=True,
                return_by_value=True,
            )
        except Exception:
            pass
        await textbox.send_keys(SpecialKeys.ENTER)

        return await self._get_response(timeout = timeout)

    async def regenerate_response(self, timeout: int = 60) -> Optional[Response]:
        """Regenerates the response from DeepSeek.

        Args
        ---------
            timeout (int): The maximum time to wait for the response.

        Returns
        ---------
            Optional[Response]: The regenerated response from DeepSeek, or None if no response is received within the timeout
        
        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
            ServerDown: If the server is busy and the response is not generated.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        # Find the last response so I can access it's buttons
        toolbar = await self.browser.main_tab.select_all(self.selectors.interactions.response_toolbar)
        await toolbar[-1].children[1].click()

        return await self._get_response(timeout = timeout, regen = True)

    async def _click_toggle_by_index_or_text(
        self,
        parent: "zendriver.Element",
        fallback_index: int,
        label: str,
        text_substrings: list,
    ) -> None:
        """Кликает переключатель по индексу или по тексту (Search/Поиск, DeepThink и т.д.)."""
        try:
            children = getattr(parent, "children", [])
            if len(children) <= fallback_index:
                return
            text_lower = " ".join(text_substrings).lower()
            for i, child in enumerate(children):
                t = (getattr(child, "text_all", None) or "").lower()
                if any(s.lower() in t for s in text_substrings):
                    await child.click()
                    self.logger.debug("Toggled %s by text (child %s)", label, i)
                    return
            await children[fallback_index].click()
            self.logger.debug("Toggled %s by index %s", label, fallback_index)
        except Exception as e:
            self.logger.debug("Toggle %s: %s", label, e)
            raise

    def _filter_search_results(
        self,
        search_results_children: list,
    ):
        """Filters the search results and returns a list of SearchResult objects.

        Args
        ---------
            search_results_children (list): The search results children.

        Returns
        ---------
            list: A list of SearchResult objects.
        
        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        search_results = []
        for search_result in search_results_children:
            search_results.append(
                SearchResult(
                    image_url = BeautifulSoup(
                        str(search_result.children[0].children[0].children),
                        'html.parser'
                    ).find('img')['src'],
                    website = search_result.children[0].children[1].text_all,
                    date = search_result.children[0].children[2].text_all,
                    index = int(search_result.children[0].children[3].text_all),
                    title = search_result.children[1].text_all,
                    description = search_result.children[2].text_all
                )
            )
        
        return search_results

    async def _get_response(
        self,
        timeout: int = 60,
        regen: bool = False,
    ) -> Optional[Response]:
        """Waits for and retrieves the response from DeepSeek.

        Args
        ---------
            timeout (int): The maximum time to wait for the response.
            regen (bool): Whether the response is a regenerated response.

        Returns
        ---------
            Optional[Response]: The generated response from DeepSeek, or None if no response is received within the timeout.
        
        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
            ServerDown: If the server is busy and the response is not generated.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        end_time = time() + timeout
        # Ждём появления текста в последнем .ds-markdown (ответ ассистента) — без селекторов по хэшам
        self.logger.debug("Waiting for the response...")
        response_text = ""
        last_len = 0
        stable_count = 0
        get_last_markdown = (
            "(() => { const els = document.querySelectorAll('.ds-markdown'); "
            "return els.length ? els[els.length-1].innerText.trim() : ''; })()"
        )
        while time() < end_time:
            try:
                response_text = str(await self.browser.main_tab.evaluate(get_last_markdown)).strip()
            except Exception:
                response_text = ""
            if response_text and response_text.lower() != "the server is busy. please try again later.":
                if len(response_text) == last_len:
                    stable_count += 1
                    if stable_count >= 2:
                        break
                else:
                    stable_count = 0
                last_len = len(response_text)
            else:
                stable_count = 0
            await sleep(2)

        if not response_text:
            return None
        if response_text.lower() == "the server is busy. please try again later.":
            raise ServerDown("The server is busy. Please try again later.")

        self.logger.debug("Response received, extracting...")
        search_results = None
        deepthink_duration = None
        deepthink_content = None
        response_generated = None
        try:
            response_generated = await self.browser.main_tab.select_all(
                self.selectors.backend.response_generated_fallback, timeout=2
            )
        except Exception:
            pass
        try:
            children = getattr(response_generated[-1], "children", [])[1:3] if response_generated else []
        except (IndexError, TypeError):
            children = []
        for child in children:
            if match(r"found \d+ results", child.text.lower()) and self._search_enabled:
                self.logger.debug("Extracting the search results...")
                # So this is a search result option, we need to click it and find the search results div
                await child.click()

                search_results = await self.browser.main_tab.select_all(self.selectors.interactions.search_results)
                # First child is "Search Results". Second child is the actual search results
                search_results_children = search_results[-1].children[1].children

                search_results = self._filter_search_results(search_results_children)
            
            if match(r"thought for \d+(\.\d+)? seconds", child.text.lower()) and self._deepthink_enabled:
                self.logger.debug("Extracting the deepthink duration and content...")
                # This is the deepthink option, we can find the duration through splitting the text
                deepthink_duration = int(child.text.split()[2])
                
                # DeepThink content is shown by default, no need to click anything
                deepthink_content = await self.browser.main_tab.select_all(self.selectors.interactions.deepthink_content)
                soup = BeautifulSoup(repr(deepthink_content[-1]), 'html.parser')
                deepthink_content = "\n".join(get_text(str(p)).strip() for p in soup.find_all('p'))

        response = Response(
            text = response_text,
            chat_id = self._chat_id,
            deepthink_duration = deepthink_duration,
            deepthink_content = deepthink_content,
            search_results = search_results
        )
        
        self.logger.debug("Response generated!")
        return response
    
    async def reset_chat(self) -> None:
        """Resets the chat by clicking the reset button.
        
        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        reset_chat_button = await self.browser.main_tab.select(self.selectors.interactions.reset_chat_button)
        await reset_chat_button.click()
        self.chat_id = ""
        self.logger.debug("Chat reset!")
    
    async def logout(self) -> None:
        """Logs out of the DeepSeek account.
        
        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        self.logger.debug("Logging out...")
        await self.browser.main_tab.evaluate(
            "localStorage.removeItem('userToken')",
            await_promise = True,
            return_by_value = True
        )
        await self.browser.main_tab.reload()
        self.logger.debug("Logged out successfully!")
    
    async def switch_account(
        self,
        token: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None
    ) -> None:
        """Switches the account by logging out and logging back in with a new token.

        Args
        ---------
            token (Optional[str]): The new token to use.
            email (Optional[str]): The new email to use.
            password (Optional[str]): The new password to use.
        
        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method
            MissingCredentials: If neither the token nor the email and password are provided
            InvalidCredentials: If the token or email and password are incorrect
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        # Check if the token or email and password are provided
        if not token and not (email and password):
            raise MissingCredentials("Either the token alone or the email and password both must be provided")

        self.logger.debug("Switching the account...")

        # Log out of the current account
        await self.logout()

        # Update the credentials
        self._token = token
        self._email = email
        self._password = password

        if self._token:
            await self._login()
        else:
            await self._login_classic()
        
    async def delete_chats(self) -> None:
        """Deletes all the chats in the chat.
        
        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
            CouldNotFindElement: If the delete chats button is not found.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        self.logger.debug("Clicking the profile button...")
        profile_button = await self.browser.main_tab.select(self.selectors.interactions.profile_button)
        await profile_button.click()
        
        self.logger.debug("Clicking the profile options dropdown...")
        profile_options_dropdown = await self.browser.main_tab.select(self.selectors.interactions.profile_options_dropdown)
        await profile_options_dropdown.click()

        self.logger.debug("Finding and clicking the delete chats button...")
        delete_chats_button = await self._find_child_by_text(
            parent = profile_options_dropdown,
            text = "Delete all chats",
            in_depth = True
        )
        if not delete_chats_button:
            raise CouldNotFindElement("Could not find the delete chats button")

        await delete_chats_button.click()

        self.logger.debug("Clicking the confirm deletion button...")
        confirm_deletion_button = await self.browser.main_tab.select(self.selectors.interactions.confirm_deletion_button)
        await confirm_deletion_button.click()

        self.logger.debug("chats deleted!")
    
    async def switch_chat(self, chat_id: str) -> None:
        """Switches the chat by navigating to a new chat id.

        Args
        ---------
            chat_id (str): The new chat id to navigate to.
        
        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
            InvalidChatID: If the chat id is invalid
            CouldNotFindElement: If the textbox is not found
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        self.logger.debug(f"Switching the chat to: {chat_id}")
        await self.browser.main_tab.get(f"https://chat.deepseek.com/a/chat/s/{chat_id}")

        # Wait till text box appears
        self.logger.debug("Waiting for the textbox to appear...")
        try:
            await self.browser.main_tab.wait_for(self.selectors.interactions.textbox, timeout = 5)
        except:
            raise CouldNotFindElement("Could not find the textbox")

        chat_id_in_url = await self.browser.main_tab.evaluate(
            f"window.location.href.includes('{chat_id}')",
            await_promise = True,
            return_by_value = True
        )

        if not chat_id_in_url:
            raise InvalidChatID("The chat id is invalid")
        
        self._chat_id = chat_id
        self.logger.debug("Chat switched!")
    
    async def switch_theme(self, theme: Theme):
        """Switches the theme of the chat.

        Args
        ---------
            theme (Theme): The theme to switch to.
        
        Raises
        ---------
            MissingInitialization: If the initialize method is not run before using this method.
        """

        if not self._initialized:
            raise MissingInitialization("You must run the initialize method before using this method.")

        self.logger.debug(f"Switching the theme to: {theme.value}")
        await self.browser.main_tab.evaluate(
            f"localStorage.setItem('__appKit_@deepseek/chat_themePreference', JSON.stringify({{value: '{theme.value}', __version: '0'}}))",
            await_promise = True,
            return_by_value = True
        )

        await self.browser.main_tab.reload()
        self.logger.debug("Theme switched!")


        # does not work, couldnt figure out how to select an option in a dropdown
        # self.logger.debug(f"Switching the theme to: {theme.name}")
        # profile_button = await self.browser.main_tab.select(self.selectors.interactions.profile_button)
        # await profile_button.click()

        # profile_options_dropdown = await self.browser.main_tab.select(self.selectors.interactions.profile_options_dropdown)
        # await profile_options_dropdown.click()

        # settings_button = await self._find_child_by_text(
        #     parent = profile_options_dropdown,
        #     text = "Settings",
        #     in_depth = True
        # )
        # if not settings_button:
        #     raise CouldNotFindElement("Could not find the settings button")
        # await settings_button.click()

        # theme_select_parent = await self.browser.main_tab.select_all(self.selectors.interactions.theme_select_parent)
        # # click the actual theme select, use -1 since the last is the theme
        # # await theme_select_parent[-1].children[0].click()
        # await theme_select_parent[-1].children[0].mouse_click() # this works, but try with headless later
        # # try_another = False
        # # await sleep(3)
        # # breakpoint()
        # # if try_another:
        # #     await theme_select_parent[-1].children[1].mouse_click()
        # await sleep(5)
        
        # for child in theme_select_parent[-1].children[0].children:
        #     if child.text_all.lower() == theme.name.lower(): # figure this out TODO
        #         await child.mouse_click()
        #         break

        # breakpoint()

    async def text_to_speech(
        self,
        text: str,
        voice_id: str,
        api_key: Optional[str] = None,
        model_id: str = "eleven_flash_v2_5",
        output_format: str = "mp3_44100_128",
        output_path: Optional[str] = None,
    ) -> bytes:
        """Convert text to speech via ElevenLabs (Eleven Flash v2.5 by default).

        Args
        ---------
            text (str): Text to synthesize (e.g. response.text).
            voice_id (str): ElevenLabs voice ID. List voices: https://elevenlabs.io/docs/api-reference/get-voices.
            api_key (Optional[str]): ElevenLabs API key. Defaults to ELEVENLABS_API_KEY env.
            model_id (str): Model ID. Defaults to eleven_flash_v2_5.
            output_format (str): Audio format. Defaults to mp3_44100_128.
            output_path (Optional[str]): If set, write audio to this file.

        Returns
        ---------
            bytes: Audio bytes.

        Raises
        ---------
            TTSError: On missing API key or ElevenLabs API errors.
        """
        from .internal.tts import text_to_speech as _tts
        return await _tts(
            text=text,
            voice_id=voice_id,
            api_key=api_key,
            model_id=model_id,
            output_format=output_format,
            output_path=output_path,
        )
