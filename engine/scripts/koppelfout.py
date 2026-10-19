"""De fout van een koppeling (Zernio of Metricool), met de statuscode en of opnieuw proberen zin heeft."""


class KoppelFout(Exception):
    def __init__(self, bericht, status=None, data=None, tijdelijk=False):
        super().__init__(bericht)
        self.status, self.data, self.tijdelijk = status, data, tijdelijk
