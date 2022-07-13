import os
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional

from eve_tools.config import TOKEN_PATH

from .application import Application
from .sso.refresh_token import refresh_token
from .sso.esi_oauth_native import esi_oauth_local


@dataclass
class Token:
    """Hold info for a single token.

    (clientId, character_name) together act as primary key for each Token.
    """

    access_token: str
    retrieve_time: str
    refresh_token: str
    character_name: str
    character_id: int
    clientId: str


class ESITokens(object):
    """Holds tokens with the same client id.

    Each Application has a unique clientId, which can be used to merge with all Token(s) with the same clientId.
    Each Token has a unique (clientId, character_name) pair, acting as key for each token.
    The ESITokens class hold all Token(s) with the given clientId, and each Token can be accessed using cname.

    This class effectively performs one read when initializing, and one read & write upon exiting.
    Class methods make effect on a buffer, self.tokens, and local files are updated when save() or use "with" statement.

    This clas does not support customizing Token(s) information.
    Customized Application is supported but caller need to make sure the attribute "app" is stored in local file
    to ensure Token(s) under "app" is effective in ESI API calls.

    Attributes:
        app: Application
            An instance of Application class that holds an effective clientId.
            All tokens generated will have the clientId field attached as a key.
        update_time: int (seconds)
            Refresh Token(s) if at least update_time passed since last refresh.
            Default 1198 seconds. EVE ESI requires tokens are effective for 1199 seconds after generation.

    Example usage:
    >>> app = Application(clientId, scope, callbackURL)
    >>> with ESITokens(app) as tokens:
    >>>     # do something, such as generate token:
    >>>     tokens.generate()
    >>> # or use the class without with:
    >>> tokens = ESITokens(app)
    >>> # do something
    >>> tokens.save()   # store change to local file
    """

    def __init__(self, app: Application, **kwd):
        self.app = app
        self.clientId = app.clientId
        self.scope = app.scope
        self.callbackURL = app.callbackURL  # not implemented

        self.tokens = []  # list of tokens for the App

        # ESI token lifespane is 1199 seconds, 1198 for safety
        self._update_time = kwd.get("update_time", 1198)

        self._save_flag = False  # Need to save() or not. Every method that changes self.tokens set this to True.

        self._load_tokens()

    def refresh(self, cname: Optional[str] = None) -> None:
        """Refreshes access token with character name under the Application.

        Updates access_token field of the Token instance with character_name = cname stored inside Tokens.
        The refresh will be executed if at least self._update_time has passed.
        If cname is None, refresh all Token under the Application.

        Args:
            cname: A string of the character name, acting as a key for a Token.

        Returns: None

        Raises:
            KeyError: {cname} is not a valid character name.
        """
        if cname:
            tokens_unrefreshed = [
                token_ for token_ in self.tokens if token_.character_name == cname
            ]
        else:
            tokens_unrefreshed = self.tokens

        if not tokens_unrefreshed:
            raise KeyError(f"Can't find Token with character_name = {cname}")

        for token_ in tokens_unrefreshed:
            if (int(time.time()) - token_.retrieve_time) < self._update_time:
                continue
            new_token_dict = refresh_token(token_.refresh_token, self.clientId)
            token_.access_token = new_token_dict["access_token"]
            token_.retrieve_time = new_token_dict["retrieve_time"]
            token_.refresh_token = new_token_dict["refresh_token"]
            # character_name and clientId field should not change.
            self._save_flag = True

    def generate(self) -> Token:
        """Generates new token for the Application.

        Generates a new Token instance that could be used for authorized request.
        If the token is generated with the same character as another Token for the Application,
        the old Token in self.tokens will be updated without creating a new Token.
        New Token is stored in a buffer, not immediately stored to the file system.

        A url will be copied to clipboard after calling, and the user needs to manually
        visit the url in any browser, complete the EVE login process,
        and copy the URL after login to the command prompt.

        Args:
            print_info: A bool of whether to print intermediate information in the authorization.
        """
        new_token_dict = esi_oauth_local(
            clientID=self.clientId,
            scope=self.scope,
            callbackURL=self.callbackURL,
        )

        # When user repeatedly calling generate()...
        old_token = None
        for token_ in self.tokens:
            if token_.character_id == new_token_dict["character_id"]:
                old_token = token_
                break

        self._save_flag = True

        if old_token:
            old_token.access_token = new_token_dict["access_token"]
            old_token.retrieve_time = new_token_dict["retrieve_time"]
            old_token.refresh_token = new_token_dict["refresh_token"]
            return old_token
        else:
            new_token = Token(
                new_token_dict["access_token"],
                new_token_dict["retrieve_time"],
                new_token_dict["refresh_token"],
                new_token_dict["character_name"],
                new_token_dict["character_id"],
                self.clientId,
            )
            self.tokens.append(new_token)
            return new_token

    def save(self, **options) -> None:
        """Saves tokens to a local file.

        Packs each Token in self.tokens to a dict, and store to local file using json.
        Local file has clientId: List[dict(Token)] format; the save perform file[clientId] = [dict(Token), ...].

        Args: None
        """
        if not self.tokens:
            return

        if not self._save_flag:
            return

        tokens_list = [asdict(token_) for token_ in self.tokens]

        if os.path.exists(TOKEN_PATH) and os.stat(TOKEN_PATH).st_size:
            with open(TOKEN_PATH, "r") as all_tokens_fp:
                all_tokens = json.load(all_tokens_fp)
            all_tokens.update({self.clientId: tokens_list})
        else:
            all_tokens = {self.clientId: tokens_list}

        with open(TOKEN_PATH, "w") as all_tokens_fp:
            json.dump(all_tokens, all_tokens_fp)

    def exist(self, cname: Optional[str] = None) -> bool:
        """Checks if a Token or tokens exist or not.

        If cname is not given, check if current Application has any tokens.
        If cname is given, check if current Application has a Token with character_name = cname.

        Args:
            cname: A string of the character name, acting as a key for a Token.

        Returns:
            A bool showing if Token exists or not.
        """
        if cname == "any" or not cname:
            return bool(self.tokens)
        else:
            for token_ in self.tokens:
                if token_.character_name == cname:
                    return True
        return False

    def remove(self, cname: str) -> Token:
        """Removes a Token with given character name.

        Removes a Token with character_name = cname. The Token is removed using list.pop() and returned.
        If no Token matches the cname, raise ValueError.

        Args:
            cname: A string of the character name, acting as a key for a Token.

        Returns:
            Token removed from Application.

        Raises:
            ValueError: No Token matches character_name = {cname}.
        """
        for i in range(len(self.tokens)):
            if self.tokens[i].character_name == cname:
                self._save_flag = True
                return self.tokens.pop(i)

        raise ValueError(f"No Token matches character_name = {cname}.")

    def _load_tokens(self) -> None:
        """Load tokens from local file.

        Read a local json file and search for file[clientId] = self.clientId.
        Unpack tokens in local file to multiple Token(s) stored in self.tokens.
        Does not support custom token file yet. Called once upon init.
        """
        if not os.path.exists(TOKEN_PATH) or not os.stat(TOKEN_PATH).st_size:
            return

        with open(TOKEN_PATH, "r") as all_tokens_fp:
            all_tokens = json.load(all_tokens_fp)

        if self.clientId not in all_tokens:
            return

        tokens = all_tokens[self.clientId]
        for token_ in tokens:
            # More robust when ADDING (removing not considered) new attr to Token but local token.json not updated.
            _append = True
            for attr in Token.__annotations__:
                if attr not in token_:
                    _append = False
                    break
            
            if _append:
                self.tokens.append(Token(**token_))  # dictionary unpacking

    def __getitem__(self, cname: str) -> Token:
        """Gets the Token with cname.

        Searches for sel.tokens and get the reference of Token with character_name = cname.
        Caller can pass in cname="any" to indicate getting any Token without considering cname.
        Token is refreshed before return if the "update_time" threshold is met.

        Args:
            cname: A string of the character name, acting as a key for a Token.

        Returns:
            Token with cname from Application.

        Raises:
            ValueError: No Token matches character_name = {cname}.
        """
        if cname == "any" and self.tokens:
            token = self.tokens[0]
            self.refresh(token.character_name)
            return token
        for token_ in self.tokens:
            if token_.character_name == cname:
                self.refresh(token_.character_name)
                return token_

        if cname == "any":
            raise ValueError(f"No Token found.")
        else:
            raise ValueError(f"No Token matches character_name = {cname}.")

    def __str__(self) -> str:
        return "Tokens(app={app}, tokens={tokens})".format(
            app=str(self.app), tokens=str(self.tokens)
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.save()
