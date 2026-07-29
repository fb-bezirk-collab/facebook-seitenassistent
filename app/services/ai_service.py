class AiService:
    """
    Dienst für die spätere KI-Textbearbeitung.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
    ):
        self.api_key = api_key
        self.model = model