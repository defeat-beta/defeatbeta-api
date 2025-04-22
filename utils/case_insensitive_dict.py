class CaseInsensitiveDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._keys = {}

    def __setitem__(self, key, value):
        lower_key = key.lower()
        self._keys[lower_key] = key
        super().__setitem__(lower_key, value)

    def __getitem__(self, key):
        return super().__getitem__(key.lower())

    def get(self, key, default=None):
        return super().get(key.lower(), default)

    def __contains__(self, key):
        return super().__contains__(key.lower())

    def items(self):
        return ((self._keys[k], v) for k, v in super().items())

    def keys(self):
        return self._keys.values()