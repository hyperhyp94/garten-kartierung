"""Fehler, deren Text dem Nutzer gezeigt wird."""


class Eingabefehler(ValueError):
    """Eine Eingabe passt nicht. Die Antwort an das Handy enthält den Text."""

    def __init__(self, text: str, status: int = 422):
        super().__init__(text)
        self.status = status
