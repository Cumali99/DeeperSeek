class DeeperSeekException(BaseException):
    pass


class InvalidChatID(DeeperSeekException):
    pass


class MissingCredentials(DeeperSeekException):
    pass


class InvalidCredentials(DeeperSeekException):
    pass


class ServerDown(DeeperSeekException):
    pass


class MissingInitialization(DeeperSeekException):
    pass


class CouldNotFindElement(DeeperSeekException):
    pass


class InvalidChatID(DeeperSeekException):
    pass


class TTSError(DeeperSeekException):
    pass
